# MyAnalyst 개선 내역

`개선 계획.md`와 `개선 계획 세부.md`의 P0/P1을 기준으로, 긴 RAG 요청을 HTTP 요청 수명과 분리하고 기본 보안 경계를 추가했다.

## 장애 검증표를 실제로 돌리다가 찾은 버그: Idempotency-Key 동시 요청이 500을 냈다 (2026-09-11)

수치측정.md의 "동일 요청 10회 전송 → Job 1개 생성" 시나리오를 살아 있는 서버(로그인 →
`/report-jobs`에 같은 `Idempotency-Key`로 10개 동시 요청)로 직접 쏴봤다. 기대와 달리
**6개가 500, 4개만 202**로 돌아왔다 — Job은 1개만 만들어졌지만 절반 넘게 클라이언트가
원인 모를 에러를 받는 상태였다.

**원인**: `enqueue()`가 "조회해서 없으면 만든다(check-then-act)" 구조였다. 10개 요청이
동시에 `findByUser_UseridAndIdempotencyKey`를 통과(전부 아직 없음)한 뒤 전부 INSERT를
시도하면, DB의 유니크 제약(`uk_report_job_user_idempotency`)이 먼저 커밋된 하나만 통과시키고
나머지는 `DataIntegrityViolationException`을 던진다 — 이 예외를 잡는 코드가 없어 그대로 500이
됐다. Idempotency-Key 기능이 원래 막으려던 바로 그 상황(중복 클릭)에서, 경합에게 진 요청들이
아무 안내 없이 실패한 것이다.

**해결**: INSERT를 `saveAndFlush`로 트랜잭션 안에서 즉시 반영해 제약 위반을 그 자리에서
확인하고, 위반 시 방금 승자가 커밋한 행을 다시 조회해 그 Job을 돌려준다(경합에서 진
요청도 202로 성공한 것처럼 같은 jobId를 받는다). `saveAndFlush`가 실패하면 Hibernate가
그 트랜잭션을 더 못 쓰게 만들므로, 재조회는 `enqueue` 메서드 바깥의 새 트랜잭션에서
한다(`TransactionTemplate`으로 명시적으로 분리).

실제 서버(Docker)에 다시 쏴서 10개 전부 202 + 동일 jobId를 확인했고,
`ReportJobConcurrencyIT`에 회귀 테스트(`tenConcurrentRequestsWithTheSameIdempotencyKeyCreateOnlyOneJob`)를
추가해 실제 PostgreSQL 경합으로 고정했다.

## 빌드 자체가 막혀 있던 문제 (2026-09-11)

작업을 시작하려고 보니 `BE/pom.xml`에 **해소되지 않은 Git 병합 충돌**(`<<<<<<< HEAD` / `=======` / `>>>>>>> 71624a1...`)이 그대로 남아 있었다. 이 상태에서는 `mvn` 명령 자체가 POM을 파싱하지 못해 컴파일도 테스트도 실행할 수 없다 — 이전 검증 기록(`ReportJobServiceTest` 통과 등)은 이 충돌이 생기기 전 상태를 기준으로 남긴 것으로 보인다.

같은 병합의 잔재가 6개 파일에 더 있었다: `MyanalystApplication.java`, `ChatService.java`(2곳), `ReportService.java`(5곳), `application.properties`, `rag_server/utils.py`(3곳). 두 branch가 각각 다른 기능을 추가한 뒤 병합이 완료되지 못한 채 커밋된 것으로 보인다 — 한쪽은 관측성(Micrometer/OTel, `spring-security-crypto` BCrypt)과 `app.rag.*`/`app.report-jobs.*` 설정 분리를, 다른 쪽은 Redis 캐싱(`spring-boot-starter-data-redis`, `RedisCacheConfig`, `@Cacheable`)을 추가했다. 실제 소스에서 `PasswordConfig`(BCrypt)·`RedisCacheConfig`·`ReportJobMetrics`(Micrometer)가 전부 쓰이고 있는 것을 확인하고, 두 기능을 모두 살리는 방향으로 병합했다.

이 과정에서 병합 충돌 자체가 만든 2차 문제도 잡았다:

- `ChatService`/`ReportService`가 쓰던 구 프로퍼티 키(`rag.server.base-url`)를 없애고 신 키(`app.rag.base-url`, 이미 타임아웃까지 설정된 `RagClientConfig.ragWebClient` 빈이 baseUrl을 갖고 있음)로 통일했다. 그런데 `docker-compose.yml`과 `infra/envs/prod/main.tf`는 여전히 옛 환경변수 이름(`RAG_SERVER_BASE_URL`)을 주입하고 있었다 — 코드가 더 이상 읽지 않는 이름이라 실제 배포·로컬 compose 실행 시 BE가 조용히 `http://localhost:8000`(기본값)으로 RAG 서버를 찾게 되는 상태였다. 둘 다 `RAG_SERVER_URL`로 맞췄다.
- `utils.py`의 LLM 호출 3곳에서 관측성 계측(`observability.time_llm_call`)과 공용 클라이언트 팩토리(`get_openai_client()`, `OPENAI_BASE_URL`까지 지원) 중 하나만 남을 뻔한 것을 병합해, 계측과 커스텀 엔드포인트 지원이 함께 동작하게 했다.

병합 정리 뒤 실제로 빌드·테스트가 도는지 확인했다:

```powershell
cd MyAnalyst\BE
.\mvnw.cmd test -Dtest='!*ApplicationTests'   # 11개 통과 (ReportJobServiceTest 9 + ReportServiceContractTest 2)
```

이 환경의 JDK가 25(Mockito 5.14.2/byte-buddy 1.15.11 출시 시점보다 새 버전)라 `ReportJobServiceTest`가 "Mockito cannot mock this class"로 즉시 실패했다 — byte-buddy가 이 JDK를 아직 공식 지원하지 않아서다. `pom.xml`의 surefire 설정에 `-Dnet.bytebuddy.experimental=true`(byte-buddy 공식 문서의 최신 JDK 대응 옵션)를 추가해 해결했다. `MyanalystApplicationTests`는 이 환경에 Docker 데몬이 없어(CLI는 있지만 미기동) 여전히 스킵된다 — Testcontainers가 스킵 처리하는 것을 확인했고, 에러로 잘못 죽지 않는다.

FE는 `node_modules`가 아예 설치돼 있지 않았다(`npm install` 필요). 설치 뒤 `npm run build`는 경고 3건과 함께 정상 빌드된다(`ReportSidebar.js`·`CompanyAnalysis.js`·`ReportView.js`의 미사용 변수/훅 의존성 — 배포 파이프라인이 FE를 빌드하지 않아 지금 당장 막는 문제는 아니지만, `CI=true`로 빌드하면 경고가 에러로 승격되어 실패한다).

`rag_server`는 `requirements.txt`에 없던 `lxml`이 실제로는 `crawling.py` 세 곳에서 파서로 쓰이고 있어 깨끗한 환경에서는 `bs4.exceptions.FeatureNotFound`로 실패했다 — `requirements.txt`에 추가했다. `pymilvus==2.3.1`은 이 환경(Python 3.12, Windows)에서 설치 자체가 안 된다는 것을 재확인했는데, 원인은 이전에 추정했던 marshmallow 충돌이 아니라 **`grpcio`의 이 버전에 Python 3.12용 사전빌드 wheel이 없어 소스 빌드로 넘어가고, 그 빌드가 로컬 MSVC 툴체인에서 실패**하는 것이었다(`pip install --no-build-isolation`로도 재현). Milvus 관련 코드는 이번에도 실행해보지 못했다.

**참고**: `infra/`(Terraform 11개 모듈)는 이미 저장소에 있었다 — 이전 감사에서 "IaC가 전혀 없다"고 적었던 것은 이 파일들이 추가되기 전 상태를 본 것으로 보인다. `terraform validate`를 이 환경에서 다시 돌리지는 못했다(Terraform CLI 미설치). `infra/README.md`에 스스로 남긴 기록에 따르면 AWS 자격증명이 없어 `plan`/`apply`는 실행하지 못했고 `validate`까지만 확인했다고 되어 있으므로, "AWS에 실제로 배포했다"는 표현은 여전히 쓰면 안 된다 — "Terraform으로 인프라를 코드화하고 validate까지 확인했다"가 정확하다.

## 아직 손대지 않은 것

- **"다양한 기업을 분석한다"는 여전히 사실이 아니다.** 핵심 RAG 파이프라인(`config.COLLECTION_NAMES = ["celltrion_embeddings", ...]`, `prompts.py`의 보고서 생성 프롬프트, `rag_report_pipeline.py`·`utils.py`의 `company="셀트리온"` 기본값)은 전부 셀트리온 컬렉션 하나에 고정돼 있다. 회사별 문서를 수집·임베딩하는 파이프라인 자체가 없다는 뜻이라 별도 라운드가 필요하다.
- FE의 ESLint 경고 3파일 — 지금 당장 아무것도 막고 있지 않아 정리하지 않았다.
- SQS로의 실제 전환, k6 부하 테스트, RDS 백업·복원 테스트, ECS Blue/Green — 실제 AWS 계정이 있어야 검증 가능하다.

**정정**: 이전 기록에서 "XSS 자동 테스트가 없다"고 적었는데 틀렸다. `FE/src/utils/sanitizeReportHtml.test.js`가 이미 실행 중이었고(`npx react-scripts test`로 확인, 통과) 이번에 새로 만든 게 아니다 — grep 패턴이 파일 내용과 안 맞아서 놓쳤던 것뿐이다.

## Docker Desktop이 켜진 뒤 진행한 것 (2026-09-11)

이 세션 초반에는 Docker 데몬이 꺼져 있어 아래 항목들이 전부 막혀 있었다. 켠 뒤 실제
`docker compose up`으로 BE·rag-server·Postgres·Redis·Milvus·OpenSearch 전체 스택을
띄워 검증했다.

**또 다른 미해결 병합 충돌.** `docker compose up --build`가 `rag_server/requirements.txt`
13번째 줄의 `<<<<<<< HEAD`에서 바로 실패했다 — pom.xml과 같은 계열의, 이전 세션에서
못 찾은 충돌이었다(그때 conflict-marker 스캔에 `.txt` 확장자를 빼먹었다). `prometheus-client`
(관측성)와 `beautifulsoup4`/`requests`/`python-multipart`/`rank-bm25`/`langgraph`
(크롤링·STT·검색·Corrective RAG) 양쪽 다 실제로 쓰이고 있어 합집합으로 병합했다.

**Testcontainers 완료조건 충족.** `MyanalystApplicationTests`가 이 Docker Desktop
버전(4.85)에서 여전히 스킵됐다 — Spring Boot 3.4.5가 끌어오는 testcontainers-java
1.20.6이 Docker Desktop의 응답을 파싱하지 못했다(`BadRequestException 400`). pom.xml에
`testcontainers.version=1.21.4`를 override하자 별도 설정 없이 해결됐다. "로컬 PostgreSQL
설치 없이 통합 테스트 실행"(P0 완료조건)이 이제 실제로 된다.

**동시 승인(P1) 진짜 동시성 테스트.** `ReportJobConcurrencyIT`를 추가해 실제 PostgreSQL
컨테이너에 10개 스레드가 동시에 같은 Job을 `claimForTest`(테스트 전용으로 package-private
공개한 `claim()` 래퍼)로 주장하게 했다. `findWithLockByJobId`의 `PESSIMISTIC_WRITE`가
정말로 하나만 통과시키는지, `attemptCount`가 정확히 1만 늘어나는지 확인했다 — 기존
`ReportJobServiceTest`는 Mockito라 이 부분(실제 DB 락)은 검증하지 못했었다.

**OpenAPI 기반 계약 테스트(P0).** FastAPI의 `app.openapi()`가 문서화하는 `/reports` 요청·
응답 스키마의 필드 이름이 Spring이 실제로 보내고 기대하는 것과 정확히 일치하는지
확인하는 테스트를 추가했다(`test_openapi_contract.py`). 과거 `evaluation`/`evaluations`
불일치가 재발하면 이 테스트가 바로 잡는다.

**섹션별 checkpoint(P1).** 보고서 생성이 섹션 단위로 진행되는데도 결과는 `generate_full_report`
호출 하나 안의 파이썬 dict에만 있어서, 중간에 죽으면 이미 만든 섹션까지 전부 다시
생성해야 했다. Spring의 `report.getGenerationJobId()`를 `/reports` 요청에 실어 보내고,
rag_server는 `section_checkpoints.py`(SQLite)에 섹션별로 즉시 저장한다. 재시도 시 이미
있는 섹션은 건너뛰고, 전체 완료 후에는 정리한다.

**검색 구조(P2) — BM25를 OpenSearch로 분리.** Worker마다 전체 문서를 메모리에 올리던
`rank_bm25` 인덱스를 없애고, Milvus 컬렉션 텍스트를 OpenSearch(`myanalyst-chunks`
인덱스)에 색인한 뒤 그쪽에서 검색하도록 바꿨다(`hybrid_search.py`). 여러 Worker가 인덱스를
공유하므로 Worker 수만큼 메모리를 중복 쓰지 않고, 신규 문서 반영에 Worker 재시작이
필요 없다(다른 Worker가 이미 색인했으면 재색인하지 않음).

실제로 문서 2건을 Milvus에 넣고 색인·검색까지 돌려보다가 진짜 버그를 하나 잡았다 —
OpenSearch 기본(standard) 분석기는 한국어 조사를 못 뗀다("영업이익은"과 "영업이익"을
다른 토큰으로 봐서 검색이 전혀 안 됐다). KLUE-BERT WordPiece 토크나이저로 색인·질의
양쪽을 미리 토큰화해 `search_tokens` 필드(whitespace 분석기)에 넣는 방식으로 고치고,
같은 질의로 정답 문서가 오답 문서보다 훨씬 높은 점수로 나오는 것을 실제로 확인했다.

**CI에 테스트·취약점 검사 추가(P4).** `deploy.yml`이 checkout 직후 바로 이미지를 빌드해
배포하고 있었다 — 테스트를 돌리는 단계 자체가 없었다. `test` job(BE `mvnw test`, rag_server
유닛 테스트, Trivy 파일시스템 스캔)을 추가하고 `deploy`가 이 job에 의존하게 했다.

**부수적으로 발견한, 이번 범위 밖의 버그**: `rebuild_milvus_collections.py`의 샘플 데이터
생성이 `nlist` 파라미터 오류로 실패한다(코퍼스 크기 대비 부적절한 값). 실제 데이터 삽입
전에 에러가 나서 컬렉션은 만들어지지만 비어 있다 — 이번 세션에서는 손대지 않았다.

테스트는 rag_server 15개 → 30개(`test_hybrid_search.py` 6개, `test_openapi_contract.py`
3개, `test_section_checkpoints.py` 5개 신설), BE는 `ReportJobConcurrencyIT` 1개 추가.

## 현재 요청 흐름

```text
React → POST /report-jobs (202)
      → PostgreSQL report_jobs / report_job_attempt
      → bounded local dispatcher → Spring RAG client → FastAPI /reports
      → PostgreSQL report + dictionary

React ← SSE /report-jobs/{jobId}/events, GET /report-jobs/{jobId}
```

`report_jobs`가 작업 상태의 기준 데이터다. 브라우저 새로고침이나 API 서버 재시작 뒤에도 상태 조회가 가능하며, lease 만료된 `RUNNING` 작업은 다시 처리 대상으로 잡힌다. 개발 환경에서는 PostgreSQL-backed in-process dispatcher를 사용한다. 운영에서 여러 API 인스턴스를 실행할 때는 이 dispatcher를 SQS + DLQ consumer로 교체해야 한다.

`outbox_events`는 Job과 같은 트랜잭션에서 `REPORT_REQUESTED` 이벤트를 저장한다. relay가 이벤트 lease를 획득한 뒤 local dispatcher에 전달하고 `PUBLISHED`로 기록한다. 따라서 Job DB 저장 성공 뒤 프로세스가 종료되어 전달이 누락되는 경우를 복구할 수 있다. 외부 SQS relay로 교체할 때도 이 테이블과 상태 전이 규칙은 유지한다.

전달이 반복적으로 실패하는 이벤트는 `app.report-jobs.outbox-max-attempts`(기본 5회)를 넘기면 `DEAD` 상태로 옮기고 연결된 Job을 `FAILED`로 종료한다. 이전에는 상한 없이 60초 간격으로 재시도가 무한 반복됐다.

생성 결과에는 `generation_job_id` unique key를 기록한다. Worker가 보고서를 저장한 직후 중단되더라도 lease recovery가 기존 결과를 찾아 Job만 완료 처리하므로 같은 Job이 Report를 중복 저장하지 않는다.

## API

인증된 세션에서만 아래 API를 호출할 수 있다.

| API | 설명 |
| --- | --- |
| `POST /report-jobs` | `Idempotency-Key` 헤더와 보고서 입력을 받아 `202 Accepted` 및 job을 반환 |
| `GET /report-jobs/{jobId}` | 현재 작업 상태 조회 |
| `GET /report-jobs/{jobId}/events` | `report-job` SSE 이벤트 구독 |
| `POST /report-jobs/{jobId}/cancel` | 대기·실행 중 작업 취소 |

작업 상태는 `QUEUED → RUNNING → SUCCEEDED`이며, 일시 실패는 지수 백오프로 `RETRYING` 상태를 거친다. 최대 시도 횟수 초과 시 `FAILED`가 된다. 동일 사용자와 동일 `Idempotency-Key` 조합은 기존 작업을 반환한다.

## 보안 및 계약

- 가입 비밀번호를 BCrypt로 저장한다. 기존 평문 개발 계정은 첫 정상 로그인 시 BCrypt로 마이그레이션한다.
- 로그인은 서버 세션을 만들며, 보고서·채팅·사전·작업 API는 세션 사용자와 소유자가 일치해야 접근할 수 있다.
- Spring → FastAPI 보고서 계약의 필드명을 `evaluations`로 통일했다.
- RAG base URL과 connect/response timeout은 `RAG_SERVER_URL`, `app.rag.*` 설정으로 분리했다.
- React API base URL은 `REACT_APP_API_BASE_URL`로 바꿨고, 보고서 HTML은 DOMPurify로 정화한다.
- 주가·차트 조회가 종목코드 `068270`(셀트리온)에 고정돼 있던 문제를 고쳤다. `crawling.resolve_stock_code`가 네이버 증권 자동완성 API(`ac.stock.naver.com/ac`)로 임의 회사명을 종목코드로 변환한다.

## 검증

```powershell
cd MyAnalyst\BE
.\mvnw.cmd test -q

cd ..\FE
cmd.exe /d /c npm run build

cd ..\rag_server
python -m unittest discover -s tests -v
python -m unittest discover -s evaluation\tests -v
```

`ReportJobServiceTest`는 Mockito로 idempotency, outbox 발행/DLQ 전환, lease 만료 후 복구, 정상 dispatch 시 Report가 정확히 한 번만 생성되는지를 검증한다. 동시에 같은 Job을 두 워커가 claim할 때 비관적 락으로 하나만 성공하는지는 `ReportJobConcurrencyIT`(Testcontainers, 실제 PostgreSQL)가 검증한다.

## RAG 평가 실행

`rag_server/evaluation/golden_dataset.example.jsonl`의 `REPLACE_WITH_MILVUS_ID`를 실제 검색 결과의 `collection:id`로 교체해 Golden Dataset을 만든다. 결과 ID는 서로 다른 collection 간 충돌을 막기 위해 항상 이 형식으로 기록한다.

```powershell
cd MyAnalyst\rag_server
python -m unittest discover -s evaluation\tests -v
python -m evaluation.evaluate_retrieval `
  --dataset evaluation\golden_dataset.jsonl `
  --top-k 10 `
  --min-recall-at-k 0.75 `
  --min-mrr 0.60 `
  --output evaluation-report.json
```

Milvus 없이 metric·CI wiring만 검증하려면 `--fixture evaluation\fixtures\retrieval_results.json`을 추가한다. fixture의 수치는 실제 검색 품질 지표가 아니므로 포트폴리오 결과로 사용하지 않는다.

## 다음 우선순위

1. in-process dispatcher를 SQS consumer로 분리한다. outbox 자체의 DLQ(반복 실패 시 `DEAD` 전환)는 완료했다.
2. Golden Dataset 기반 Recall@K, MRR, citation/faithfulness 평가를 CI 품질 게이트로 만든다. `golden_dataset.example.jsonl`은 아직 placeholder ID이며 실제 Milvus 검색 결과로 교체해야 한다.
3. Tempo/Jaeger 같은 분산 추적 백엔드를 붙이고, FastAPI의 trace_id를 Spring 쪽 OpenTelemetry span과 실제로 연결한다.
4. Grafana dashboard로 Spring `/actuator/prometheus`와 FastAPI `/metrics`를 함께 시각화한다.

## 관측성 기반

Spring은 `/actuator/prometheus`에 Job 상태 전이(`report_jobs_transitions_total`)와 실행 시간(`report_job_execution_seconds`)을 노출한다. 모든 HTTP 응답에는 `X-Trace-Id`를 반환하며, 이 값은 Job에 영속화되어 Spring Worker와 FastAPI 호출로 전달된다.

FastAPI는 같은 `X-Trace-Id` 헤더를 구조화 로그에 남기고, `/metrics`에서 Prometheus 포맷으로 지표를 노출한다. `rag_stage_duration_seconds`(파이프라인 단계별 소요시간), `rag_milvus_search_duration_seconds`(collection별 검색 시간), `rag_llm_call_duration_seconds`·`rag_llm_tokens_total`(모델·용도별 LLM 호출 시간과 토큰 사용량)을 `rag_server/observability.py`에서 기록한다. Micrometer OpenTelemetry bridge는 Spring 쪽에만 있고, FastAPI는 아직 OTel SDK가 아니라 Prometheus client 기반이라 두 서비스의 trace가 하나로 연결되지는 않는다. Tempo/Jaeger collector와 Grafana dashboard는 다음 관측성 단계에서 추가한다.
