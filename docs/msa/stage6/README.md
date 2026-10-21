# MSA 6단계: report, generation 분리와 서비스별 DB

작업일: 2026-10-21 · 대상: `BE/` → `services/generation-service`, `services/report-service`, `services/market-data`(캐시), `services/generation-worker`(D11), `services/api-gateway`, `scripts/postgres`, `scripts/migrate`, `contracts/`, `docker-compose.yml`, CI

## 1. 구조

```
브라우저 ──▶ api-gateway :8080 (catch-all 없음, 맞는 라우트가 없으면 404)
              ├─ /sessions, /auth/**, POST /users ─────────▶ auth-service, user-service ── user_db
              ├─ /report-jobs, /report-jobs/** ────────────▶ generation-service ───────── generation_db
              │     (GET /report-jobs/*/events는 notification-service)
              ├─ /reports, /reports/** ────────────────────▶ report-service ───────────── report_db
              │     (/reports/*/dictionary, /reports/*/chat은 dictionary·chat-service) ── dictionary_db, chat_db
              └─ GET /news/*, /stocks/*, /stocks/*/chart-image ▶ market-data ──── Redis(캐시)

generation-service ──generation.requested──▶ generation-worker ──generation.progressed/completed/failed──▶ generation-service
generation-service ──report.save-requested──▶ report-service ──report.created──▶ generation-service, dictionary, chat
```

- `BE/`는 `git mv`로 `services/generation-service`가 됐다(이력 유지). report 모듈과 그 테스트는 `services/report-service`로 다시 옮겼다. marketdata 모듈(market-data 중계 + Redis 캐시)은 지웠고, Gateway가 market-data로 바로 보낸다. 캐시는 market-data(Python)로 옮겼다.
- Spring Modulith의 **모듈 검증과 `ModularityTests`는 없앴다**(D7). 서비스 경계가 이제 프로세스 경계라 검증할 모듈 구조가 없다. Modulith는 두 서비스에서 **이벤트 발행 레지스트리(Outbox)와 Kafka 외부 발행으로만** 쓴다. 각자 자기 DB에 `event_publication`을 가진다.
- `ModuleBoundaryMigration`(1단계의 FK 제거)은 지웠다. 테이블이 이제 서로 다른 database에 있다.

### 보고서 저장 Saga (D5)

전에는 generation 모듈이 완료 이벤트를 받으면 `ReportService.saveGeneratedReport`를 같은 프로세스에서 불렀다. 이제 두 서비스는 DB도 프로세스도 다르므로 명령 토픽으로 잇는다.

```
RUNNING ──generation.completed──▶ SAVING ──report.created(generationJobId)──▶ SUCCEEDED
   │       (같은 트랜잭션: Job 상태 + report.save-requested 발행 기록)
   └─ report-service: 저장(generationJobId unique, 멱등) + ReportCreated 발행 기록 (같은 트랜잭션)
```

- 새 상태 **`SAVING`**: lease와 재시도 대상이 아니다. report-service가 내려가 있으면 명령이 Kafka에 남고 Job은 SAVING으로 기다린다(E3). 이때 취소는 409다. 명령은 이미 나갔으므로, 취소하면 보고서는 저장되는데 Job만 CANCELLED로 남는다.
- 완료 이벤트가 여러 번 와도 명령은 한 번만 나간다. SAVING이면 무시한다. 명령이 여러 번 와도 보고서는 하나다. 이미 저장된 jobId면 아무것도 하지 않는다(E4).
- generation-service는 `report.created`를 그룹 `generation`으로 소비한다. `event-type=ReportCreated`이고 `generationJobId`가 있으면 그 Job을 SUCCEEDED로 바꾼다. 같은 토픽의 ReportDeleted와 Saga 밖에서 만들어진 보고서는 건너뛴다.
- 계약: [contracts/report.save-requested.v1.json](../../../contracts/report.save-requested.v1.json).

### 서비스별 database (D6)

| database | 소유 서비스 | 테이블 |
|---|---|---|
| user_db | user-service | users |
| report_db | report-service | reports, event_publication |
| generation_db | generation-service | report_jobs, report_job_attempt, event_publication |
| chat_db | chat-service | chats, chat_reports |
| dictionary_db | dictionary-service | dictionary, dictionary_reports |

- 같은 PostgreSQL 인스턴스 안의 database다. 새 볼륨이면 `scripts/postgres/init-databases.sql`(`/docker-entrypoint-initdb.d`)이 만든다. 스키마는 각 서비스가 만든다(ddl-auto, Modulith JDBC).
- 기존 공용 DB(`myanalystdb`)에서 옮기는 일회성 스크립트: `scripts/migrate/stage6_split_databases.sh`.
  1. 공용 DB에 쓰는 서비스(be, user, dictionary, chat)를 멈춘다.
  2. 스크립트를 실행한다.
     - 미완료 이벤트 발행이 있으면 중단한다. 서비스마다 `event_publication`이 따로라 옮기지 않기 때문이다.
     - 5단계 정리 SQL을 먼저 돌린다.
     - 서비스별로 `pg_dump -t`로 스키마·데이터·시퀀스를 복사한다. 대상 테이블에 행이 있으면 중단한다.
  3. 새 서비스를 띄운다.
  - 공용 DB는 그대로 둔다(되돌릴 수 있게). 확인이 끝나면 직접 지운다.
- 스크립트는 `report_jobs`의 status CHECK 제약도 지운다. Hibernate가 enum 값 목록으로 CHECK를 만드는데, `ddl-auto=update`는 이 제약을 고치지 않는다. 그래서 그대로 두면 새 값 `SAVING`이 거부된다.

### D11

- **`__TypeId__` 헤더 제거.** 처음에는 `spring.json.add.type.headers=false`(producer 속성)로 껐는데 헤더가 그대로 남았다(E2 첫 실행). Modulith는 producer serializer를 `ByteArraySerializer`로 두고 JSON 변환을 `ByteArrayJsonMessageConverter`에서 한다. 헤더도 그 변환기의 type mapper가 붙인다. 그래서 같은 이름의 빈(Modulith 쪽은 `@ConditionalOnMissingBean`)을 직접 등록했다. 이 빈은 type mapper가 헤더를 쓰지 않고, 소비할 때는 리스너 파라미터 타입으로 변환한다(INFERRED). report-service의 타입 지정 리스너는 헤더 없이도 명령을 받는다(E2).
- **`ask_llm`이 OpenAI 오류를 예외로 올린다.** 전에는 "OpenAI API 오류가 발생했습니다" 같은 문자열을 답변으로 돌려줬다. 그래서 LLM 장애 중에 그 문구가 보고서 본문으로 들어간 채 성공으로 저장될 수 있었다. 이제 예외가 올라가 워커가 `generation.failed`(retryable)를 보낸다. 쿼리 재작성처럼 원래 실패를 흡수하던 호출부는 그대로 기존 키워드로 대체한다.

### market-data 직접 라우팅

- Gateway가 조회 경로(`GET /news/*`, `/stocks/*`, `/stocks/*/chart-image`)만 market-data로 보낸다. market-data는 Python이라 `X-Internal-Token`을 보지 않는다. 그래서 내부용 `POST /dictionaries`는 라우트에 넣지 않았다(Gateway에서 404). JWT 검증은 Gateway에서 그대로 한다.
- BE가 하던 Redis 캐시(뉴스 5분, 시세 1분)를 market-data에 `cache.py`로 옮겼다. Redis가 없거나 장애면 캐시 없이 동작한다.
- 응답이 BE 중계 때와 달라졌다. 오류는 원래 상태 코드(404, 503)와 FastAPI JSON(`{"detail": ...}`)으로 나간다. BE는 모두 500과 평문으로 바꿔 보냈다.

## 2. 작업 중 발견한 문제

1. **`__TypeId__`를 끄는 설정이 듣지 않았다.** 위 D11 참고. 설정 이름만 보고 끄면 안 되고, 실제 메시지 헤더로 확인해야 했다.
2. **Hibernate의 enum CHECK 제약.** 공용 DB에서 복사한 `report_jobs`에 `status IN (...)` CHECK가 있었다. 새 상태를 넣으면 실패하므로 마이그레이션 스크립트에서 지운다(E0 이후 SAVING 저장 정상).
3. **계약 테스트의 상대 경로.** `GenerationMessageContractTest`가 `../contracts`를 읽고 있었다. 서비스가 한 단계 깊어져 `../../contracts`로 고쳤다.

## 3. 검증 (docker compose)

먼저 5단계 이미지로 공용 DB에 데이터를 만들었다. 보고서 25개, Job 32개(그중 1개는 QUEUED로 남김), 채팅 1건, 용어 50개, 사용자 4명이다. 그 뒤 쓰기 서비스를 멈추고 마이그레이션 스크립트를 돌린 다음, 같은 볼륨 위에 6단계 서비스를 올렸다. 워커와 RAG 스택은 5단계와 마찬가지로 `scripts/verify/stage6_flow.py`가 대신했다.

| 실험 | 결과 | 로그 |
|---|---|---|
| E0 DB 분리 | 미완료 이벤트 0 확인. 8개 테이블 행 수가 원본과 같음(users 5, reports 26, report_jobs 33, attempt 32, chats 1, chat_reports 26, dictionary 52, dictionary_reports 26) | [migration](experiment-migration.txt) |
| E1 옮긴 데이터 | 5단계에서 만든 사용자로 로그인 → 보고서 목록·본문·용어·채팅 기록 200. 다른 사용자 403. QUEUED Job 유지. 새 보고서 ID는 복사한 시퀀스에서 이어짐(32 → 33) | 같은 파일 |
| E2 **Saga** | SSE: RUNNING/10 → RUNNING/50 → **SAVING/99** → SUCCEEDED/100. 완료 이벤트 후 40ms 안에 SUCCEEDED. report_db에 1행. **`report.save-requested`, `report.created`, `job.status-changed` 헤더에 `__TypeId__` 없음** | [saga](experiment-saga.txt) |
| E3 **report-service 중단** | 완료 → SAVING에서 대기, `/reports` 503. **SAVING 중 취소 409.** 20초 뒤에도 SAVING, 보고서 0행. report-service 시작 → 6.9초 뒤 SUCCEEDED(컨테이너 기동 포함), 보고서 1행 | 같은 파일 |
| E4 재전달 | 같은 완료 이벤트 3번 → 저장 명령 1개, 보고서 1행. 같은 명령 2번 더 → 보고서 1행, `report.created` 1건, Job SUCCEEDED | 같은 파일 |
| E5 Gateway | 없는 경로·`/swagger-ui.html`·`POST /dictionaries` 404. 토큰 없이 `/stocks/*` 401. 시세 1회차 0.23s → 2회차 0.01s(Redis `market-data:stocks:*`, TTL 60) | [gateway-isolation-d11](experiment-gateway-isolation-d11.txt) |
| E6 DB 격리 | 각 database에는 자기 테이블만 있다(위 표와 같음). `myanalystdb`는 원본 그대로 | 같은 파일 |
| E7 D11 | 스텁이 500을 돌려주면 `ask_llm`이 `InternalServerError`를 올린다(전에는 오류 문구를 반환). 정상일 때는 답변 반환. 워커 이미지 안에서 함수 단위로 확인했다 | 같은 파일 |
| E8 새 볼륨 | init 스크립트가 database 5개를 만들고 각 서비스가 스키마를 만든다. 5단계 흐름(`stage5_flow.py flow`)을 회귀로 다시 돌림: 소유권, 채팅, SSE 필터링, 삭제 모두 같은 결과이고, SSE에 SAVING이 추가됨 | [fresh-and-regression](experiment-fresh-and-regression.txt) |

### 테스트

- generation-service `./mvnw clean test` 13개 통과. BE의 15개에서 `ModularityTests`(D7로 제거)와 report-service로 옮긴 `ReportServiceContractTest`가 빠졌다.
- report-service 1개 통과.
- 고친 테스트:
  - `ReportJobServiceTest`: `ReportService` 목 대신, 완료 시 저장 명령이 한 번만 나가는지와 `report.created` 뒤 SUCCEEDED가 되는지를 본다.
  - `MyanalystApplicationTests`: Redis 컨테이너를 뺐다.
  - `GenerationMessageContractTest`: 계약 파일 경로.
- 새 테스트는 추가하지 않았다.

## 4. 알려진 공백

- **Saga 보상이 없다.** report-service가 저장에 끝까지 실패하면(재시도 3회 뒤 `report.save-requested.DLT`) Job은 SAVING에 머문다. `report.save-failed` 같은 실패 이벤트로 FAILED로 돌리는 단계는 만들지 않았다.
- **D11의 워커 전체 흐름은 확인하지 않았다.** `ask_llm` 예외 → 워커 `generation.failed` → RETRYING은 함수 단위(E7)와 기존 워커 코드(모든 예외를 retryable 실패로 보고)로만 확인했다. RAG 스택을 띄운 실험은 하지 않았다.
- 서비스별 database가 **같은 인스턴스, 같은 계정(postgres)**을 쓴다. 다른 서비스의 database에 접속하는 것을 막는 장치는 없다(계정 분리는 하지 않음). 인스턴스 장애는 모든 서비스에 영향을 준다.
- `myanalystdb`(공용 DB)는 남아 있다. 지우는 것은 운영자 몫이다.
- Swagger UI(`/swagger-ui.html`)는 Gateway를 거쳐서는 열리지 않는다. 각 서비스 포트로만 열린다.
- 3단계에서 넘어온 "진행·완료·실패 토픽 간 순서"와 "워커가 취소된 Job을 모르고 끝까지 생성함"은 다루지 않았다. 둘 다 워커와 generation-service 사이 계약을 바꿔야 한다. 7단계 이후 과제로 남긴다.
- market-data는 Gateway 뒤에서 `X-Internal-Token`을 확인하지 않는다(Python 서비스 공통). 같은 네트워크 안에서는 직접 부를 수 있다.
