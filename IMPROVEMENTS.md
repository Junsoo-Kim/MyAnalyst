# MyAnalyst 개선 내역

`개선 계획.md`와 `개선 계획 세부.md`의 P0/P1을 기준으로, 긴 RAG 요청을 HTTP 요청 수명과 분리하고 기본 보안 경계를 추가했다.

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

`ReportJobServiceTest`는 Mockito로 idempotency, outbox 발행/DLQ 전환, lease 만료 후 복구, 정상 dispatch 시 Report가 정확히 한 번만 생성되는지를 검증한다. 동시에 같은 Job을 두 워커가 claim할 때 비관적 락으로 하나만 성공하는지는 실제 PostgreSQL 동시성에 의존하므로 Testcontainers 통합 테스트가 별도로 필요하다(Docker 없는 환경에서는 실행 불가, 아직 작성하지 않음).

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
