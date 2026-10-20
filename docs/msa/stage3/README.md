# MSA 3단계 — rag_server 분리, 보고서 생성을 Kafka 워커로

작업일: 2026-10-20 · 대상: `rag_server/` → `services/`, `BE/`(generation·chat·marketdata 모듈), `contracts/`, `docker-compose.yml`, CI

## 1. 무엇이 바뀌었나

`rag_server` 하나에 있던 기능을 자원 특성과 소유 데이터에 따라 나눴다.

| 서비스 | 하는 일 | 소유 데이터 / 의존 | 이미지 |
|---|---|---|---|
| `services/python-common` | 관측성(trace id, Prometheus), OpenAI 클라이언트, FastAPI 공통 설정 | – (라이브러리) | – |
| `knowledge` (API) | 하이브리드 검색 `/search` (KLUE-BERT 임베딩 + Milvus + OpenSearch BM25 + RRF) | **Milvus, OpenSearch** (읽기) | torch 포함 |
| `knowledge-ingest` (배치) | BM25 색인, Milvus 재구축 도구 → `knowledge.indexed` 발행 | Milvus, OpenSearch (쓰기) | knowledge와 같은 이미지 |
| `generation-worker` | `generation.requested` 소비 → LangGraph 파이프라인 → 진행/완료/실패 이벤트 | 섹션 체크포인트(SQLite) | torch 없음 |
| `market-data` | 뉴스·주가·차트·용어 사전 크롤링 | – | 경량 |
| `qa` | 보고서 본문 기반 질의응답 | – | 경량 |
| `stt` | 음성 → 텍스트 | – | 경량 |

- 계획 대비 변경: `/questions`(보고서 Q&A)를 STT와 묶지 않고 `qa`로 따로 뺐다. 음성 질문은 BE 채팅 모듈이 `stt → qa`를 순서대로 부른다.
- **검색과 색인은 같은 코드베이스, 다른 실행 단위**다. 둘 다 같은 저장소를 쓰므로 서비스로 쪼개면 공유 DB가 된다. 검색 API는 이제 색인을 만들지 않는다(이전에는 첫 검색 때 색인이 비어 있으면 API가 직접 색인했다).
- 워커에는 임베딩 모델·Milvus 클라이언트가 없다. 검색은 knowledge에 HTTP로 위임한다. 그래서 워커 이미지에는 torch가 들어가지 않는다.

### 보고서 생성 흐름

```
BE: Job 저장 + generation.requested(attempt=N, 생성 입력 전부)  ─ 같은 트랜잭션(Outbox)
          │ Kafka
          ▼
generation-worker ── generation.progressed (STARTED, SECTION_2…, SUMMARY, TERMS)
                  ── generation.completed (report, terms)  또는  generation.failed (error)
          │ Kafka
          ▼
BE(generation-tracker): STARTED → RUNNING + lease / 진행 → 진행률·lease 연장 /
                        completed → 보고서 저장(멱등) → SUCCEEDED / failed → RETRYING → 백오프 후 재발행
```

- **BE는 워커의 상태를 모른다.** 워커가 내려가 있으면 요청은 Kafka에 남고 Job은 `QUEUED`로 기다린다.
- 진행 이벤트가 lease를 늘리는 heartbeat 역할을 한다. lease(300초) 안에 아무 이벤트도 없으면 워커가 죽은 것으로 보고 재시도한다.
- 모든 상태 전이는 "현재 상태 + 시도 번호"를 확인한 뒤에만 일어난다. 그래서 재전달·중복 워커·오래된 시도의 이벤트가 와도 무시된다.
- SSE로 섹션 단위 진행률이 보인다(이전에는 10% → 100%로 한 번에 바뀌었다).

### 메시지 계약

`contracts/*.json`에 토픽별 예시 메시지(v1)를 둔다. BE의 `GenerationMessageContractTest`와 워커의 `test_message_contract.py`가 **같은 파일**을 읽는다. 그래서 어느 쪽이든 필드 이름을 바꾸면 둘 중 하나가 깨진다. 이 테스트는 기존 `test_openapi_contract.py`(FastAPI `/reports` 스키마 검증)와 `RagReportClientContractTest`(HTTP 요청의 `evaluations` 필드 검증)를 메시지 기준으로 옮긴 것이다.

### 긴 작업과 Kafka

보고서 하나는 수 분이 걸린다. 처리하는 동안 `poll()`을 멈추면 `max.poll.interval.ms`를 넘겨 그룹에서 쫓겨난다. 그러면 offset 커밋이 실패하고 같은 메시지가 다시 전달된다. 워커는 다음과 같이 이를 피한다.
1. 메시지를 받으면 할당된 파티션을 `pause`한다.
2. 생성은 별도 스레드에서 돌리고, 메인 루프는 계속 `poll()`해 그룹 멤버십을 유지한다.
3. 결과 이벤트가 브로커에 기록된 것을 확인(`flush`)한 뒤 커밋하고 `resume`한다.

처리 중에 리밸런스로 새 파티션이 배정되면 그 파티션도 바로 멈춘다. 처리 중 파티션을 뺏겼다면 커밋하지 않는다. 그러면 새 주인이 같은 메시지를 처리하고, BE가 시도 번호로 중복을 걸러낸다.

## 2. 작업 중 발견해 고친 문제

1. **MinIO 이미지가 Docker Hub에서 사라져 Milvus 스택이 뜨지 않았다.** `minio/minio`를 pull하면 "repository does not exist"가 난다. Chainguard 빌드로 바꾸고 digest로 고정했다. 이 이미지는 비루트(65532)로 돌아 named volume에 쓰지 못해(`file access denied`) 로컬 compose에서는 root로 실행한다. 이번 변경 이전부터 깨져 있던 상태다.
2. **샘플 데이터 도구가 인덱스를 만들지 못했다(`nlist out of range`).** IMPROVEMENTS.md에 "범위 밖의 버그"로 남아 있던 문제다. 원인은 IVF_FLAT **빌드** 파라미터에 **검색** 파라미터인 `nprobe`를 넣어 `nlist`가 비어 있던 것이다. `nlist: 128`로 고쳤다.
3. **방금 넣은 Milvus 데이터가 BM25 색인에서 빠졌다.** `num_entities`는 flush된 세그먼트만 세기 때문에, 삽입 직후 0으로 보여 `limit=0` 질의가 실패했다. 색인 전에 flush하도록 고쳤다. 플러시 안 된 컬렉션은 조용히 색인되지 않던 문제다.
4. **`knowledge.indexed`가 발행되지 않았다.** 브로커 자동 생성을 꺼 두었고 토픽을 만드는 주체가 없었다. 발행자인 ingest가 만들도록 했다. 전달 실패도 이제 조용히 넘기지 않고 오류로 낸다.
5. `evaluate_retrieval.py`가 이름 변경 과정에서 모듈을 None 비교하던 실수를 잡았다(`if embedding is None` → `if query_vector is None`).

## 3. 검증 (docker compose 전체 스택, LLM은 OpenAI 호환 스텁)

OpenAI 키가 없어 `OPENAI_BASE_URL`로 OpenAI 호환 스텁을 붙였다. 그 외에는 모두 실제 구성 요소다(Kafka, PostgreSQL, Redis, Milvus, OpenSearch, KLUE-BERT 임베딩, LangGraph 그래프). 데이터는 샘플 데이터 도구로 Milvus에 40건을 넣고 knowledge-ingest로 BM25 색인을 만들었다. `/search`가 Dense + BM25를 RRF로 합친 결과를 돌려주는 것까지 확인했다.

| 실험 | 결과 | 로그 |
|---|---|---|
| E1 전체 흐름 | Job → 워커(LLM 호출 22회) → SSE로 섹션별 진행률 `10 → 23 → … → 95 → 100` → 보고서·용어 저장(20자 초과 용어 제외). 채팅(qa), 음성 질문(stt → qa), 뉴스(market-data) 동작 | – |
| E2 **워커 중단** | 로그인·조회·채팅 200(수 ms), Job 요청 202(83ms). 30초 동안 `QUEUED`. 요청은 Kafka에 대기(outbox 0, consumer lag 1). 워커 재기동 후 8초 만에 **정확히 한 번** 처리(시도 1, 보고서 1, LLM 22회) | [worker-down](experiment-worker-down.txt) |
| E3 knowledge 중단 | 시도 1·2가 `KnowledgeServiceError`로 실패 → `generation.failed` → BE가 백오프 후 `generation.requested` 재발행 → knowledge 복구 뒤 **시도 3 성공** | [knowledge-down-retry](experiment-knowledge-down-retry.txt) |
| E4a 긴 작업 — 순진한 소비자 | `max.poll.interval.ms=10s`, 작업 20초: `MAXPOLL … leaving group` → 커밋 실패(`Unknown member`) → 같은 메시지 **4번 재처리**, 다음 메시지로 영영 못 넘어감 | [naive-consumer](experiment-long-job-naive-consumer.txt) |
| E4b 긴 작업 — 워커 | 같은 설정, 보고서 23초짜리 2건: 각각 **한 번만** 처리(STARTED 1회, 시도 1). 리밸런스는 최초 배정 1회뿐 | [worker](experiment-long-job-worker.txt) |
| E5 처리 중 워커 강제 종료 | 섹션 4 생성 중 `docker kill` → 체크포인트(섹션 2·3) 보존 → 재기동 후 메시지 재전달, **섹션 2·3을 체크포인트에서 복원**하고 4부터 생성. LLM 호출 14회(전체 22회), 보고서 1, 시도 1 | [worker-crash](experiment-worker-crash-checkpoint.txt) |
| E6 워커 2대 | 파티션 3개가 2:1로 나뉨. 보고서 4건이 jobId key에 따라 두 워커에 분산되고 각각 한 번씩 처리 | – |
| 마무리 | 미완료 발행 0, 모든 DLT 비어 있음, `generation-tracker` lag 0, Job 10건 모두 SUCCEEDED | – |

E5에서 재기동 후 완료까지 54초가 걸렸다. 대부분은 Kafka가 죽은 소비자를 그룹에서 빼기까지 기다린 시간(`session.timeout.ms=45s`)이다.

### 테스트

- BE `./mvnw clean test`: 15개 통과. `GenerationMessageContractTest`(2)는 삭제된 HTTP 계약 테스트를 메시지 계약으로 옮긴 것이다. `ReportJobConcurrencyIT`는 이제 "같은 시도의 STARTED가 동시에 10번 와도 시도는 한 번만 시작"을 실제 PostgreSQL로 검증한다.
- Python: python-common 9, generation-worker 10, market-data 6, knowledge 7 + 평가 지표 3. 모두 기존 테스트를 옮기거나 구조에 맞게 고친 것이고, 새로 추가한 테스트 파일은 없다. knowledge는 torch·pymilvus가 있는 자기 이미지 안에서 실행했다.

## 4. 알려진 공백 / 다음 단계로 넘긴 것

- **LLM 호출 실패는 여전히 실패로 드러나지 않는다.** `ask_llm`이 OpenAI 오류를 예외 대신 "OpenAI API 오류가 발생했습니다" 문자열로 돌려준다(기존 동작). 그래서 LLM 장애 중에는 오류 문구가 담긴 보고서가 "성공"으로 저장될 수 있다. 재시도가 실제로 동작하는 것은 검색 서비스 장애처럼 예외가 올라오는 경우다. 파이프라인의 오류 처리를 바꾸는 일이라 이번 범위에서는 건드리지 않았다.
- 진행·완료·실패가 서로 다른 토픽이라 토픽 사이의 순서는 보장되지 않는다. 완료가 STARTED보다 먼저 소비돼도 보고서는 저장되지만, 실패가 STARTED보다 먼저 오면 그 실패는 무시된다. 그래도 lease 만료(300초)로 재시도되므로 결국 정리된다.
- 워커는 취소된 Job을 모른다. 취소 후에도 생성은 끝까지 돌고, 그 결과를 BE가 무시한다.
- 섹션 체크포인트는 워커 볼륨의 SQLite에 있다. 워커 2대가 같은 named volume을 공유하지만, 다른 워커가 이어받는 경우의 재사용은 검증하지 않았다.
- 실제 OpenAI·실제 공시/뉴스 데이터로는 실행하지 않았다(스텁 + 샘플 데이터). 뉴스 크롤러는 현재 네이버 HTML과 맞지 않아 엉뚱한 항목을 돌려준다. 기존 크롤러 문제로, 이번 범위 밖이다.
- `infra/`(Terraform)와 ECS 서비스는 아직 `rag-server` 기준이다. CI의 이미지 빌드 매트릭스는 새 서비스로 바꿨지만, 대응하는 ECS 서비스는 7단계에서 만든다.
