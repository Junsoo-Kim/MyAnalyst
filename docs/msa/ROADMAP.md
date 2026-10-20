# MSA 전환 로드맵

모놀리스(Spring Boot BE + 단일 FastAPI RAG 서버)를 기능 단위 서비스로 나누는 작업의 계획, 현재 상태, 남은 단계.
단계별 상세 기록과 실험 로그는 `docs/msa/stageN/README.md`에 있다. 이 문서만 읽고도 다음 단계를 이어서 진행할 수 있게 쓴다.

## 1. 진행 상태

| 단계 | 내용 | 상태 | 기록 |
|---|---|---|---|
| 1 | Spring Modulith로 BE 내부 모듈 경계 확정(verify 테스트), JPA 연관관계 → ID 참조, 자체 Outbox → Modulith 이벤트 레지스트리 | 완료 | [stage1](stage1/README.md) |
| 2 | 모듈 간 이벤트를 Kafka로(@Externalized, DLT, 리스너 백그라운드 시작) | 완료 | [stage2](stage2/README.md) |
| 3 | rag_server → Python 서비스 분리, 보고서 생성을 Kafka 워커로 | 완료 | [stage3](stage3/README.md) |
| 4 | api-gateway + auth-service + user-service, 세션 → JWT | 완료 | [stage4](stage4/README.md) |
| 5 | 이벤트 소비 서비스 분리: notification, dictionary, chat | 완료 | [stage5](stage5/README.md) |
| 6 | 핵심 분리: report, generation → BE 모놀리스 소멸, 서비스별 DB | **다음** | – |
| 7 | 인프라: Terraform(ECS 서비스, Kafka EC2, Service Connect), 모니터링 | 대기 | – |

## 2. 현재 구조 (5단계 완료 시점)

```
브라우저 ──▶ api-gateway :8080 ── JWT(RS256) 검증, X-User-Id 재작성, CORS, 로그인 rate limit
              ├─ /sessions, /auth/** ──▶ auth-service ──(내부 API)──▶ user-service
              ├─ POST /users ─────────▶ user-service
              ├─ GET /report-jobs/*/events ──▶ notification-service ◀─ job.status-changed
              ├─ GET /reports/*/dictionary ──▶ dictionary-service   ◀─ report.created
              ├─ /chat, /chat/stt, GET /reports/*/chat ▶ chat-service ◀─ report.created, HTTP ▶ qa, stt
              └─ /** ──────────────────▶ BE (Spring Modulith 모놀리스)
                                          ├─ report, generation, marketdata 모듈
                                          ├─ HTTP ▶ market-data
                                          └─ Kafka ◀▶ generation-worker ──HTTP▶ knowledge ── Milvus, OpenSearch
```

| 서비스 | 위치 | 언어 | 포트(컨테이너) | 소유 데이터 |
|---|---|---|---|---|
| api-gateway | `services/api-gateway` | Java, Spring Cloud Gateway 2024.0.2 | 8080 (호스트 공개는 이것 하나) | Redis(rate limit) |
| auth-service | `services/auth-service` | Java | 8080 | Redis(refresh token 해시), 볼륨(JWT 서명 키) |
| user-service | `services/user-service` | Java | 8080 | Users 테이블(공용 DB) |
| notification-service | `services/notification-service` | Java | 8080 | 없음(Job별 마지막 상태, 메모리) |
| dictionary-service | `services/dictionary-service` | Java | 8080 | dictionary, dictionary_reports(사본: reportId → userId) |
| chat-service | `services/chat-service` | Java | 8080 | chats, chat_reports(사본: reportId → userId, 본문) |
| BE | `BE/` | Java, Spring Boot 3.4.5, Modulith 1.3.12 | 8080 | reports, report_jobs, report_job_attempt(공용 DB), event_publication |
| knowledge / knowledge-ingest | `services/knowledge` | Python, FastAPI | 8000 | Milvus, OpenSearch |
| generation-worker | `services/generation-worker` | Python | 9100(metrics) | 섹션 체크포인트(SQLite, 볼륨) |
| market-data / qa / stt | `services/{market-data,qa,stt}` | Python, FastAPI | 8000 | 없음 |
| python-common | `services/python-common` | Python 라이브러리 | – | – |

### Kafka 토픽 (모두 3파티션, 각 토픽에 `<topic>.DLT`)

| 토픽 | key | 발행 | 소비 그룹 | 비고 |
|---|---|---|---|---|
| `generation.requested` | jobId | BE generation | `generation-worker` | 생성 입력 전부 + attempt |
| `generation.progressed` / `.completed` / `.failed` | jobId | generation-worker | `generation-tracker`(BE) | 계약: `contracts/*.json` |
| `job.status-changed` | jobId | BE generation | `notification-<uuid>`(인스턴스별, latest) | SSE 전달용, `job.userId` 포함 |
| `report.created` | reportId | BE report | `dictionary`, `chat` | compacted. `ReportCreated`와 `ReportDeleted`가 같은 key로 섞여 온다(`event-type` 헤더로 구분) |
| `knowledge.indexed` | index | knowledge-ingest | (없음) | 1파티션 |

- 토픽은 **발행하는 쪽이 생성**한다(브로커 자동 생성 꺼짐). 소비 실패용 DLT는 소비하는 쪽이 만든다. 단, 5단계 서비스(dictionary, chat)가 쓰는 `report.created.DLT`는 BE가 만들어 둔다.
- 5단계 소비자는 값을 JSON 바이트로 받아 필요한 필드만 읽고 `__TypeId__`는 무시한다. 계약 예시는 `contracts/report.created.v1.json`, `report.deleted.v1.json`, `job.status-changed.v1.json`.
- 헤더 `event-type`, `event-version`(현재 1). 메시지는 JSON(camelCase).
- 모든 소비자는 멱등이어야 한다(최소 한 번 전달). 생성 Job의 상태 전이는 "현재 상태 + attempt 번호"로 판정한다.

## 3. 작업 규칙

- 단계마다 끝에 **docker compose로 실제 흐름을 확인**하고, 실험 결과를 `docs/msa/stageN/experiment-*.txt`로 남긴다(`*.log`는 gitignore 대상이라 `.txt`).
- **새 테스트 파일은 추가하지 않는다.** 기존 테스트만 바뀐 구조에 맞게 최소로 고친다. 예외는 `BE/src/test/.../ModularityTests`(Modulith verify) 하나다. 새 서비스는 빌드(`mvnw verify`)·임포트 확인까지만 한다.
- 단계 기록 문서에는 구조, 작업 중 발견한 문제와 원인, 검증 결과 표, **알려진 공백**을 쓴다. 검증하지 못한 것은 그렇다고 적는다.
- 커밋은 단계(또는 의미 있는 하위 단위)마다 한다. 메시지는 한국어로, 무엇을 왜 바꿨는지와 검증 결과를 적는다.
- 서비스 간 계약을 바꿀 때는 `contracts/*.json`을 먼저 고친다. BE `GenerationMessageContractTest`와 워커 `test_message_contract.py`가 같은 파일을 읽는다.
- 모듈/서비스 경계를 넘는 호출은 공개 API나 이벤트로만 한다. BE 안에서는 `ModularityTests`가 강제한다.
- **배포 상태는 문서에 쓰지 않는다.** README·아키텍처 문서에는 AWS 구성(리소스와 연결 관계)만 그린다. "배포했다/운영 중"이나 "계획만 했다" 같은 상태 서술, 실제 배포를 전제로 한 수치(트래픽·비용·가용성)는 넣지 않는다.

## 4. 확정된 결정

아래는 정해진 사항이다. 다음 단계에서는 이 결정을 따른다.

| # | 단계 | 결정 |
|---|---|---|
| D1 | 5 | **소유권 확인은 이벤트로 받은 사본으로 한다.** 이벤트에 `userId`를 싣고 각 서비스가 자기 데이터로 판단한다. 요청마다 report에 묻는 동기 호출은 두지 않는다. `ReportJobStatusChanged`가 싣는 `ReportJobResponseDto`에 `userId`를 추가한다(`ReportCreated`에는 이미 있다). |
| D2 | 5 | **chat-service는 `ReportCreated.content`로 보고서 본문 사본을 보관한다.** 필드 추가는 하위 호환이므로 `event-version`은 1을 유지한다. |
| D3 | 5 | **삭제는 `ReportDeleted`를 같은 key(reportId)로 `report.created` 토픽에 발행한다**(구현: `report.deleted` 토픽은 없앴다). compaction 후 key별 마지막 이벤트가 삭제로 남아 재생 시 삭제 상태가 유지된다. Modulith Outbox를 그대로 쓴다(null tombstone은 쓰지 않는다). `report.created` 소비자는 `event-type` 헤더로 생성/삭제를 구분해 처리한다. 기존 `report.deleted` 토픽은 다른 소비자를 위해 유지할지 정리할지 구현 시 판단한다. |
| D4 | 5 | **5단계는 공용 PostgreSQL을 계속 쓴다.** 테이블 소유만 서비스별로 나눈다. 물리 분리는 6단계에서 한다. |
| D5 | 6 | **생성 완료 → 보고서 저장은 명령 토픽 `report.save-requested`로 비동기 처리한다(Saga, 오케스트레이션).** generation-service가 발행하고 report-service가 저장한 뒤 `report.created`(generationJobId 포함)를 발행하면, generation-service가 Job을 SUCCEEDED로 바꾼다. 저장은 `generationJobId` unique로 멱등이다. |
| D6 | 6 | **같은 PostgreSQL 인스턴스 안에 서비스별 database를 둔다**(user_db, report_db, generation_db, chat_db, dictionary_db). 스키마는 지금처럼 `ddl-auto`에 맡기고, 기존 데이터 이전은 일회성 SQL 스크립트로 한다(Flyway는 도입하지 않는다). |
| D7 | 6 | **BE가 사라지면 Spring Modulith와 `ModularityTests`도 제거한다.** 각 Java 서비스는 Outbox가 필요하면 Modulith 이벤트 레지스트리(JDBC)만 쓴다. |
| D8 | 7 | **Terraform은 `validate`·`plan`까지만 실행한다(`apply` 하지 않음).** 문서 표기는 §3 규칙을 따른다. |
| D9 | 7 | **비밀 값과 JWT 서명 키(JWK)는 Secrets Manager에 두고 환경 변수로 주입한다.** auth-service는 `JWT_KEY_FILE` 대신 JWK 문자열을 받는 경로를 추가한다. |
| D10 | 7 | **서비스 간 인증은 공유 비밀(`X-Internal-Token`)을 유지한다.** mTLS는 알려진 공백으로 문서에 남긴다. |
| D11 | 6 | **이월 공백 중 두 가지를 함께 처리한다.** (1) `ask_llm`이 OpenAI 오류를 예외로 올리게 바꿔 실패한 생성이 재시도되게 한다. (2) Kafka 메시지에서 Spring `__TypeId__` 헤더를 없앤다. |

## 5. 남은 단계

### 5단계 — 완료

[stage5/README.md](stage5/README.md) 참고. 6단계가 이어받을 것:
- dictionary·chat-service의 보고서 사본은 `report.created`로 만든다. 6단계에서 report-service가 발행자가 되어도 토픽·key·헤더(`event-type`)·필드는 그대로 유지한다.
- `scripts/migrate/stage5_report_copies.sql`은 공용 DB에서만 동작한다. 서비스별 DB로 나누기 전에 실행한다.
- `ReportJobResponseDto.userId`는 notification-service가 필터링에 쓴다. generation-service로 옮길 때 빼지 않는다.

### 6단계 — report, generation 분리와 서비스별 DB

- BE에 남는 report·generation(+ marketdata 프록시) 모듈을 report-service, generation-service로 옮긴다. marketdata 프록시는 Gateway가 market-data 서비스로 직접 라우팅하도록 바꾸고 BE 쪽 코드는 없앤다(Redis 캐시가 필요하면 market-data 서비스로 옮긴다). BE 디렉터리는 사라진다.
- **생성 완료 흐름(D5).** generation-service가 `generation.completed`를 받으면 `report.save-requested`(jobId, userId, 보고서 입력, 본문, 용어)를 발행한다. report-service가 저장 후 `report.created`를 발행하고, generation-service가 그것을 받아 Job을 SUCCEEDED로 바꾼다. 새 토픽과 메시지는 `contracts/`에 먼저 추가한다.
- **서비스별 database(D6).** user_db, report_db, generation_db, chat_db, dictionary_db. 공용 DB에서 옮기는 일회성 SQL 스크립트를 `scripts/`에 두고 순서(쓰기 중지 → 복사 → 전환)를 문서에 남긴다. `ModuleBoundaryMigration`은 이 시점에 제거한다.
- 각 Java 서비스가 필요하면 자기 `event_publication`(Modulith JDBC 레지스트리)을 가진다. Modulith 모듈 검증과 `ModularityTests`는 제거한다(D7).
- Gateway 라우트를 서비스별로 나누고 catch-all(`/** → BE`)을 없앤다.
- 3단계 공백 중 "토픽 간 순서"와 "취소된 Job"은 generation-service로 옮기면서 다룬다.

### 7단계 — 인프라

- `infra/envs/prod/main.tf`는 아직 `be`, `rag-server` 두 ECS 서비스 기준이다. 서비스별 ECS 서비스(`modules/ecs-service` 재사용), ALB → api-gateway만 노출, 나머지는 Service Connect로 연결한다.
- Kafka: EC2 단일 KRaft 브로커 모듈(`modules/milvus-ec2` 패턴 재사용). 환경 변수 `KAFKA_BOOTSTRAP_SERVERS`를 모든 소비·발행 서비스에 주입한다.
- 비밀(D9): `INTERNAL_GATEWAY_TOKEN`, OpenAI 키, DB 비밀번호, auth-service JWK를 Secrets Manager로 관리하고 ECS 태스크 정의의 `secrets`로 주입한다.
- 서비스 간 인증은 공유 비밀 유지(D10).
- 제거: `RAG_SERVER_URL` 등 rag-server 시절 설정.
- 모니터링: consumer lag(Kafka exporter + Prometheus), worker 지표(`worker_jobs_total`, `worker_rebalances_total`), DLT 적재량(`kafka.consumer.dead_lettered`).
- 검증은 `terraform fmt -check`, `terraform validate`, `terraform plan`(자격 증명이 있을 때)까지 한다. `apply`는 하지 않는다(D8).
- `infra/README.md`와 루트 `README.md`의 아키텍처 그림·구성 설명을 새 구조로 고친다. 배포 상태 서술은 넣지 않는다(§3 마지막 규칙).
- CI(`.github/workflows/deploy.yml`)의 이미지 매트릭스는 이미 새 서비스를 포함한다.

## 6. 이월된 공백 (단계 기록에서 모음)

| 출처 | 내용 | 다룰 단계 |
|---|---|---|
| 2 | 메시지에 Spring `__TypeId__` 헤더(Java 클래스명)가 붙음(5단계 소비자는 무시) | 6 (D11) |
| 2 | compose의 Kafka에 볼륨이 없어 `down` 시 데이터 소실 | 필요 시 |
| 3 | `ask_llm`이 OpenAI 오류를 예외 대신 문자열로 반환 → LLM 장애 중 오류 문구가 담긴 보고서가 성공으로 저장될 수 있음 | 6 (D11) |
| 3 | 진행/완료/실패가 서로 다른 토픽이라 토픽 간 순서 비보장(실패가 STARTED보다 먼저 오면 lease 만료까지 대기) | 6 |
| 3 | 워커는 취소된 Job을 모르고 끝까지 생성함 | 6 |
| 3 | 뉴스 크롤러가 현재 네이버 HTML과 맞지 않음 | 아무 때나 |
| 4 | 로그아웃 후에도 access token은 만료(15분)까지 유효 | 필요 시(jti denylist) |
| 4 | Gateway와 auth-service가 동시에 재시작되면 JWKS를 받지 못해 모든 토큰 거부(미검증) | 7 |
| 4 | refresh token 재사용 감지 시 토큰 패밀리 폐기 없음 | 필요 시 |
| 4 | 서비스 간 인증이 공유 비밀(`X-Internal-Token`) 수준 | 7(mTLS 등) |
| 5 | 보고서 사본은 최종 일관성(저장 직후 10~70ms 동안 사전·채팅 404 가능, 재시도 없음) | 필요 시 |
| 5 | SSE 구독은 없는/남의 Job이어도 열림(정보는 안 새지만 연결이 남음) | 6(generation-service가 Job 소유자 사본 제공 등) |
| 5 | qa의 400을 chat-service가 500으로 응답(기존 동작) | 아무 때나 |
| 5 | 새 Java 소비자에 계약 테스트 없음 | 필요 시 |

## 7. 검증 환경 메모

- **LLM 없이 전체 파이프라인 돌리기.** `scripts/verify/openai_stub.py`는 OpenAI 호환 스텁이다(chat.completions, audio.transcriptions). 워커·qa·stt는 `OPENAI_BASE_URL`을 따르므로 이렇게 띄운다.
  ```
  python scripts/verify/openai_stub.py            # :18001, STUB_DELAY_SECONDS로 호출당 지연
  OPENAI_API_KEY=stub OPENAI_BASE_URL=http://host.docker.internal:18001/v1 \
    docker compose -p myanalyst-verify -f docker-compose.yml -f scripts/verify/compose.verify.yml up -d --build
  ```
  `STUB_FAIL_FILE`이 가리키는 파일이 있으면 500을 돌려준다. 다만 `ask_llm`이 오류를 삼키므로 재시도 실험에는 knowledge 중단이 더 적합하다(3단계 E3).
- **검색 데이터.** Milvus는 비어 있으면 검색 결과가 0건이다(파이프라인은 그래도 동작). 샘플을 넣으려면:
  ```
  docker compose run --rm knowledge-ingest python ingest.py rebuild-milvus --create-dummy news_embeddings 40
  docker compose run --rm knowledge-ingest          # BM25 색인 + knowledge.indexed 발행
  ```
- **RAG 스택 없이 보고서 만들기(5단계).** `scripts/verify/stage5_flow.py`가 워커 대신 `generation.progressed/completed`를 브로커에 넣는다. `flow`(소유권·SSE·삭제), `bulk N D`(보고서 N개 생성, D개 삭제), `replay`(chat 사본 재생). 띄울 서비스: `postgres redis kafka be api-gateway auth-service user-service notification-service dictionary-service chat-service qa stt`.
- **긴 작업 비교 실험.** `scripts/verify/naive_consumer.py`는 poll 루프 안에서 동기 처리하는 기준 소비자다(3단계 E4a). 워커 이미지 안에서 실행한다.
- compose 프로젝트 이름을 단계별로 따로 쓰면(`-p myanalyst-sN`) 볼륨이 분리된다. 끝나면 `down -v`로 정리한다. `container_name`이 고정이라 두 프로젝트를 동시에 띄울 수는 없다.
- MinIO는 Docker Hub 이미지가 사라져 Chainguard 이미지를 digest로 고정해 쓴다(root로 실행).
- Windows Git Bash에서 `docker exec ... /opt/...`는 경로가 변환되므로 `MSYS_NO_PATHCONV=1`을 붙인다. 이때 다른 인자의 `/c/...` 경로도 변환되지 않으니 섞어 쓰지 않는다.
- 한국어가 들어간 문자열을 셸 heredoc으로 Python에 넘기면 인코딩이 깨질 수 있다. 편집 스크립트는 파일로 작성해 실행한다.
- 테스트: BE `cd BE && ./mvnw clean test`(Docker 필요, Testcontainers). Python은 서비스 디렉터리마다 `python -m unittest discover -s tests`. knowledge는 torch·pymilvus가 필요해 자기 이미지 안에서 돌린다: `docker run --rm -w /app myanalyst/knowledge:local python -m unittest discover -s tests`.
