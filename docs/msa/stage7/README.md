# MSA 7단계: 인프라 (Terraform, 모니터링)

작업일: 2026-10-21 · 대상: `infra/`(network, alb, ecs-service, kafka-ec2 신규, milvus-ec2, ecs-cluster, observability, envs/prod), `services/auth-service`(D9), `.github/workflows/deploy.yml`, `README.md`

## 1. 구조

`envs/prod`는 BE·rag-server 두 서비스 기준이었다. 6단계 서비스 구성에 맞춰 다시 짰다. 구성도와 사용법은 [infra/README.md](../../../infra/README.md)에 있다.

| 영역 | 바뀐 것 |
|---|---|
| ECS | `services.tf`의 서비스 13개를 `for_each`로 만든다(ECR 리포지토리도 같은 키). 이름은 CI 매트릭스와 같다(`myanalyst-prod-<name>`). 환경 변수 이름은 docker-compose와 같고 주소만 Service Connect DNS다 |
| 노출 | ALB 대상 그룹 `be` → `gateway`. 외부에 열리는 것은 api-gateway 하나. ALB idle timeout은 60초에서 300초로 늘렸다(SSE) |
| 보안그룹 | `be`/`rag` 대신 `gateway`(ALB → 8080)와 `services`(같은 SG끼리 8000/8080/9100)로 바꿨다. 데이터 계층(RDS, Redis, Kafka, 검색 데이터)은 `services` SG에서만 받는다 |
| Kafka | 새 모듈 `kafka-ec2`. EC2 한 대에 단일 KRaft 브로커를 compose와 같은 설정으로 띄운다(자동 토픽 생성 off). SSM 접속 가능 |
| 검색 데이터 | `milvus-ec2`에 OpenSearch를 추가했다(knowledge의 BM25). 인스턴스 기본 사양을 t3.large에서 t3.xlarge로 올렸다 |
| 이름 해석 | EC2 두 대를 Cloud Map(Service Connect와 같은 네임스페이스)에 `kafka.<ns>`, `search-data.<ns>`로 등록한다. Kafka advertised listener도 이 이름이다 |
| DB | RDS 하나에 database 5개(D6). 일회성 ECS 태스크 `database-init`이 `scripts/postgres/init-databases.sql`을 VPC 안에서 실행한다(`terraform output database_init_command`) |
| 비밀(D9) | Secrets Manager 시크릿 `internal-gateway-token`, `jwt-signing-key`를 만들고 태스크 `secrets`로 주입한다. 값은 Terraform 밖에서 넣는다(state에 남지 않게). OpenAI 키는 기존처럼 미리 만든 시크릿의 ARN을 받는다 |
| auth-service(D9) | `JWT_SIGNING_KEY`(JWK JSON)가 있으면 키 파일 대신 그것을 쓴다. 없으면 기존 동작(파일 읽기/생성). 비공개키가 없는 JWK면 기동 실패 |
| 모니터링 | 브로커 호스트의 systemd 타이머(`kafka-metrics.sh`, 1분)가 consumer lag(그룹별)와 DLT 끝 offset(토픽별)을 CloudWatch `MyAnalyst/Kafka`로 올린다. 알람은 다음 세 가지다. 그룹별 lag가 10분 연속 기준 초과, DLT 증가(`DIFF`), Kafka·검색 데이터 EC2 상태 검사 실패 |
| 서비스 간 인증(D10) | 공유 비밀(`X-Internal-Token`) 유지 |

- 롤 권한: GitHub OIDC 배포 역할은 13개 ECR 리포지토리·ECS 서비스와 그 실행/태스크 역할로만 한정한다. Kafka EC2 역할의 `cloudwatch:PutMetricData`는 `MyAnalyst/Kafka` 네임스페이스 조건으로 묶었다.
- 제거: `be`, `rag-server` ECS 서비스·ECR, `RAG_SERVER_URL`, `be_image_tag`/`rag_image_tag`(→ `image_tag`), `milvus_key_name`(→ `ec2_key_name`).

## 2. 작업 중 발견한 문제 (이전부터 있던 것 포함)

1. **보안그룹 description이 AWS 문자 제약을 어겼다.** AWS는 `a-zA-Z0-9 ._-:/()#,@[]+=&;{}!$*`만 허용한다. 기존 description은 한국어였고, 새로 쓴 것은 `->`를 썼다. `terraform validate`가 규칙 description의 `->`를 거부해 발견했다. 모두 영어로, `->`는 `to`로 바꿨다.
2. **Milvus EC2 user data가 실행되지 않는 형태였다.**
   - 첫 줄이 `#!`가 아니라 `set -eux`였다. cloud-init은 `#!`로 시작하는 user data만 스크립트로 실행한다.
   - compose 파일을 들여쓰기 없이 `<<-EOF` heredoc 안에 넣고 있었다. 그래서 공통 들여쓰기가 0이 되어 아무것도 지워지지 않았다. 결과적으로 shebang과 heredoc 종료 표시(`COMPOSE`)가 공백 4칸을 단 채 남는다.
   - 두 모듈 모두 user data를 `templatefile` 템플릿 파일로 옮겼다. 그러면 자격 증명 없이 렌더링해 확인할 수 있다(E2).
3. **EC2 템플릿이 사라진 `minio/minio` 이미지를 쓰고 있었다.** 3단계에서 로컬 compose만 Chainguard 이미지로 바꿨었다. EC2 템플릿도 같은 이미지(digest 고정)로 맞췄다. 그 이미지에 없는 `curl` 헬스체크도 뺐다.
4. **SSE와 ALB 기본 idle timeout(60초).** 생성 진행 이벤트는 섹션 사이에 1분 넘게 없을 수 있어 300초로 늘렸다. 실제 ALB에서 측정한 값은 아니다.

## 3. 검증

AWS 자격 증명이 없어 `plan`/`apply`는 하지 않았다(D8: apply는 하지 않음, plan은 자격 증명이 있을 때). Terraform은 `hashicorp/terraform:1.9.8` 이미지로 실행했다.

| 실험 | 결과 | 로그 |
|---|---|---|
| E1 정적 검사 | `terraform fmt -recursive`(서식 맞춤 후 통과), `init -backend=false`, `validate` → "Success! The configuration is valid." | 아래 |
| E2 **user data 렌더링·실행** | 두 템플릿을 `templatefile`로 렌더링 → `bash -n` 통과, 검색 데이터용 compose 파일 `docker compose config` 통과. 렌더링된 Kafka `docker run`을 로컬에서 실행(advertised host만 localhost, 데이터 디렉터리는 EC2처럼 uid 1000 소유): 브로커 기동, 토픽 생성, **없는 토픽에 발행 시 UNKNOWN_TOPIC_OR_PARTITION**(자동 생성 off), 힙 1GB, 데이터 디렉터리 사용. user data가 써 넣는 지표 스크립트도 그대로 동작 | [kafka-metrics](experiment-kafka-metrics.txt) |
| E3 **lag·DLT 지표** | 로컬 브로커에서 `chat` 그룹이 5개 중 2개를 소비하자 `ConsumerLag Group=chat 3`. 인스턴스별 그룹(`notification-*`)은 제외. DLT 2건 → `DeadLetterMessages 2`, 빈 DLT → 0 (`DRY_RUN=1`, AWS CLI 대신 출력) | 같은 파일 |
| E4 **JWT 서명 키(D9)** | 키 파일로 만든 키를 `JWT_SIGNING_KEY`로 넣은 새 컨테이너(키 파일 없음)가 같은 kid, 같은 공개 JWKS를 낸다. 공개키만 넣으면 기동 실패 | [auth-signing-key](experiment-auth-signing-key.txt) |

E1 실행 명령:

```bash
docker run --rm -v "$PWD:/repo" -w /repo/infra/envs/prod hashicorp/terraform:1.9.8 fmt -recursive -check /repo/infra
docker run --rm -v "$PWD:/repo" -w /repo/infra/envs/prod hashicorp/terraform:1.9.8 init -backend=false
docker run --rm -v "$PWD:/repo" -w /repo/infra/envs/prod hashicorp/terraform:1.9.8 validate
```

- auth-service `./mvnw clean verify` 통과(테스트 없음, 빌드만). 다른 Java 서비스 코드는 바뀌지 않았다.
- **확인하지 않은 것**:
  - `terraform plan` 결과(리소스 수, 권한 오류).
  - Fargate 태스크가 Cloud Map의 EC2 레코드를 실제로 해석하는지.
  - Service Connect 하에서 Gateway의 SSE 장시간 연결.
  - `database-init` 태스크의 실제 실행.
  - CloudWatch 알람 발화.

## 4. 알려진 공백

- Kafka 데이터가 EC2 루트 볼륨에 있다. 인스턴스를 교체하면 토픽 데이터가 사라진다. 서비스 DB의 사본은 남지만, `report.created`를 처음부터 다시 읽는 재생은 그 시점 이후 이벤트만 가능해진다. 별도 EBS 볼륨(인스턴스와 수명 분리)이 필요하다.
- 브로커 하나(복제 1). 브로커 장애 중에는 발행이 Outbox에 쌓이고 소비가 멈춘다(2단계 실험과 같은 동작). 다중 브로커나 MSK는 범위 밖이다.
- Prometheus 지표(`/actuator/prometheus`, 워커 `:9100`의 `worker_jobs_total`, `kafka.consumer.dead_lettered`)는 노출만 되고 AWS에서 수집하지 않는다. Kafka 쪽은 브로커에서 직접 계산한 lag·DLT로 대신했다.
- 서비스별 DB 계정이 없다(모두 RDS 마스터 계정). 서비스 SG 하나를 같이 쓰므로, 네트워크 수준에서도 서비스끼리는 서로의 포트에 닿을 수 있다. 이 경계는 공유 비밀(D10)이 맡는다.
- Python 서비스(market-data, qa, stt, knowledge)는 `X-Internal-Token`을 확인하지 않는다.
- 지식 베이스 적재(knowledge-ingest)를 AWS에서 돌리는 경로가 없다. 원본 데이터가 이미지에 없다.
- 워커의 섹션 체크포인트(SQLite)는 Fargate 태스크 임시 디스크에 있다. 태스크가 바뀌면 처음 섹션부터 다시 생성한다.
- 3단계에서 넘어온 "토픽 간 순서"와 "워커가 취소된 Job을 모름"은 그대로다(워커 계약 변경 필요).
