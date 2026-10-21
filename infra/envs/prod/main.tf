data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs         = slice(data.aws_availability_zones.available.names, 0, 2)
  name_prefix = "myanalyst-${var.environment}"
  tags        = { Environment = var.environment }
}

module "network" {
  source = "../../modules/network"

  name_prefix = local.name_prefix

  azs                  = local.azs
  public_subnet_cidrs  = ["10.0.0.0/24", "10.0.1.0/24"]
  private_subnet_cidrs = ["10.0.10.0/24", "10.0.11.0/24"]

  single_nat_gateway = true

  management_cidr = var.management_cidr

  tags = local.tags
}

# --- 데이터 계층 ---

# PostgreSQL 인스턴스 하나에 서비스별 database(user_db, report_db, generation_db, chat_db, dictionary_db)를 둔다.
# database는 database_init.tf의 일회성 태스크가 만든다.
module "rds" {
  source = "../../modules/rds"

  name_prefix        = local.name_prefix
  private_subnet_ids = module.network.private_subnet_ids
  security_group_id  = module.network.rds_security_group_id
  tags               = local.tags
}

# api-gateway(로그인 rate limit), auth-service(refresh token), market-data(크롤링 캐시)
module "elasticache" {
  source = "../../modules/elasticache"

  name_prefix        = local.name_prefix
  private_subnet_ids = module.network.private_subnet_ids
  security_group_id  = module.network.elasticache_security_group_id
  tags               = local.tags
}

# 검색 데이터(Milvus + OpenSearch). knowledge 서비스만 읽는다.
module "milvus_ec2" {
  source = "../../modules/milvus-ec2"

  name_prefix       = local.name_prefix
  subnet_id         = module.network.private_subnet_ids[0]
  security_group_id = module.network.milvus_security_group_id
  key_name          = var.ec2_key_name
  tags              = local.tags
}

module "kafka_ec2" {
  source = "../../modules/kafka-ec2"

  name_prefix       = local.name_prefix
  subnet_id         = module.network.private_subnet_ids[0]
  security_group_id = module.network.kafka_security_group_id
  advertised_host   = "kafka.${module.ecs_cluster.namespace_name}"
  key_name          = var.ec2_key_name
  tags              = local.tags
}

# --- 컴퓨팅 ---

module "ecs_cluster" {
  source = "../../modules/ecs-cluster"

  name_prefix = local.name_prefix
  vpc_id      = module.network.vpc_id
  tags        = local.tags
}

module "alb" {
  source = "../../modules/alb"

  name_prefix         = local.name_prefix
  vpc_id              = module.network.vpc_id
  public_subnet_ids   = module.network.public_subnet_ids
  security_group_id   = module.network.alb_security_group_id
  acm_certificate_arn = var.acm_certificate_arn
  tags                = local.tags
}

# 서비스별 ECR 리포지토리. 이름은 CI(.github/workflows/deploy.yml)의 "${NAME_PREFIX}-${matrix.name}"과 같다.
module "ecr" {
  source   = "../../modules/ecr"
  for_each = local.services

  name = "${local.name_prefix}-${each.key}"
  tags = local.tags
}

# 서비스 정의는 services.tf
module "service" {
  source   = "../../modules/ecs-service"
  for_each = local.services

  name_prefix                   = local.name_prefix
  service_name                  = each.key
  cluster_arn                   = module.ecs_cluster.cluster_arn
  cluster_name                  = module.ecs_cluster.cluster_name
  service_connect_namespace_arn = module.ecs_cluster.service_connect_namespace_arn
  subnets                       = module.network.private_subnet_ids
  security_group_ids = concat(
    [module.network.services_security_group_id],
    each.value.public ? [module.network.gateway_security_group_id] : [],
  )

  image          = "${module.ecr[each.key].repository_url}:${var.image_tag}"
  container_port = each.value.port
  cpu            = each.value.cpu
  memory         = each.value.memory

  environment = each.value.environment
  secrets     = each.value.secrets

  target_group_arn           = each.value.public ? module.alb.gateway_target_group_arn : null
  capacity_provider_strategy = each.value.spot ? local.spot_strategy : local.on_demand_strategy
  min_capacity               = each.value.min_capacity
  max_capacity               = each.value.max_capacity

  tags = local.tags
}

module "github_oidc" {
  source = "../../modules/github-oidc"

  name_prefix      = local.name_prefix
  github_repo      = var.github_repo
  allowed_branches = ["main"]

  ecr_repository_arns = [for repo in module.ecr : repo.repository_arn]
  ecs_service_arns    = [for svc in module.service : svc.service_arn]
  passable_role_arns = flatten([
    for svc in module.service : [svc.execution_role_arn, svc.task_role_arn]
  ])

  tags = local.tags
}

module "observability" {
  source = "../../modules/observability"

  name_prefix = local.name_prefix
  alarm_email = var.alarm_email

  alb_arn_suffix                  = module.alb.arn_suffix
  gateway_target_group_arn_suffix = module.alb.gateway_target_group_arn_suffix
  rds_instance_id                 = "${local.name_prefix}-postgres"
  elasticache_cluster_id          = "${local.name_prefix}-redis"
  ecs_cluster_name                = module.ecs_cluster.cluster_name
  ecs_service_names               = [for svc in module.service : svc.service_name]

  kafka_metrics_namespace = module.kafka_ec2.metrics_namespace
  kafka_lag_thresholds = {
    # 워커는 긴 생성 중에 파티션을 멈춰 두므로 인스턴스당 몇 건은 정상이다.
    "generation-worker"  = 20
    "generation-tracker" = 100
    "generation"         = 100
    "report"             = 50
    "dictionary"         = 100
    "chat"               = 100
  }
  kafka_dlt_topics = [
    "generation.requested.DLT",
    "generation.progressed.DLT",
    "generation.completed.DLT",
    "generation.failed.DLT",
    "job.status-changed.DLT",
    "report.save-requested.DLT",
    "report.created.DLT",
  ]
  ec2_instance_ids = {
    kafka       = module.kafka_ec2.instance_id
    search-data = module.milvus_ec2.instance_id
  }

  tags = local.tags
}
