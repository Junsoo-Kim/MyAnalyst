# 서비스별 database를 만드는 일회성 ECS 태스크(D6). 서비스(aws_ecs_service)로 띄우지 않고 정의만 둔다.
# RDS는 프라이빗 서브넷에 있어 Terraform 실행 위치에서 직접 접속할 수 없으므로, 같은 VPC 안에서 psql을 한 번 돌린다.
# SQL은 로컬 docker-compose가 쓰는 scripts/postgres/init-databases.sql 그대로이며 여러 번 실행해도 된다.
#
#   $(terraform output -raw database_init_command)

resource "aws_cloudwatch_log_group" "database_init" {
  name              = "/ecs/${local.name_prefix}-database-init"
  retention_in_days = 14
  tags              = local.tags
}

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "database_init" {
  name               = "${local.name_prefix}-database-init-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "database_init" {
  role       = aws_iam_role.database_init.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "database_init_secret" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [module.rds.master_user_secret_arn]
  }
}

resource "aws_iam_role_policy" "database_init_secret" {
  name   = "rds-master-secret"
  role   = aws_iam_role.database_init.id
  policy = data.aws_iam_policy_document.database_init_secret.json
}

resource "aws_ecs_task_definition" "database_init" {
  family                   = "${local.name_prefix}-database-init"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.database_init.arn

  container_definitions = jsonencode([
    {
      name      = "psql"
      image     = "postgres:16-alpine"
      essential = true
      command   = ["sh", "-c", "printf '%s\\n' \"$INIT_SQL\" | psql -v ON_ERROR_STOP=1"]
      environment = [
        { name = "PGHOST", value = module.rds.endpoint },
        { name = "PGPORT", value = tostring(module.rds.port) },
        { name = "PGUSER", value = "postgres" },
        { name = "PGDATABASE", value = "postgres" },
        { name = "INIT_SQL", value = file("${path.module}/../../../scripts/postgres/init-databases.sql") },
      ]
      secrets = [
        { name = "PGPASSWORD", valueFrom = "${module.rds.master_user_secret_arn}:password::" },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.database_init.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "database-init"
        }
      }
    }
  ])

  tags = local.tags
}
