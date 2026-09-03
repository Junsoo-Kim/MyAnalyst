terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-rds-subnets"
  subnet_ids = var.private_subnet_ids
  tags       = merge(var.tags, { Name = "${var.name_prefix}-rds-subnets" })
}

resource "aws_db_instance" "this" {
  identifier     = "${var.name_prefix}-postgres"
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage = var.allocated_storage_gb
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = var.db_name
  username = var.username
  # 비밀번호를 직접 만들어 tfvars/state에 평문으로 남기지 않고, RDS가 Secrets Manager에
  # 자동 생성/로테이션하도록 위임한다. BE는 배포 시 이 시크릿을 읽어 SPRING_DATASOURCE_PASSWORD로 주입.
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.security_group_id]

  multi_az                = var.multi_az
  publicly_accessible     = false
  deletion_protection     = false
  skip_final_snapshot     = true # 데모/개인 프로젝트 기준 - 운영 전환 시 false + final_snapshot_identifier로 변경
  backup_retention_period = 3

  tags = merge(var.tags, { Name = "${var.name_prefix}-postgres" })
}
