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
| 5 | 이벤트 소비 서비스 분리: notification, dictionary, chat | **다음** | – |
| 6 | 핵심 분리: report, generation → BE 모놀리스 소멸, 서비스별 DB | 대기 | – |
| 7 | 인프라: Terraform(ECS 서비스, Kafka EC2, Service Connect), 모니터링 | 대기 | – |

## 2. 현재 구조 (4단계 완료 시점)

```
브라우저 ──▶ api-gateway :8080 ── JWT(RS256) 검증, X-User-Id 재작성, CORS, 로그인 rate limit
              ├─ /sessions, /auth/** ──▶ auth-service ──(내부 API)──▶ user-service
              ├─ POST /users ─────────▶ user-service
              └─ /** ──────────────────▶ BE (Spring Modulith 모놀리스)
                                          ├─ report, generation, dictionary, chat, notification, marketdata 모듈
                                          ├─ HTTP ▶ market-data, qa, stt
                                          └─ Kafka ◀▶ generation-worker ──HTTP▶ knowledge ── Milvus, OpenSearch
```

| 서비스 | 위치 | 언어 | 포트(컨테이너) | 소유 데이터 |
|---|---|---|---|---|
| api-gateway | `services/api-gateway` | Java, Spring Cloud Gateway 2024.0.2 | 8080 (호스트 공개는 이것 하나) | Redis(rate limit) |
| auth-service | `services/auth-service` | Java | 8080 | Redis(refresh token 해시), 볼륨(JWT 서명 키) |
| user-service | `services/user-service` | Java | 8080 | Users 테이블(공용 DB) |
| BE | `BE/` | Java, Spring Boot 3.4.5, Modulith 1.3.12 | 8080 | 나머지 테이블(공용 DB), event_publication |
| knowledge / knowledge-ingest | `services/knowledge` | Python, FastAPI | 8000 | Milvus, OpenSearch |
| generation-worker | `services/generation-worker` | Python | 9100(metrics) | 섹션 체크포인트(SQLite, 볼륨) |
| market-data / qa / stt | `services/{market-data,qa,stt}` | Python, FastAPI | 8000 | 없음 |
| python-common | `services/python-common` | Python 라이브러리 | – | – |

### Kafka 토픽 (모두 3파티션, 각 토픽에 `<topic>.DLT`)

| 토픽 | key | 발행 | 소비 그룹 | 비고 |
|---|---|---|---|---|
| `generation.requested` | jobId | BE generation | `generation-worker` | 생성 입력 전부 + attempt |
| `generation.progressed` / `.completed` / `.failed` | jobId | generation-worker | `generation-tracker`(BE) | 계약: `contracts/*.json` |
| `job.status-changed` | jobId | BE generation | `notification-<uuid>`(인스턴스별) | SSE 전달용 |
| `report.created` | reportId | BE report | `dictionary` | compacted |
| `report.deleted` | reportId | BE report | `dictionary`, `chat` | |
| `knowledge.indexed` | index | knowledge-ingest | (없음) | 1파티션 |

- 토픽은 **발행하는 쪽이 생성**한다(브로커 자동 생성 꺼짐). 소비 실패용 DLT는 소비하는 쪽이 만든다.
- 헤더 `event-type`, `event-version`(현재 1). 메시지는 JSON(camelCase).
- 모든 소비자는 멱등이어야 한다(최소 한 번 전달). 생성 Job의 상태 전이는 "현재 상태 + attempt 번호"로 판정한다.

## 3. 작업 규칙

- 단계마다 끝에 **docker compose로 실제 흐름을 확인**하고, 실험 결과를 `docs/msa/stageN/experiment-*.txt`로 남긴다(`*.log`는 gitignore 대상이라 `.txt`).
- **새 테스트 파일은 추가하지 않는다.** 기존 테스트만 바뀐 구조에 맞게 최소로 고친다. 예외는 `BE/src/test/.../ModularityTests`(Modulith verify) 하나다. 새 서비스는 빌드(`mvnw verify`)·임포트 확인까지만 한다.
- 단계 기록 문서에는 구조, 작업 중 발견한 문제와 원인, 검증 결과 표, **알려진 공백**을 쓴다. 검증하지 못한 것은 그렇다고 적는다.
- 커밋은 단계(또는 의미 있는 하위 단위)마다 한다. 메시지는 한국어로, 무엇을 왜 바꿨는지와 검증 결과를 적는다.
- 서비스 간 계약을 바꿀 때는 `contracts/*.json`을 먼저 고친다. BE `GenerationMessageContractTest`와 워커 `test_message_contract.py`가 같은 파일을 읽는다.
- 모듈/서비스 경계를 넘는 호출은 공개 API나 이벤트로만 한다. BE 안에서는 `ModularityTests`가 강제한다.

## 4. 남은 단계

### 5단계 — notification, dictionary, chat 분리

BE의 해당 모듈을 서비스로 옮긴다. 이미 Kafka로만 연결되어 있으므로 **코드 이동이 중심**이다.

| 새 서비스 | BE에서 옮길 것 | 데이터 | Gateway 경로 |
|---|---|---|---|
| notification-service | `notification` 모듈(SSE emitter, `job.status-changed` 소비) | 없음 | `GET /report-jobs/*/events` |
| dictionary-service | `dictionary` 모듈(`report.created`/`report.deleted` 소비, 조회 API) | Dictionary 테이블 | `GET /reports/*/dictionary` |
| chat-service | `chat` 모듈(qa·stt 호출, 기록 저장, `report.deleted` 소비) | Chats 테이블 + **보고서 본문 사본** | `POST /chat`, `POST /chat/stt`, `GET /reports/*/chat` |

정해야 할 것과 할 일:
- **소유권 확인.** 지금은 세 모듈 모두 `ReportService.assertOwnedBy/getOwnedReportContent`(BE 내부 호출)를 쓴다. 서비스로 나가면 둘 중 하나를 고른다.
  - (권장) 이벤트에 `userId`를 싣고 각 서비스가 자기 사본으로 판단한다. `ReportCreated`에는 이미 `userId`가 있다. `ReportJobStatusChanged`(→ `ReportJobResponseDto`)에는 `userId`가 없어 추가해야 한다.
  - 또는 BE/report-service에 소유권 확인 내부 API를 둔다(동기 의존이 생긴다).
- **chat-service의 보고서 본문.** 질문마다 BE를 부르지 않도록 `report.created`로 본문 사본을 보관한다. 지금 `ReportCreated`에는 본문이 없으므로 `content` 필드를 추가하고(`event-version` 판단 필요), 이벤트 레지스트리 `serialized_event`(TEXT) 크기도 고려한다.
- **재생 실험(이 단계의 핵심 증거).** chat-service DB를 비우고 consumer group offset을 `report.created` 처음으로 되돌려, 사본이 다시 만들어지는지(건수·소요 시간)를 기록한다.
- **2단계 공백 해결.** `report.created`를 처음부터 다시 읽으면 삭제된 보고서도 되살아난다. 삭제를 같은 key의 tombstone(null value)으로 `report.created`에 남기거나, 소비자가 `report.deleted`를 함께 반영하는 방식을 정한다. Modulith `@Externalized`는 null payload를 보낼 수 없으므로 tombstone은 별도 경로가 필요하다.
- notification-service는 인스턴스마다 고유 consumer group(`latest`)을 그대로 유지한다. Gateway의 SSE 경로가 notification으로 가도록 라우트를 BE보다 앞에 둔다.
- 서비스별 내부 토큰 검사(`X-Internal-Token`)와 `X-User-Id` 사용은 user/auth-service와 같은 방식으로 한다.
- 이 단계의 DB는 공용 PostgreSQL을 계속 쓰되, 테이블 소유를 서비스별로 분명히 한다(FK는 1단계에서 이미 제거됨).

### 6단계 — report, generation 분리와 서비스별 DB

- BE에 남는 report·generation 모듈을 report-service, generation-service로 옮긴다. BE 디렉터리는 사라진다(Modulith는 서비스 내부 구조 정리용으로만 남거나 제거).
- **생성 완료 흐름.** 지금은 generation 모듈이 `ReportService.saveGeneratedReport`를 직접 부른다. 서비스로 나가면 Saga로 바꾼다: generation-service가 `generation.completed`를 받으면 report-service에 저장을 요청하고(명령 토픽 또는 내부 API), report-service가 `report.created`(generationJobId 포함)를 발행하면 generation-service가 Job을 SUCCEEDED로 바꾼다. report 저장은 `generationJobId` unique로 이미 멱등이다.
- **서비스별 database**(같은 RDS 인스턴스 안): user_db, report_db, generation_db, chat_db, dictionary_db. 기존 공용 DB에서 옮기는 마이그레이션 스크립트와 순서(쓰기 중지 → 복사 → 전환)를 정한다. `ModuleBoundaryMigration`(BE)은 이 시점에 제거할 수 있다.
- 각 서비스가 자기 `event_publication`(Outbox)을 가진다(Modulith를 쓰는 Java 서비스).
- Gateway 라우트를 서비스별로 나누고 catch-all(`/** → BE`)을 없앤다.

### 7단계 — 인프라

- `infra/envs/prod/main.tf`는 아직 `be`, `rag-server` 두 ECS 서비스 기준이다. 서비스별 ECS 서비스(`modules/ecs-service` 재사용), ALB → api-gateway만 노출, 나머지는 Service Connect로 연결한다.
- Kafka: EC2 단일 KRaft 브로커 모듈(`modules/milvus-ec2` 패턴 재사용). 환경 변수 `KAFKA_BOOTSTRAP_SERVERS`를 모든 소비·발행 서비스에 주입한다.
- 비밀: `INTERNAL_GATEWAY_TOKEN`, OpenAI 키, DB 비밀번호는 Secrets Manager로 관리한다. auth-service 서명 키는 영속 볼륨(EFS) 또는 Secrets Manager에 둔다.
- 제거: `RAG_SERVER_URL` 등 rag-server 시절 설정.
- 모니터링: consumer lag(Kafka exporter + Prometheus), worker 지표(`worker_jobs_total`, `worker_rebalances_total`), DLT 적재량(`kafka.consumer.dead_lettered`).
- CI(`.github/workflows/deploy.yml`)의 이미지 매트릭스는 이미 새 서비스를 포함한다. ECS 서비스가 생기면 배포 단계가 동작한다.

## 5. 이월된 공백 (단계 기록에서 모음)

| 출처 | 내용 | 다룰 단계 |
|---|---|---|
| 2 | `report.created` 재생 시 삭제된 보고서가 되살아남(tombstone 없음) | 5 |
| 2 | 메시지에 Spring `__TypeId__` 헤더(Java 클래스명)가 붙음. 소비자는 의존하지 않지만 언어 중립 계약을 위해 제거 검토 | 5~6 |
| 2 | compose의 Kafka에 볼륨이 없어 `down` 시 데이터 소실 | 필요 시 |
| 3 | `ask_llm`이 OpenAI 오류를 예외 대신 문자열로 반환 → LLM 장애 중 오류 문구가 담긴 보고서가 성공으로 저장될 수 있음 | 아무 때나 |
| 3 | 진행/완료/실패가 서로 다른 토픽이라 토픽 간 순서 비보장(실패가 STARTED보다 먼저 오면 lease 만료까지 대기) | 6 |
| 3 | 워커는 취소된 Job을 모르고 끝까지 생성함 | 6 |
| 3 | 뉴스 크롤러가 현재 네이버 HTML과 맞지 않음 | 아무 때나 |
| 4 | 로그아웃 후에도 access token은 만료(15분)까지 유효 | 필요 시(jti denylist) |
| 4 | Gateway와 auth-service가 동시에 재시작되면 JWKS를 받지 못해 모든 토큰 거부(미검증) | 7 |
| 4 | refresh token 재사용 감지 시 토큰 패밀리 폐기 없음 | 필요 시 |
| 4 | 서비스 간 인증이 공유 비밀(`X-Internal-Token`) 수준 | 7(mTLS 등) |

## 6. 검증 환경 메모

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
- **긴 작업 비교 실험.** `scripts/verify/naive_consumer.py`는 poll 루프 안에서 동기 처리하는 기준 소비자다(3단계 E4a). 워커 이미지 안에서 실행한다.
- compose 프로젝트 이름을 단계별로 따로 쓰면(`-p myanalyst-sN`) 볼륨이 분리된다. 끝나면 `down -v`로 정리한다. `container_name`이 고정이라 두 프로젝트를 동시에 띄울 수는 없다.
- MinIO는 Docker Hub 이미지가 사라져 Chainguard 이미지를 digest로 고정해 쓴다(root로 실행).
- Windows Git Bash에서 `docker exec ... /opt/...`는 경로가 변환되므로 `MSYS_NO_PATHCONV=1`을 붙인다. 이때 다른 인자의 `/c/...` 경로도 변환되지 않으니 섞어 쓰지 않는다.
- 한국어가 들어간 문자열을 셸 heredoc으로 Python에 넘기면 인코딩이 깨질 수 있다. 편집 스크립트는 파일로 작성해 실행한다.
- 테스트: BE `cd BE && ./mvnw clean test`(Docker 필요, Testcontainers). Python은 서비스 디렉터리마다 `python -m unittest discover -s tests`. knowledge는 torch·pymilvus가 필요해 자기 이미지 안에서 돌린다: `docker run --rm -w /app myanalyst/knowledge:local python -m unittest discover -s tests`.
