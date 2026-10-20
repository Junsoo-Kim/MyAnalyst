# MSA 1단계 — Spring Modulith로 모듈 경계 확정

작업일: 2026-10-20 · 대상: `BE/` (Spring Boot 3.4.5, Spring Modulith 1.3.12)

배포 단위는 아직 Spring Boot 애플리케이션 하나다. 이 단계의 목표는 이후 서비스로 떼어낼 경계를
모놀리스 안에서 먼저 확정하고, 그 경계를 테스트로 강제하는 것이다.

## 1. 진행 방식

1. **커밋 A** (`11f6137`) — 로직 변경 없이 계층별 패키지(`controller/service/repository/entity/dto`)를
   도메인 모듈 패키지로만 옮기고 `ModularityTests`(`ApplicationModules.verify()`)를 추가했다.
   기존 코드의 경계 위반을 그대로 드러내기 위해 이 시점의 verify는 **실패하는 상태로 커밋**했다.
2. **커밋 B** — 검출된 위반을 해소했다. verify 통과.

## 2. 커밋 A에서 verify가 검출한 것 (원문: [verify-before.txt](verify-before.txt))

| 구분 | 내용 |
|---|---|
| 순환 의존 | `report ↔ chat`, `report ↔ dictionary`, `report ↔ user` (+ 이를 경유하는 3-모듈 순환) |
| 원인 | JPA 양방향 연관관계(`Report.chats`, `Report.dictionaryEntries`, `User.reports`)와 서로의 Repository 직접 사용 (`ReportService → DictionaryRepository`, `DictionaryService/ChatService → ReportRepository`) |
| 내부 타입 직접 참조 | 232건. 예: `chat`·`dictionary`·`generation` → `report.internal.Report`, `generation`·`report` → `user.internal.UserRepository` |

## 3. 해소 방법

| 위반 | 해소 |
|---|---|
| 엔티티 간 연관관계 | `@ManyToOne`/`@OneToMany`를 ID 컬럼으로 교체 (`Report.userId`, `Chat.reportId`, `Dictionary.reportId`, `ReportJob.userId/reportId`). 컬럼명은 그대로라 데이터 이전 없음 |
| `report → dictionary` (보고서 저장 시 용어 저장) | 보고서 모듈이 `ReportCreated`를 발행하고, 용어 사전 모듈이 `@ApplicationModuleListener`로 저장 |
| `chat/dictionary → report` 내부 접근 | `ReportService`의 공개 API(`assertOwnedBy`, `getOwnedReportContent`)만 사용 |
| 보고서 삭제 시 DB cascade | `ReportDeleted` 이벤트 → 채팅·용어 모듈이 각자 정리. 기존 DB에 남은 모듈 간 FK는 `ModuleBoundaryMigration`이 기동 시 제거 |
| SSE가 생성 서비스 안에 섞임 | `notification` 모듈로 분리. 생성 모듈은 `ReportJobStatusChanged`만 발행 |
| RAG 호출이 보고서 서비스 안에 있음 | `generation.internal.RagReportClient`로 이동. 보고서 모듈은 RAG를 모른다 |
| 뉴스·주가 프록시가 보고서 서비스 안에 있음 | `marketdata` 모듈로 분리 |
| 세션 속성 문자열을 컨트롤러마다 직접 읽음 | `auth.CurrentUser` 한 곳으로 모음 (Gateway 헤더 방식 전환 대비) |
| 직접 만든 Outbox relay | Modulith 이벤트 발행 레지스트리(JDBC, `event_publication`)로 교체. Job 저장과 `ReportGenerationRequested` 발행 기록이 한 트랜잭션 |

동기식 `POST /reports`(요청 스레드에서 RAG를 기다리던 구버전 API)는 제거했다. FE는 이미 `POST /report-jobs`만 쓴다.

## 4. 결과 모듈 의존 (모두 단방향, 순환 없음)

```
user          ← (의존 없음)
auth          → user
report        → auth, shared
generation    → user, report, auth, shared
dictionary    → report(uses, listens to ReportCreated/ReportDeleted), auth, shared
chat          → report(uses, listens to ReportDeleted), auth, shared
notification  → generation(uses, listens to ReportJobStatusChanged), auth
marketdata    → shared
shared (OPEN) — 예외, 추적, WebClient, 캐시, 이벤트 인프라
```

다이어그램: [components-before.puml](components-before.puml) → [components-after.puml](components-after.puml)

## 5. 작업 중 발견한 버그

1. **(기존 버그) 20자 넘는 용어 하나가 보고서 저장 전체를 실패시킴.**
   구버전은 용어 저장 실패를 `try/catch`로 삼켰지만, 같은 트랜잭션이 rollback-only로 표시돼 보고서 저장이
   `Transaction silently rolled back` 500으로 끝났다. 이전 버전 jar를 실제 PostgreSQL에 띄워 재현했다.
   이제 용어는 별도 트랜잭션(이벤트 리스너)에서 저장하고, 컬럼(20자)에 맞지 않는 용어는 경고 로그를 남기고 건너뛴다.
2. **(이번 변경에서 생겨 잡은 버그) 이벤트 레지스트리 컬럼 길이.**
   처음 쓴 JPA 레지스트리는 테이블 생성을 Hibernate에 맡겨 `serialized_event`가 `varchar(255)`가 됐고,
   `ReportJobStatusChanged` 저장이 실패했다. `ReportJobConcurrencyIT`가 잡았다. JDBC 레지스트리(자체 스키마, `TEXT`)로 교체.
3. **(이번 변경에서 생겨 잡은 버그) 비동기 리스너가 스케줄러 단일 스레드에서 실행됨.**
   `reportJobExecutor`(Executor 빈) 때문에 Boot가 기본 비동기 풀을 만들지 않아 `@Async`가 `scheduling-1`로
   떨어졌다. 실제 컨테이너 로그에서 발견. `ModuleEventAsyncConfig`로 전용 풀(`module-event-*`) 지정.
4. **(기존 설정 문제) `ReportJobConcurrencyIT`가 CI에서 한 번도 실행되지 않았음.**
   Surefire 기본 include에 `*IT`가 없다. includes에 추가했다.

## 6. 검증

### 테스트 (`./mvnw clean test`, Docker Desktop 기동 상태)

14개 통과: `ModularityTests` 1, `ReportJobServiceTest` 8, `ReportJobConcurrencyIT` 2, `RagReportClientContractTest` 1,
`ReportServiceContractTest` 1, `MyanalystApplicationTests` 1.

새로 추가한 테스트는 `ModularityTests` 하나다. 나머지는 바뀐 구조에 맞춘 수정이며, 기존 Outbox DEAD 전환 테스트는
기능 자체가 레지스트리로 대체되어 삭제했다. `RagReportClientContractTest`는 기존 `ReportServiceContractTest`의
`evaluations` 계약 검증을 RAG 호출이 옮겨간 곳으로 함께 옮긴 것이다.

### docker compose (실제 PostgreSQL·Redis + 새 BE 컨테이너)

RAG 서버는 OpenAI 키·Milvus 데이터 없이 띄울 수 없어, BE가 호출하는 엔드포인트만 흉내 내는 스텁을 사용했다.
**업그레이드 경로**를 보기 위해 이전 커밋(`ece2609`)의 BE로 먼저 스키마와 데이터를 만든 뒤 새 BE로 교체했다.

| 확인 항목 | 결과 |
|---|---|
| 이전 스키마의 모듈 간 FK 5개 제거, 모듈 내부 FK(`report_job_attempt → report_jobs`) 유지 | 확인 |
| 이전 버전에서 가입한 사용자 로그인, 이전 보고서·용어·채팅 조회 | 확인 |
| 비로그인 401, 타인 보고서·용어 403 | 확인 |
| `POST /report-jobs` 202 → SSE `RUNNING` → `SUCCEEDED`(reportId 포함) | 확인 |
| 같은 Idempotency-Key 재요청 → 같은 jobId | 확인 |
| `ReportCreated` → 용어 저장, 20자 초과 용어는 건너뛰고 보고서는 저장 | 확인 |
| 채팅 질의/기록, 뉴스 조회(marketdata) | 확인 |
| 이전 버전 보고서 삭제 → `ReportDeleted` → 채팅·용어 정리 (FK 없이도 정합성 유지) | 확인 |
| RAG 500 → `RETRYING`(지수 백오프) → 3회 시도 후 `FAILED`, 시도 이력 3건 | 확인 |
| 모든 이벤트 발행 기록 완료(미완료 0) | 확인 |
| 비동기 리스너가 `module-event-*` 풀에서 실행 | 확인 |

### 검증하지 못한 것

- **커밋 직후~디스패치 사이 프로세스 강제 종료 시 재전달.** 디스패치가 커밋 후 수 ms 안에 일어나 컨테이너 강제
  종료로 그 구간을 안정적으로 재현하지 못했다. 이 경로는 Modulith 레지스트리의 동작(`republish-outstanding-events-on-restart`)에
  의존하며, 직접 확인한 것은 아니다. 2단계에서 Kafka 브로커 중단 실험으로 함께 검증한다.
- 실제 RAG 서버(OpenAI·Milvus)와의 연동. BE→RAG 요청 계약은 `RagReportClientContractTest`로만 확인했다.

## 7. 알려진 공백

- 이전 relay는 이벤트 전달이 5회 실패하면 `DEAD`로 옮겼지만, Modulith 레지스트리는 상한 없이 재전달한다.
  Job은 `max-attempts`로 끝나므로 보고서 생성이 무한 반복되지는 않지만, 계속 실패하는 리스너는 30초마다 재시도된다.
  2단계(Kafka)에서 DLT로 보완한다.
- 기존 `outbox_events` 테이블은 더 이상 쓰지 않지만 ddl-auto가 지우지 않아 남아 있을 수 있다.
- `mvnw test` 종료 시 Surefire가 "fork JVM을 30초 후 강제 종료" 경고를 낸다. 이번 변경 이전 커밋에서도 동일하게 발생한다.
