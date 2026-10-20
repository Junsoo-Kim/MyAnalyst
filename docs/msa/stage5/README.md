# MSA 5단계: 이벤트 소비 서비스 분리 (notification, dictionary, chat)

작업일: 2026-10-21 · 대상: `services/notification-service`, `services/dictionary-service`, `services/chat-service`, `BE/`(report·generation 이벤트, chat·dictionary·notification 모듈 제거), `services/api-gateway`, `contracts/`, `scripts/`, `docker-compose.yml`, CI

## 1. 구조

```
브라우저 ──▶ api-gateway :8080
              ├─ GET  /report-jobs/*/events ─────────────▶ notification-service ◀── job.status-changed
              ├─ GET  /reports/*/dictionary ─────────────▶ dictionary-service   ◀── report.created
              ├─ POST /chat, /chat/stt, GET /reports/*/chat ▶ chat-service ──HTTP▶ qa, stt
              │                                                                ◀── report.created
              ├─ (4단계 경로) auth-service, user-service
              └─ /** ──▶ BE: report, generation, marketdata 모듈 ──▶ report.created, job.status-changed 발행
```

| 서비스 | BE에서 옮긴 것 | 소유 데이터(공용 DB, D4) | 소비 |
|---|---|---|---|
| notification-service | `notification` 모듈 | 없음(Job별 마지막 상태를 메모리에 최대 1만 건) | `job.status-changed`, 그룹 `notification-<uuid>`(latest) |
| dictionary-service | `dictionary` 모듈 | `dictionary`, **`dictionary_reports`**(reportId → userId) | `report.created`, 그룹 `dictionary` |
| chat-service | `chat` 모듈, qa·stt 클라이언트 설정 | `chats`, **`chat_reports`**(reportId → userId, 본문) | `report.created`, 그룹 `chat` |

- 세 모듈은 `git mv`로 옮겼다(패키지 이름 유지, 이력이 이어진다). 각 서비스는 user-service와 같은 골격이다: `InternalTokenFilter`(X-Internal-Token), `CurrentUser`(X-User-Id), `KafkaListenerStarter`(브로커 없이도 기동), DLT 오류 처리기(dictionary·chat).
- BE에서 사라진 것: `ReportService.assertOwnedBy / getOwnedReportContent`(다른 모듈이 부르던 소유권 확인), qa·stt 설정, `report.deleted` 토픽 선언.

### 소유권: 요청마다 묻지 않고 이벤트 사본으로 판단 (D1)

전에는 세 모듈이 BE 안에서 `ReportService`·`ReportJobService`를 직접 불러 소유권을 확인했다. 서비스로 나누면 이 호출이 동기 HTTP가 되고, 그러면 BE가 내려가는 순간 사전·채팅도 같이 멈춘다. 그래서 각 서비스가 필요한 만큼만 사본을 갖는다.

- `ReportCreated`에 `content`를 추가했다(D2, 하위 호환이라 `event-version` 1 유지). dictionary는 `userId`만, chat은 `userId`와 본문을 보관한다.
- `ReportJobResponseDto`(= `job.status-changed` 본문)에 `userId`를 추가했다. notification-service는 구독을 요청자 ID와 함께 등록하고, 이벤트의 `job.userId`가 같은 구독자에게만 보낸다. 남의 jobId로 구독하면 연결은 열리지만 아무것도 받지 못한다. 전에는 404였다. 구독 시점에 BE에 물어보지 않으므로 존재 여부를 알 수 없다.
- 구독 직후의 현재 상태는 이 인스턴스가 마지막으로 본 스냅샷이 있고 소유자가 같으면 바로 보낸다. 없으면 다음 이벤트부터 보낸다. 화면(`ReportJobView`)은 구독 전에 `GET /report-jobs/{id}`로 현재 상태를 읽고 2초마다 다시 읽으므로 SSE는 최선 노력 전달이다.
- 사본이 생기기 전(이벤트 도착 전)에 요청하면 404다. 측정한 지연은 보고서 저장 직후 10~70ms였다(E1, E4).

### 삭제: 같은 토픽, 같은 key (D3)

`ReportDeleted`를 `report.created` 토픽에 같은 key(reportId)로 발행한다. 소비자는 `event-type` 헤더(`ReportCreated` / `ReportDeleted`)로 구분한다. compaction 뒤에도 보고서별 마지막 레코드는 삭제로 남으므로, offset을 처음으로 되돌려 다시 읽어도 삭제된 보고서는 살아나지 않는다(E8).

- 별도 `report.deleted` 토픽은 소비자가 없어져 선언을 지웠다. 이미 만들어진 환경에서는 토픽이 남아 있으니 필요하면 직접 지운다.
- Modulith 외부 발행은 이벤트 하나에 토픽 하나라서 "두 토픽에 발행"은 하지 않았다. 대신 소비자가 한 토픽만 읽게 정리했다(ROADMAP 5단계에서 우선 검토하라던 방안).
- 새 소비자는 값을 JSON 바이트로 받아 필요한 필드만 읽는다. Spring `__TypeId__` 헤더(Java 클래스 이름)는 보지 않는다. 헤더 자체를 없애는 일은 6단계로 넘겼다(D11).

### 이벤트 이전에 생긴 데이터: 일회성 정리 스크립트

재생으로 다시 만들 수 없는 경우가 두 가지 있다.

1. Kafka 도입(2단계) 이전에 저장된 보고서는 발행된 적이 없어 사본이 생기지 않는다.
2. 5단계 이전의 삭제는 옛 `report.deleted` 토픽으로 나갔다. 그래서 `report.created`를 처음부터 읽으면 그 보고서가 사본으로 되살아난다.

`scripts/migrate/stage5_report_copies.sql`은 공용 DB의 `reports`를 기준으로 사본을 채우고, 없는 보고서의 사본과 채팅·용어를 지운다. 여러 번 실행해도 결과가 같다(E7). 6단계에서 DB를 나누면 이 스크립트는 쓸 수 없다. 그 전에 한 번 실행해 둔다.

## 2. 작업 중 발견한 문제

1. **보낼 상태가 없는 SSE 구독은 응답 헤더조차 오지 않았다.** `SseEmitter`는 첫 `send` 때 헤더를 내보낸다. 전에는 구독 즉시 현재 상태를 보냈기 때문에 드러나지 않았다. 사본이 없거나 남의 Job이면 보낼 것이 없어서, 연결이 응답 없이 매달려 있었다(E3 첫 실행에서 bob의 HTTP 상태 `None`). 구독 시 SSE 주석(`:subscribed`)을 보내도록 고쳤다. EventSource는 주석을 무시한다.
2. **qa-service는 100자 미만 보고서를 400으로 거절한다.** 검증용 보고서가 짧아 첫 실행에서 채팅이 500으로 실패했다. 이 동작은 원래 있던 것이다. 다만 chat-service가 그 400을 500으로 바꿔 내보내는 것도 기존 동작 그대로다(아래 공백).
3. **재생만으로는 사본을 완전히 복원할 수 없다.** 위 "이벤트 이전에 생긴 데이터" 참고. E8에서 보고서 183개 중 182개가 복원됐고, 남은 1개는 이벤트 없이 넣은 보고서였다.

## 3. 검증 (docker compose: Gateway·auth·user·BE·notification·dictionary·chat·qa·stt·PostgreSQL·Redis·Kafka)

generation-worker와 RAG 스택(knowledge, Milvus, OpenSearch)은 띄우지 않았다. 그 대신 `scripts/verify/stage5_flow.py`가 워커 역할을 한다. 계약(`contracts/generation.*.v1.json`) 형식의 `generation.progressed` / `generation.completed`를 브로커에 직접 넣는다. 그 뒤의 흐름은 실제 코드 그대로다: BE 저장 → `report.created` → 각 서비스. qa·stt는 OpenAI 스텁을 쓴다.

| 실험 | 결과 | 로그 |
|---|---|---|
| E1 사본 생성 | 보고서 저장 → `dictionary_reports`, `chat_reports`(본문 540자)에 사본. 사전 조회 200(저장 후 10ms) | [flow](experiment-flow.txt) |
| E2 소유권 | 남의 보고서: 사전·채팅·채팅 기록 모두 403. 없는 보고서 404. 본인 채팅 200(qa 경유), 기록 1건 | 같은 파일 |
| E3 SSE 필터링 | 소유자: RUNNING/10 → RUNNING/50 → SUCCEEDED/100. **같은 jobId를 구독한 다른 사용자: 200, 이벤트 0건.** 완료 후 구독하면 마지막 스냅샷(SUCCEEDED) | 같은 파일 |
| E4 삭제 | DELETE → 사전 404(70ms), 채팅 404(10ms). 용어·사본·채팅 기록·채팅 사본 모두 0행 | 같은 파일 |
| E5 음성 질문 | `/chat/stt` → stt → qa 200. 다른 사용자 403 | 같은 파일 |
| E6 **BE 중단** | BE 경로(`/reports/{id}`)는 503. **사전 조회, 채팅, 채팅 기록은 200.** BE 재시작 후 7초 안에 복구 | 같은 파일 |
| E7 일회성 정리 | 이벤트 없는 보고서: 사전·채팅 404 → 스크립트 후 200. 삭제된 보고서의 사본·채팅 1/1/1 → 0/0/0. 두 번째 실행은 0행 변경 | [replay-and-migration](experiment-replay-and-migration.txt) |
| E8 **재생** | 보고서 200개 생성, 20개 삭제 후 chat-service 정지 → `chat_reports` 비움 → 그룹 `chat` offset을 처음으로 → 시작. 메시지 228개(생성 + 삭제)를 읽어 **사본 182개 복원, 삭제된 보고서의 사본 0개.** 컨테이너 시작부터 lag 0까지 7.7초(JVM 기동 약 5초 포함). 채팅 기록(`chats`)은 사본이 아니라 원본이므로 비우지 않았고 그대로 남았다 | 같은 파일 |

### 테스트

BE `./mvnw clean test` 15개 통과. 기존 테스트는 고칠 필요가 없었다(바뀐 공개 API를 쓰는 테스트가 없었다). `ModularityTests`는 세 모듈이 빠진 구조로 통과한다. 새 서비스 셋은 빌드(`mvnw verify`)만 확인했고 CI에 추가했다. 새 테스트는 추가하지 않았다.

## 4. 알려진 공백

- **사본은 최종 일관성이다.** 보고서 저장 직후 아주 짧은 시간(측정 10~70ms) 동안 사전·채팅이 404일 수 있다. 서버와 FE 모두 재시도하지 않는다. FE 화면에서는 확인하지 않았다.
- **보고서 수정 이벤트가 없다.** 지금은 보고서를 수정하는 API가 없어서 문제가 아니다. 수정 기능이 생기면 `ReportUpdated`(같은 토픽, 같은 key)가 필요하다.
- **SSE 구독은 존재하지 않거나 남의 Job이어도 열린다**(전에는 404). 정보는 새지 않지만, 잘못된 jobId로 연결이 열린 채 남는다. 연결은 클라이언트가 닫을 때까지 유지된다.
- notification의 스냅샷은 인스턴스 메모리에 있다. 재시작하면 비고, 인스턴스마다 다르다. 이 경우 화면의 주기 조회가 현재 상태를 보완한다.
- qa가 400(짧은 보고서·질문)을 돌려줘도 chat-service는 500으로 응답한다. 원래 동작이다.
- 새 Java 소비자에는 계약 테스트가 없다. `contracts/report.*.v1.json`, `job.status-changed.v1.json`은 예시 문서로만 있다.
- 4단계 상태에서 그대로 올리는 전환(기존 `dictionary` 그룹 offset 이어받기, 남은 `report.deleted` 토픽)은 실행해 보지 않았다. E7은 빈 환경에 옛 데이터를 SQL로 흉내 내 확인했다.
- D11(`ask_llm` 예외화, `__TypeId__` 제거)은 6단계로 넘겼다.
