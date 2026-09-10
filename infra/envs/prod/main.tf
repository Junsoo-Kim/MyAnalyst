data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

module "network" {
  source = "../../modules/network"

  name_prefix = "myanalyst-${var.environment}"

  azs                  = local.azs
  public_subnet_cidrs  = ["10.0.0.0/24", "10.0.1.0/24"]
  private_subnet_cidrs = ["10.0.10.0/24", "10.0.11.0/24"]

  single_nat_gateway = true

  management_cidr = var.management_cidr

  tags = {
    Environment = var.environment
  }
}

locals {
  name_prefix = "myanalyst-${var.environment}"
  tags        = { Environment = var.environment }
}

module "rds" {
  source = "../../modules/rds"

  name_prefix        = local.name_prefix
  private_subnet_ids = module.network.private_subnet_ids
  security_group_id  = module.network.rds_security_group_id
  tags               = local.tags
}

module "elasticache" {
  source = "../../modules/elasticache"

  name_prefix        = local.name_prefix
  private_subnet_ids = module.network.private_subnet_ids
  security_group_id  = module.network.elasticache_security_group_id
  tags               = local.tags
}

module "milvus_ec2" {
  source = "../../modules/milvus-ec2"

  name_prefix       = local.name_prefix
  subnet_id         = module.network.private_subnet_ids[0]
  security_group_id = module.network.milvus_security_group_id
  key_name          = var.milvus_key_name
  tags              = local.tags
}

module "ecr_be" {
  source = "../../modules/ecr"
  name   = "${local.name_prefix}-be"
  tags   = local.tags
}

module "ecr_rag" {
  source = "../../modules/ecr"
  name   = "${local.name_prefix}-rag-server"
  tags   = local.tags
}

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

module "ecs_service_be" {
  source = "../../modules/ecs-service"

  name_prefix                   = local.name_prefix
  service_name                  = "be"
  cluster_arn                   = module.ecs_cluster.cluster_arn
  cluster_name                  = module.ecs_cluster.cluster_name
  service_connect_namespace_arn = module.ecs_cluster.service_connect_namespace_arn
  subnets                       = module.network.private_subnet_ids
  security_group_id             = module.network.be_security_group_id

  image          = "${module.ecr_be.repository_url}:${var.be_image_tag}"
  container_port = 8080
  cpu            = 512
  memory         = 1024

  environment = {
    RAG_SERVER_BASE_URL        = "http://rag-server:8000"
    CORS_ALLOWED_ORIGINS       = var.fe_origin
    REDIS_HOST                 = module.elasticache.redis_endpoint
    REDIS_PORT                 = tostring(module.elasticache.redis_port)
    SPRING_DATASOURCE_URL      = "jdbc:postgresql://${module.rds.endpoint}:${module.rds.port}/${module.rds.db_name}"
    SPRING_DATASOURCE_USERNAME = "postgres"
  }
  secrets = {
    SPRING_DATASOURCE_PASSWORD = "${module.rds.master_user_secret_arn}:password::"
  }

  target_group_arn = module.alb.be_target_group_arn
  capacity_provider_strategy = [
    { capacity_provider = "FARGATE", weight = 1, base = 1 },
  ]
  min_capacity = 1
  max_capacity = 4

  tags = local.tags
}

module "ecs_service_rag" {
  source = "../../modules/ecs-service"

  name_prefix                   = local.name_prefix
  service_name                  = "rag-server"
  cluster_arn                   = module.ecs_cluster.cluster_arn
  cluster_name                  = module.ecs_cluster.cluster_name
  service_connect_namespace_arn = module.ecs_cluster.service_connect_namespace_arn
  subnets                       = module.network.private_subnet_ids
  security_group_id             = module.network.rag_security_group_id

  image          = "${module.ecr_rag.repository_url}:${var.rag_image_tag}"
  container_port = 8000
  cpu            = 2048
  memory         = 4096

  environment = {
    MILVUS_HOST = module.milvus_ec2.private_ip
    MILVUS_PORT = "19530"
  }
  secrets = {
    OPENAI_API_KEY = var.openai_api_key_secret_arn
  }

  target_group_arn = null
  capacity_provider_strategy = [
    { capacity_provider = "FARGATE", weight = 1, base = 1 },
    { capacity_provider = "FARGATE_SPOT", weight = 4, base = 0 },
  ]
  min_capacity = 1
  max_capacity = 6

  tags = local.tags
}

module "github_oidc" {
  source = "../../modules/github-oidc"

  name_prefix      = local.name_prefix
  github_repo      = var.github_repo
  allowed_branches = ["main"]

  ecr_repository_arns = [module.ecr_be.repository_arn, module.ecr_rag.repository_arn]
  ecs_service_arns    = [module.ecs_service_be.service_arn, module.ecs_service_rag.service_arn]
  passable_role_arns = [
    module.ecs_service_be.execution_role_arn, module.ecs_service_be.task_role_arn,
    module.ecs_service_rag.execution_role_arn, module.ecs_service_rag.task_role_arn,
  ]

  tags = local.tags
}

module "observability" {
  source = "../../modules/observability"

  name_prefix = local.name_prefix
  alarm_email = var.alarm_email

  alb_arn_suffix             = module.alb.arn_suffix
  be_target_group_arn_suffix = module.alb.be_target_group_arn_suffix
  rds_instance_id            = "${local.name_prefix}-postgres"
  elasticache_cluster_id     = "${local.name_prefix}-redis"
  ecs_cluster_name           = module.ecs_cluster.cluster_name
  ecs_service_names          = [module.ecs_service_be.service_name, module.ecs_service_rag.service_name]

  tags = local.tags
}
