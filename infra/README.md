# infra/ — Terraform으로 코드화한 AWS 인프라

```
infra/
├── modules/
│   ├── network/         # VPC, public/private 서브넷×2AZ, IGW, NAT, 서비스별 보안그룹
│   ├── rds/              # RDS(PostgreSQL), 비밀번호는 Secrets Manager가 관리
│   ├── elasticache/       # ElastiCache(Redis) 단일 노드 - 뉴스/주가 캐시
│   ├── milvus-ec2/        # Milvus(EC2, stateful이라 Fargate 대신 EC2)
│   ├── ecr/               # 컨테이너 이미지 레지스트리 (BE/RAG 공용, 2회 인스턴스화)
│   ├── ecs-cluster/       # Fargate 클러스터 + Service Connect 네임스페이스
│   ├── alb/               # Public ALB (BE만 노출, RAG는 내부 전용, HTTPS는 인증서 있으면 자동 활성화)
│   ├── ecs-service/       # BE/RAG 공용 Fargate 서비스 모듈 (오토스케일링 포함)
│   ├── github-oidc/       # GitHub Actions가 장기 액세스키 없이 배포할 수 있는 IAM 역할(OIDC)
│   └── observability/     # CloudWatch 알람 + SNS
└── envs/
    └── prod/              # 위 모듈을 실제 값으로 조합하는 진입점
```

## 아키텍처

```
                    Route53(선택) -> ALB(public)
                                       │ :80
                          ┌────────────────────────┐
                          │ ECS Fargate: be         │  ALB 헬스체크: /actuator/health
                          │ 온디맨드 100%            │  min1/max4, CPU 60% 타깃트래킹
                          └───────────┬─────────────┘
                                      │ Service Connect (http://rag-server:8000)
                          ┌───────────────────────────┐
                          │ ECS Fargate: rag-server    │  min1/max6, CPU 60% 타깃트래킹
                          │ 온디맨드1 + Spot 나머지     │  (임베딩 연산이라 Spot에 관대)
                          └──────┬──────────┬──────────┘
                                 │          │
                     Milvus(EC2) │          │ RDS(PostgreSQL) ◄── be
                                 │          └ ElastiCache(Redis) ◄── be

[CloudWatch 알람: ALB 5xx/헬스체크, RDS CPU/스토리지, Redis CPU, ECS CPU] -> SNS -> 이메일
```

1단계(docker-compose)에서 검증한 `BE → RAG → Milvus/RDS/Redis` 통신 경로를 그대로 AWS 리소스로 옮긴 것 - 서비스 이름(`rag-server`, 포트 8080/8000/19530/5432/6379)도 동일하게 맞춰서, 로컬에서 맞는 그림이 클라우드에서도 그대로 맞게 했습니다.

## 사용법

```bash
cd infra/envs/prod
cp terraform.tfvars.example terraform.tfvars
# openai_api_key_secret_arn은 미리 만들어야 함:
aws secretsmanager create-secret --name myanalyst-prod/openai-api-key --secret-string "sk-..."
# 위 명령 출력의 ARN을 terraform.tfvars에 채운 뒤:

terraform init
terraform plan
terraform apply
```

**첫 apply 이후 순서**: `terraform apply`는 ECR 리포지토리까지만 만듭니다. 그 안에 이미지가 없으면 ECS 서비스는 태스크를 기동하지 못하고 재시도만 반복합니다.

1. `terraform output github_actions_deploy_role_arn` 값을 GitHub repo → Settings → Secrets and variables → Actions에 `AWS_DEPLOY_ROLE_ARN`으로 등록
2. main 브랜치에 `BE/` 또는 `rag_server/` 변경을 푸시하면 [.github/workflows/deploy.yml](../.github/workflows/deploy.yml)이 자동으로 이미지 빌드 → ECR 푸시 → ECS 서비스 배포까지 수행합니다 (장기 AWS 액세스키를 GitHub Secret에 두지 않고 OIDC로 임시 자격증명만 씀)
3. 최초 1회는 태스크 정의가 없으니 `workflow_dispatch`로 수동 실행하거나, `terraform apply` 직후 아무 커밋이나 푸시해서 첫 배포를 트리거하세요

이 세션에는 AWS 자격증명이 없어 `plan`/`apply`는 실행하지 못했습니다. `terraform validate`로 11개 모듈 전체의 문법·리소스 참조 오류가 없음을 확인했고, `terraform plan`은 그래프 구성까지 정상적으로 마친 뒤 자격증명 단계에서만 멈추는 것까지 확인했습니다 (`No valid credential sources found` - 딱 예상되는 지점에서 멈춤). 실제 계정에 적용하기 전 `terraform plan`으로 생성될 리소스 목록을 반드시 검토하세요.

### state 백엔드(S3+DynamoDB) 전환

1. 지금처럼 로컬 state로 첫 `apply` (버킷/테이블이 아직 없으므로)
2. S3 버킷 + DynamoDB 테이블을 콘솔이나 별도 부트스트랩 스택으로 생성
3. `envs/prod/versions.tf`의 `backend "s3" { ... }` 주석 해제, 버킷/테이블 이름 채우기
4. `terraform init -migrate-state`

## 설계 판단 메모

- **Milvus는 Fargate가 아니라 EC2** — stateful 워크로드라 컨테이너 오케스트레이션과 궁합이 안 좋음. `modules/milvus-ec2`가 부팅 시 cloud-init으로 `processing/docker-compose.yml`과 동일한 etcd+minio+milvus 조합을 올림.
- **RAG는 ALB에 노출하지 않음** — BE만 외부에 열고, RAG는 ECS Service Connect(`http://rag-server:8000`)로 BE에서만 접근. 1단계 docker-compose와 동일한 신뢰 경계.
- **RAG는 Fargate Spot 위주** — `base=1`(온디맨드 1개는 항상 보장) + 나머지 스케일아웃은 Spot. 임베딩 배치 연산이라 중단에 상대적으로 관대함. BE는 진입점이라 100% 온디맨드.
- **비밀번호/API 키를 Terraform이 만들지 않음** — RDS 비밀번호는 `manage_master_user_password = true`로 AWS가 Secrets Manager에 직접 생성·관리하게 위임했고, OpenAI API 키는 `terraform.tfvars`에 평문으로 두지 않고 미리 만든 시크릿의 ARN만 참조.
- **ElastiCache는 단일 노드** — 캐시로만 쓰이고(뉴스 5분/주가 1분 TTL), 유실돼도 BE가 원본(RAG 서버)으로 그대로 폴백하므로 Multi-AZ 복제 없이 비용을 아꼈다. 세션 저장 등 유실되면 안 되는 용도로 넓히면 `aws_elasticache_replication_group`으로 바꿔야 함.
- **HTTPS는 인증서 유무로 토글** — `acm_certificate_arn`이 null(기본값)이면 HTTP:80만 열고, 도메인을 만들어 ACM 인증서를 발급받은 뒤 그 ARN을 넘기면 코드 변경 없이 443 리스너 + 80→443 리다이렉트가 켜집니다.
- **CI/CD는 OIDC 기반** — `modules/github-oidc`가 만드는 역할은 지정한 repo의 main 브랜치에서 실행된 워크플로우만 assume 가능하고, 권한도 ECR push / 해당 ECS 서비스 업데이트 / 필요한 role의 PassRole로만 좁혀뒀습니다. GitHub Secret에 남는 건 역할 ARN 하나뿐, AWS 액세스키는 저장하지 않습니다.

## 아직 없는 것 (다음 단계 후보)

- FE 호스팅(S3+CloudFront) - 지금 `fe_origin` 변수는 자리만 잡아둔 상태
- S3+DynamoDB state 백엔드로의 실제 전환
- 도메인 구매 + ACM 인증서 발급 (HTTPS 코드는 이미 있고 인증서 ARN만 넘기면 됨)
