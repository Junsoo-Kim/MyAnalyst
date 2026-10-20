# MSA 4단계 — API Gateway와 인증 분리 (세션 → JWT)

작업일: 2026-10-20 · 대상: `services/api-gateway`, `services/auth-service`, `services/user-service`, `BE/`(auth 모듈 축소, user 모듈 제거), `FE/src/api/client.js`, `docker-compose.yml`, CI

## 1. 구조

```
브라우저 ──▶ api-gateway :8080 (유일한 공개 포트)
              │  JWT 검증(RS256, JWKS 공개키 캐시) · X-User-Id 재작성 · CORS · 로그인 rate limit(Redis)
              ├─ POST /sessions, DELETE /sessions, POST /auth/refresh ──▶ auth-service ──(내부 API)──▶ user-service
              ├─ POST /users ─────────────────────────────────────────▶ user-service (Users 테이블 소유)
              └─ 그 밖의 모든 경로 ───────────────────────────────────▶ BE (모놀리스, 5·6단계에서 더 나눔)
```

| 서비스 | 책임 | 상태 저장 |
|---|---|---|
| api-gateway (Spring Cloud Gateway 2024.0.2) | 라우팅, access token 검증, 신원 헤더 전파, CORS, 로그인 rate limit, upstream 장애 시 503 | Redis(rate limit 버킷) |
| auth-service | 로그인(자격 증명은 user-service에 확인), access JWT 발급, refresh token 교체, 로그아웃, JWKS | Redis(refresh token 해시), 볼륨(서명 키) |
| user-service | 가입, 자격 증명 확인 내부 API(`/internal/credentials/verify`), 평문 비밀번호 BCrypt 이전 | Users 테이블 |

- BE의 user 모듈은 user-service로 **그대로 옮겼다**(`git mv`라 이력이 이어진다). BE의 auth 모듈은 "Gateway가 넘겨준 사용자 ID를 읽는" 역할만 남았다.
- 계획과 다른 점이 있다. auth-service에 자격 증명 DB(auth_db)를 따로 두지 않았다. 비밀번호 해시는 user-service에만 있고, auth는 확인 결과(누구인지)만 받는다. 해시를 두 곳에 두면 동기화 문제가 생기기 때문이다.

### 토큰 설계

| | access token | refresh token |
|---|---|---|
| 형태 | JWT, RS256, `iss=myanalyst-auth`, `sub=userId`, `jti` | 무작위 32바이트 |
| 수명 | 15분 | 14일 |
| 서버 저장 | 없음(Gateway가 서명·만료·발급자만 검증) | Redis에 **SHA-256 해시**만 저장 |
| 사용 후 | – | 즉시 폐기하고 새로 발급(rotation). 쓴 토큰이 다시 오면 401 |
| 전달 | HttpOnly·SameSite=Lax 쿠키(`Path=/`) 또는 `Authorization: Bearer` | HttpOnly·SameSite=Lax 쿠키(`Path=/auth`, 갱신 요청에만 붙음) |

**쿠키를 고른 이유.** FE의 SSE(`EventSource`)와 차트 이미지(`<img src>`)는 Authorization 헤더를 붙일 수 없다. 그래서 헤더 방식만으로는 진행 상황과 차트가 보이지 않는다. HttpOnly라 스크립트(XSS)로 토큰을 읽을 수 없다. CSRF는 SameSite=Lax와 CORS 허용 목록으로 막는다. 다른 사이트에서 시작한 POST/DELETE에는 쿠키가 붙지 않는다.

**서명 키.** auth-service가 RSA 키(JWK)를 볼륨에 보관하고, 공개키만 JWKS로 내보낸다. Gateway는 요청마다 auth-service를 부르지 않는다. 그래서 auth-service가 내려가도 이미 발급된 토큰은 계속 검증된다.

### Gateway를 거친 요청만 믿기

- Gateway는 클라이언트가 보낸 `X-User-Id`·`X-Internal-Token`을 **무조건 지우고**, 검증된 JWT의 subject로 `X-User-Id`를 다시 넣는다.
- BE·user-service·auth-service는 `X-Internal-Token`(공유 비밀)이 맞지 않으면 403을 돌려준다. 외부에는 Gateway 포트만 열려 있지만, 같은 네트워크 안에서 BE에 직접 붙어 `X-User-Id`를 위조하는 것까지 막기 위해서다. 운영에서는 mTLS 같은 서비스 간 인증으로 바꿀 자리다.
- `/internal/**` 경로는 Gateway에서 `denyAll`이다.

### FE 변경

`api/client.js` 한 곳만 바꿨다. 401을 받으면 `/auth/refresh`를 **한 번만** 호출하고(동시에 여러 요청이 401을 받아도 갱신은 1회) 원래 요청을 다시 보낸다. 로그인·로그아웃·가입 코드는 그대로다. 경로와 응답 형식(`POST /sessions → {"userid"}`)을 세션 시절과 같게 유지했기 때문이다. `npm run build` 통과.

## 2. 작업 중 발견해 고친 문제

1. **재시작으로 IP가 바뀐 뒤 Gateway가 요청을 다른 서비스로 보냈다** ([수정 전 기록](experiment-ip-change-before-fix.txt)).
   auth-service와 user-service를 재시작하자 두 컨테이너의 IP가 서로 바뀌었다. 그런데 Gateway(reactor-netty)가 DNS 응답을 TTL(Docker DNS 600초)만큼 캐시하고 있었다. 그 결과 **로그인 요청이 user-service로 가서 404**가 났다. Gateway가 모든 요청에 내부 토큰을 붙이므로 user-service의 토큰 검사로도 막을 수 없었다. 실패보다 위험한 "오배송"이다.
   → 리졸버 캐시 상한을 5초로 두었다. 수정 후에는 IP를 강제로 바꿔도(user-service가 auth의 예전 IP를 받음) 정상 라우팅된다 ([수정 후 기록](experiment-ip-change-routing.txt)).
2. **내려간 서비스로 가는 요청이 30초 매달린 뒤 500이 났다.** 연결 타임아웃을 2초로 줄이고, 연결 실패는 503으로 응답한다.
3. **JWT 만료가 60초 늦게 적용됐다.** Spring의 기본 검증기가 시계 오차를 60초 허용해서, 20초짜리 토큰이 22초 뒤에도 통과했다. 같은 네트워크 안 서비스끼리라 5초로 줄였다.
4. **(기존 버그) 다른 사용자의 Job을 조회하면 404가 아니라 500이 났다.** `/report-jobs` 컨트롤러가 `ApiException`을 처리하지 않았다. 세션 시절부터 있던 문제다. 공용 `@RestControllerAdvice`를 추가했다.

## 3. 검증 (docker compose: Gateway·auth·user·BE·PostgreSQL·Redis·Kafka)

| 실험 | 결과 | 로그 |
|---|---|---|
| E1 전체 흐름 | Gateway로 가입·로그인 → `Set-Cookie`: access(HttpOnly, SameSite=Lax, Path=/), refresh(HttpOnly, SameSite=Lax, Path=/auth). 쿠키로도, Bearer 헤더로도 API 200. Job 생성 202, **SSE가 Gateway를 거쳐** QUEUED → CANCELLED 수신. Users 테이블은 user-service가 BCrypt 해시로 저장 | [gateway-flow](experiment-gateway-flow.txt) |
| E2 토큰 위조 | 토큰 없음 401(**401에도 CORS 헤더**). payload 변조(sub 바꿔치기) 401, 다른 키·HS256 위조 401, `alg=none` 401 | [token-and-spoofing](experiment-token-and-spoofing.txt) |
| E3 신원 헤더 위조 | bob이 `X-User-Id: alice`를 붙여 alice의 Job 조회 → 404(헤더 무시됨). alice 본인 200. 토큰 없이 헤더만 → 401 | 같은 파일 |
| E4 Gateway 우회 | 같은 네트워크에서 BE에 `X-User-Id`만 붙여 직접 호출 → 403. 틀린 내부 토큰 403. user-service 내부 API 직접 호출 403. Gateway 경유 `/internal/**` 403. BE 포트는 호스트에 노출 안 됨 | 같은 파일 |
| E5 만료와 갱신 | 만료된 토큰 401 → `/auth/refresh` 200 → 새 토큰 200. **이미 쓴 refresh token 재사용 401** | [lifecycle-outage-ratelimit](experiment-token-lifecycle-outage-ratelimit.txt) |
| E6 **auth·user 중단** | 이미 로그인한 사용자: 조회 200, Job 생성 202. 새 로그인·가입만 503. user만 복구되면 가입 201. auth 재시작 후에도 **재시작 전에 발급된 토큰 200**(키를 볼륨에서 다시 읽음) | 같은 파일 |
| E7 로그인 rate limit | 틀린 비밀번호 10연속: 401×5 → 429×5. `X-RateLimit-*` 헤더 | 같은 파일 |
| E8 로그아웃 | 204, 쿠키 삭제, 쿠키로 조회 401. 로그아웃 전 access token을 직접 붙이면 만료 전까지 200(아래 한계) | 같은 파일 |
| E9 IP 변경 후 라우팅 | user-service가 auth-service의 이전 IP를 받은 상태에서 로그인·가입 모두 정상 | [ip-change-routing](experiment-ip-change-routing.txt) |

### 테스트

BE `./mvnw clean test` 15개 통과. 바뀐 것은 `ReportJobServiceTest`(UserService 목 제거)와 `ReportJobConcurrencyIT`(사용자 행 생성 제거)다. `ModularityTests`는 user 모듈이 빠진 구조로 통과한다. 새 Java 서비스 셋은 빌드만 확인했고(`mvnw verify`, CI에 추가), 새 테스트는 추가하지 않았다.

## 4. 알려진 공백

- **로그아웃해도 access token은 만료(최대 15분)까지 유효하다.** 서버에 저장하지 않는 토큰의 대가다. 즉시 차단이 필요하면 `jti` denylist를 Gateway가 Redis에서 확인하게 할 수 있다. 다만 그러면 Gateway가 Redis 장애에 묶인다.
- **Gateway가 재시작되는 동안 auth-service도 내려가 있으면** JWKS를 받지 못해 모든 토큰이 거부된다. JWKS 캐시가 메모리에만 있기 때문이다(검증하지 않음, 구조상 예상되는 동작). 공개키를 설정으로도 주입하는 방법이 있다.
- 공유 비밀(`X-Internal-Token`)은 네트워크 격리를 보완하는 장치일 뿐, 서비스 간 인증의 최종 형태는 아니다.
- user-service는 아직 공용 DB의 Users 테이블을 쓴다. 서비스별 DB 분리는 6단계다. `user.deleted` 이벤트는 탈퇴 API가 없어 만들지 않았다.
- `infra/`(Terraform)에는 아직 Gateway·auth·user ECS 서비스가 없다(7단계).
- refresh token 재사용을 감지했을 때 그 사용자의 다른 refresh token까지 폐기하는 "토큰 패밀리" 처리는 하지 않았다. 지금은 재사용된 토큰만 거절한다.
