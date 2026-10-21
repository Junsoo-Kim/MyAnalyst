# infra/ — Terraform으로 코드화한 AWS 인프라

```
infra/
├── modules/
│   ├── network/         # VPC, public/private 서브넷×2AZ, IGW, NAT, 보안그룹(ALB → gateway → services → 데이터 계층)
│   ├── rds/             # RDS(PostgreSQL) 1개, 서비스별 database 5개. 비밀번호는 Secrets Manager가 관리
│   ├── elasticache/     # ElastiCache(Redis) 단일 노드 - 로그인 rate limit, refresh token, 시세·뉴스 캐시
│   ├── kafka-ec2/       # Kafka 단일 KRaft 브로커(EC2) + consumer lag·DLT 지표를 CloudWatch로 올리는 타이머
│   ├── milvus-ec2/      # 검색 데이터(EC2): Milvus standalone(etcd, MinIO) + OpenSearch
│   ├── ecr/             # 서비스별 이미지 레지스트리 (for_each로 13개)
│   ├── ecs-cluster/     # Fargate 클러스터 + Service Connect(Cloud Map) 네임스페이스
│   ├── alb/             # Public ALB → api-gateway만. HTTPS는 인증서 ARN이 있으면 켜짐
│   ├── ecs-service/     # Fargate 서비스 공용 모듈 (Service Connect, 오토스케일링, Secrets Manager 주입)
│   ├── github-oidc/     # GitHub Actions가 장기 액세스키 없이 배포하는 IAM 역할(OIDC)
│   └── observability/   # CloudWatch 알람 + SNS (ALB, RDS, Redis, ECS, Kafka lag/DLT, EC2 상태)
└── envs/
    └── prod/
        ├── main.tf           # 모듈 조합
        ├── services.tf       # ECS 서비스 13개의 포트·자원·환경 변수·시크릿 (docker-compose.yml과 같은 이름)
        ├── discovery.tf      # EC2(Kafka, 검색 데이터)를 Cloud Map DNS 이름으로 등록
        ├── secrets.tf        # 내부 토큰, JWT 서명 키 시크릿(값은 Terraform 밖에서 넣음)
        └── database_init.tf  # 서비스별 database를 만드는 일회성 ECS 태스크
```

## 아키텍처

```
인터넷 ──▶ ALB (:80, 인증서가 있으면 :443) ──▶ api-gateway (Fargate)
                                                 │ JWT 검증, X-User-Id + X-Internal-Token, 라우팅
                    ┌────────────────────────────┼──────────────────────────────────┐
                    ▼ Service Connect (http://<서비스>:8080 / :8000)                 ▼
   auth-service ─▶ user-service       generation-service ◀──Kafka──▶ generation-worker ─▶ knowledge
   report-service   notification-service   dictionary-service   chat-service ─▶ qa, stt   market-data

   ┌─────────────── 데이터 계층 (프라이빗 서브넷) ────────────────────────────────────────────┐
   │ RDS PostgreSQL: user_db, report_db, generation_db, chat_db, dictionary_db              │
   │ ElastiCache Redis: gateway rate limit, auth refresh token, market-data 캐시             │
   │ EC2 kafka.<ns>:9092   단일 KRaft 브로커 ── kafka-metrics.timer ─▶ CloudWatch             │
   │ EC2 search-data.<ns>  Milvus :19530, OpenSearch :9200 ◀── knowledge                      │
   └─────────────────────────────────────────────────────────────────────────────────────────┘

[CloudWatch 알람 → SNS → 이메일]
  ALB 5xx·비정상 대상, RDS CPU·스토리지, Redis CPU, ECS 서비스별 CPU,
  Kafka consumer lag(그룹별), DLT 신규 메시지(토픽별), Kafka·검색 데이터 EC2 상태 검사
```

| 서비스 | 포트 | 용량 | 의존 |
|---|---|---|---|
| api-gateway | 8080 (ALB 대상) | 온디맨드, 1~4 | Redis, 모든 HTTP 서비스 |
| auth-service | 8080 | 온디맨드, 1~2 | user-service, Redis, 시크릿(JWT 서명 키) |
| user-service | 8080 | 온디맨드, 1~2 | user_db |
| generation-service | 8080 | 온디맨드, 1~3 | generation_db, Kafka |
| report-service | 8080 | 온디맨드, 1~3 | report_db, Kafka |
| notification-service | 8080 | 온디맨드, 1~3 | Kafka (인스턴스마다 고유 consumer group) |
| dictionary-service / chat-service | 8080 | 온디맨드 | 각자 database, Kafka (chat → qa, stt) |
| knowledge | 8000 | 온디맨드 1 + Spot | Milvus, OpenSearch |
| generation-worker | 9100(지표) | 온디맨드 1 + Spot | Kafka, knowledge, OpenAI |
| market-data | 8000 | 온디맨드 | Redis |
| qa / stt | 8000 | 온디맨드 1 + Spot | OpenAI |

이름과 환경 변수는 로컬 `docker-compose.yml`과 같다. 로컬의 `http://report-service:8080`이 그대로 Service Connect 주소이고, 로컬의 `kafka:19092`는 `kafka.<namespace>:9092`로 바뀐다.

## 사용법

```bash
cd infra/envs/prod
cp terraform.tfvars.example terraform.tfvars
# OpenAI 키 시크릿은 미리 만들고 ARN을 terraform.tfvars에 넣는다:
aws secretsmanager create-secret --name myanalyst-prod/openai-api-key --secret-string "sk-..."

terraform init
terraform plan
terraform apply
```

### 비밀 값 넣기

Terraform은 시크릿의 이름과 권한만 만들고 값은 넣지 않는다(state에 값이 남지 않게). `apply` 뒤에 한 번 넣는다.

```bash
# 서비스 간 공유 비밀 (X-Internal-Token)
aws secretsmanager put-secret-value --secret-id myanalyst-prod/internal-gateway-token \
  --secret-string "$(openssl rand -hex 32)"

# JWT 서명 키: RSA JWK(비공개키 포함). auth-service를 로컬에서 한 번 띄우면 data/jwt-signing-key.json이 생긴다.
aws secretsmanager put-secret-value --secret-id myanalyst-prod/jwt-signing-key \
  --secret-string file://services/auth-service/data/jwt-signing-key.json
```

### 서비스별 database 만들기

RDS는 프라이빗 서브넷에 있으므로 VPC 안에서 일회성 태스크로 `scripts/postgres/init-databases.sql`을 실행한다(여러 번 실행해도 된다).

```bash
$(terraform output -raw database_init_command)
```

기존 공용 database(`myanalystdb`)에 데이터가 있으면 먼저 [scripts/migrate/stage6_split_databases.sh](../scripts/migrate/stage6_split_databases.sh)의 순서(쓰기 중지 → 복사 → 전환)를 따른다. 이 스크립트는 `docker exec`로 psql·pg_dump를 부르므로, RDS에서는 같은 명령을 VPC 안(일회성 태스크나 SSM 접속한 EC2)에서 직접 실행한다.

### 이미지와 배포

`apply`는 ECR 리포지토리까지만 만든다. 리포지토리에 이미지가 없으면 ECS 서비스는 태스크를 기동하지 못하고 재시도만 반복한다.

1. `terraform output github_actions_deploy_role_arn` 값을 GitHub repo → Settings → Secrets and variables → Actions에 `AWS_DEPLOY_ROLE_ARN`으로 등록
2. main 브랜치에 `services/**` 변경을 푸시하거나 `workflow_dispatch`로 [.github/workflows/deploy.yml](../.github/workflows/deploy.yml)을 실행하면 서비스마다 이미지 빌드 → ECR 푸시 → 태스크 정의 갱신 → ECS 배포가 진행된다. 매트릭스 이름이 곧 ECR 리포지토리·태스크 정의·ECS 서비스 이름(`myanalyst-prod-<name>`)이다.

### 검증 방법

```bash
terraform fmt -recursive -check infra
terraform -chdir=infra/envs/prod init -backend=false && terraform -chdir=infra/envs/prod validate
terraform -chdir=infra/envs/prod plan     # AWS 자격 증명이 있을 때
```

로컬에 Terraform이 없으면 `docker run --rm -v "$PWD:/repo" -w /repo/infra/envs/prod hashicorp/terraform:1.9.8 validate`처럼 이미지로 실행한다(`init`을 먼저). EC2 user data는 `templatefile`이라 `terraform console`로 렌더링해 볼 수 있다.

### state 백엔드(S3+DynamoDB) 전환

1. 로컬 state로 첫 `apply` (버킷/테이블이 아직 없으므로)
2. S3 버킷 + DynamoDB 테이블을 콘솔이나 별도 부트스트랩 스택으로 생성
3. `envs/prod/versions.tf`의 `backend "s3" { ... }` 주석 해제, 버킷/테이블 이름 채우기
4. `terraform init -migrate-state`

## 설계 판단 메모

- **ALB 뒤에는 api-gateway 하나.** 인증(JWT 검증)과 라우팅이 Gateway에 있으므로 다른 서비스는 ALB에 붙이지 않는다. Java 서비스는 Gateway가 붙이는 `X-Internal-Token`이 없는 요청을 거절하고(Python 서비스는 확인하지 않는다), 보안그룹도 같은 SG(services) 안에서만 서비스 포트를 연다.
- **Kafka와 Milvus/OpenSearch는 EC2.** 디스크에 상태를 두는 워크로드라 Fargate 대신 EC2에 컨테이너로 띄운다. 인스턴스 IP를 직접 쓰지 않고 Cloud Map에 `kafka.<ns>`, `search-data.<ns>`로 등록해, Kafka의 advertised listener와 서비스 설정이 IP 변경에 묶이지 않게 했다.
- **Kafka 지표는 브로커 호스트에서 CloudWatch로.** Prometheus 서버를 따로 두지 않고, 브로커 호스트의 systemd 타이머가 1분마다 consumer group lag와 `<topic>.DLT` 끝 offset을 `MyAnalyst/Kafka` 네임스페이스로 올린다. 알람은 lag가 10분 동안 기준을 넘을 때, DLT에 새 메시지가 생길 때 울린다. 서비스별 Prometheus 지표(`/actuator/prometheus`, 워커 `:9100`)는 노출만 되어 있고 수집하지 않는다.
- **서비스별 database, 인스턴스는 하나.** 데이터 소유는 database 단위로 나누되 RDS 인스턴스와 마스터 계정은 공유한다(비용). 서비스별 DB 계정은 두지 않았다.
- **Spot은 다시 해도 되는 연산에만.** knowledge, generation-worker, qa, stt는 온디맨드 1개 + Spot. 워커가 회수되면 lease 만료 후 generation-service가 재시도한다. 진입점(api-gateway)과 상태 전이를 맡는 서비스는 온디맨드.
- **비밀 값은 Terraform 밖에서.** RDS 비밀번호는 `manage_master_user_password`로 AWS가 관리하고, OpenAI 키·내부 토큰·JWT 서명 키는 Secrets Manager 시크릿을 ECS `secrets`로 주입한다. auth-service는 `JWT_SIGNING_KEY`가 있으면 파일 대신 그 값을 쓰므로 태스크가 여러 개여도 같은 키로 서명한다.
- **보안그룹 description은 ASCII.** AWS가 허용하는 문자 집합(`a-zA-Z0-9 ._-:/()#,@[]+=&;{}!$*`) 밖이면 `validate`/`apply`가 실패한다.
- **ALB idle timeout 300초.** 보고서 생성 진행을 SSE로 받는 연결은 섹션 사이에 1분 넘게 조용할 수 있다.
- **HTTPS는 인증서 유무로 토글.** `acm_certificate_arn`이 null이면 HTTP:80만 열고, ARN을 넘기면 443 리스너 + 80→443 리다이렉트가 켜진다.
- **CI/CD는 OIDC 기반.** `modules/github-oidc`의 역할은 지정한 repo의 main 브랜치 워크플로우만 assume할 수 있고, 권한도 이 스택의 ECR push / ECS 서비스 업데이트 / 해당 역할 PassRole로 좁혔다.

## 아직 없는 것

- FE 호스팅(S3+CloudFront). `fe_origin`은 자리만 있다.
- 지식 베이스 적재(knowledge-ingest)를 AWS에서 돌리는 방법. 원본 데이터(`processing/`)가 이미지에 없다.
- Kafka 데이터가 루트 볼륨에 있어 인스턴스를 교체하면 토픽 데이터가 사라진다(별도 EBS 볼륨 미적용). 서비스 DB의 사본은 남지만 `report.created` 재생 이력은 처음부터 다시 쌓인다.
- 서비스 간 mTLS(D10: 공유 비밀 유지), 서비스별 DB 계정, Prometheus 지표 수집.
