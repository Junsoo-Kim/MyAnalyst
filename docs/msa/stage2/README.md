# MSA 2단계 — Kafka 도입 (Transactional Outbox → Kafka)

작업일: 2026-10-20 · 대상: `BE/`, `docker-compose.yml` · Kafka 3.9.1 (KRaft 단일 브로커), Spring Kafka, Spring Modulith 1.3.12

배포 단위는 여전히 BE 하나다. 바뀐 것은 **모듈 사이의 연결**이다. 1단계에서 프로세스 안 이벤트로 이어져 있던
생성·용어 사전·채팅·알림 모듈이 이제 Kafka 토픽으로만 연결된다. 그래서 이후 단계에서 모듈을 별도 서비스로
떼어낼 때 코드 이동만으로 끝나고, 연결 방식은 바뀌지 않는다.

## 1. 구조

```
[generation] Job 저장 + ReportGenerationRequested ─┐  같은 트랜잭션 (event_publication = Outbox)
                                                    └→ 커밋 후 Modulith가 Kafka로 발행
generation.requested ──→ [generation-dispatcher] claim → 실행 → RAG
report.created (compact) ──→ [dictionary] 용어 저장
report.deleted ──→ [dictionary], [chat] 정리
job.status-changed ──→ [notification-<인스턴스별 UUID>] SSE
실패 3회(1s→2s→4s) ──→ <topic>.DLT
```

| 토픽 | key | 발행 | 소비 그룹 |
|---|---|---|---|
| `generation.requested` | jobId | generation (최초 요청, 재시도 재발행) | `generation-dispatcher` |
| `job.status-changed` | jobId | generation | `notification-<uuid>` (인스턴스마다 전부 수신, `latest`) |
| `report.created` | reportId | report | `dictionary` |
| `report.deleted` | reportId | report | `dictionary`, `chat` |
| 각 `<topic>.DLT` | 원본 key | 에러 핸들러 | (수동 확인 후 재투입) |

- 모든 토픽 3파티션. 토픽은 **발행하는 모듈이 선언**한다(`GenerationKafkaTopics`, `ReportKafkaTopics`). 브로커 자동 생성은 꺼 두었다.
- 메시지는 JSON. 헤더 `event-type`, `event-version`(현재 `1`)을 붙여 Python 워커(3단계) 같은 다른 언어 소비자도 클래스 정보 없이 해석할 수 있게 했다.
- 소비자는 모두 **자연 멱등**이다: 생성 dispatch는 비관적 락 claim, 용어 저장은 "이미 있으면 건너뜀", 삭제는 몇 번 와도 결과가 같다. 그래서 별도의 `processed_events` 테이블은 두지 않았다.
- 재시도: 실패한 Job은 `RETRYING`이 되고, 백오프 시간이 지나면 스케줄러가 `QUEUED`로 바꾸면서 `generation.requested`를 **다시 발행**한다. 최초 실행과 재시도가 같은 Kafka 경로를 탄다.

## 2. 작업 중 발견한 문제

1. **브로커가 내려간 상태에서 BE가 재시작되면 BE 전체가 뜨지 않았다.**
   Kafka 컨테이너가 멈추면 Docker DNS에서 `kafka` 이름이 사라지고, Kafka 클라이언트가 생성 시점에
   `No resolvable bootstrap urls`로 실패한다. Spring Kafka 기본 설정은 리스너를 컨텍스트 시작과 함께 띄우므로
   이 예외가 기동을 실패시켰다(exit 1). 브로커 장애가 로그인·조회까지 막는 **장애 전파**였다.
   → 리스너와 토픽 생성을 기동에서 분리했다(`spring.kafka.listener.auto-startup=false`). `KafkaListenerStarter`가
   10초마다 토픽 확인과 멈춘 리스너 시작을 재시도한다. 발행 쪽은 원래 Modulith 레지스트리가 미완료 발행을 다시 보낸다.
2. **DLT 발행이 실패해 파티션이 멈췄다.**
   Spring Kafka 3.x `DeadLetterPublishingRecoverer`의 기본 목적지는 `<topic>-dlt`인데 토픽은 `<topic>.DLT`로 만들었다.
   브로커 자동 생성을 꺼 두었기 때문에 이름 불일치가 조용히 새 토픽을 만드는 대신 실패로 드러났지만, DLT 발행이
   실패하는 동안 에러 핸들러가 같은 메시지를 계속 다시 시도해 **파티션 0이 독성 메시지 뒤에서 멈췄다**(그 뒤에 온 정상
   보고서의 용어가 저장되지 않음). → 목적지를 `<topic>.DLT`, 같은 파티션으로 명시했다. 재기동 후 막혀 있던 메시지가 DLT로
   가고 뒤의 메시지가 처리되는 것까지 확인했다.

## 3. 검증 (docker compose: PostgreSQL·Redis·Kafka + BE, RAG는 스텁)

### E1. 기본 흐름

로그인 → `POST /report-jobs` → SSE `QUEUED → RUNNING → SUCCEEDED` → `report.created` 소비로 용어 저장 → 채팅 →
삭제 후 `report.deleted` 소비로 채팅·용어 정리. 토픽 8개(본 토픽 4 + DLT 4)가 3파티션으로 생성되고
`report.created`에 `cleanup.policy=compact`가 적용된 것을 확인했다. 메시지 key가 jobId/reportId이고 `event-type`,
`event-version` 헤더가 붙어 있는 것도 확인했다.

### E2·E3. 브로커 장애 + 장애 중 BE 재시작 ([로그](experiment-broker-outage.log))

| 시점 | 결과 |
|---|---|
| 브로커 중지 후 BE 재기동 | 10초 만에 health UP (수정 전에는 기동 실패) |
| 브로커 다운 중 로그인, 보고서 목록, 용어 조회 | 모두 200, 수십 ms |
| 브로커 다운 중 `POST /report-jobs` | 202, 111ms. Job은 `QUEUED`, 미완료 발행 기록으로 남음 |
| 브로커 다운 중 | 이전 실험(수정 전 BE가 기동 실패했던 때)에 만든 Job도 미완료 발행으로 살아 있음 |
| 브로커 재기동 | 리스너 자동 시작, 두 Job 모두 `SUCCEEDED` |
| 중복 여부 | Job별 시도 1회, 보고서 1건, RAG 호출 1회. 미완료 발행 0 |

1단계에서 검증하지 못했던 "커밋 후 디스패치 전 프로세스 종료 시 재전달"도 여기서 확인됐다. 브로커가 내려가 있는 동안
발행이 미완료로 남은 상태에서 BE 프로세스가 두 번 교체됐고, 브로커가 돌아온 뒤 정확히 한 번 처리됐다.

### E4. 독성 메시지 → DLT

`report.created`에 JSON이 아닌 값을 넣었다. 1s·2s·4s 재시도 후 `report.created.DLT` 파티션 0(원본과 같은 파티션)으로
이동했고, 헤더에 원본 토픽·소비 그룹·예외 클래스가 남았다. `kafka.consumer.dead_lettered` 지표가 1 증가했고,
그 뒤에 온 정상 메시지가 처리되어 `dictionary` 그룹의 lag가 0이 됐다.

### E5. 중복 메시지

이미 처리된 `report.created`(reportId=1)를 그대로 다시 발행했다. 용어 행 수가 2 → 2로 변하지 않았다.

### E6. 재시도 경로

RAG가 500을 반환하도록 했다. `RETRYING → QUEUED(재발행) → RUNNING`을 세 번 반복한 뒤 `FAILED`가 됐다.
해당 Job의 `generation.requested` 메시지는 3건이다.

### 테스트

`./mvnw clean test` 14개 통과. 신규 테스트는 없다. `MyanalystApplicationTests`에 Kafka Testcontainer를 추가했고,
DB 락만 보는 `ReportJobConcurrencyIT`는 Kafka를 끈 채로 돌린다.

## 4. 알려진 공백 / 다음 단계로 넘긴 것

- **긴 작업과 poll 간격 문제는 아직 나타나지 않는다.** 지금의 dispatch 소비자는 claim 후 실행을 별도 스레드 풀에 넘기고
  바로 반환하기 때문이다. RAG 실행을 Python 워커가 Kafka 소비자로 직접 맡는 3단계에서 다룬다.
- **`report.created` 재생 시 삭제된 보고서의 용어가 되살아날 수 있다.** 삭제가 같은 key의 tombstone으로 남지 않기
  때문이다. 재생으로 읽기 모델을 재구축하는 실험(5단계, chat-service)에서 함께 해결한다.
- 메시지에 Spring의 `__TypeId__` 헤더(Java 클래스 이름)가 붙는다. 소비자는 메서드 파라미터 타입으로 역직렬화하므로
  이 헤더에 의존하지 않지만, 언어 중립 계약을 위해 이후 제거를 검토한다.
- 비동기 발행 풀 때문에 몇 ms 차이로 커밋된 상태 변경이 뒤바뀌어 나갈 수 있다. 알림 모듈은 이미 보낸 것보다 오래된
  `updatedAt`을 버린다.
- compose의 Kafka는 볼륨이 없어 `docker compose down` 시 데이터가 사라진다(stop/start는 유지).
- consumer lag 모니터링(Kafka exporter + Prometheus)은 아직 없다.
- `infra/envs/prod/main.tf`에 `KAFKA_BOOTSTRAP_SERVERS`가 없다. 7단계(Kafka EC2 모듈)에서 추가한다.
  그 전에 배포되더라도 위 1번 수정 덕분에 BE는 뜨지만, 이벤트는 흐르지 않는다.
