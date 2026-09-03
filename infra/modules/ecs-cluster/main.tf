terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

resource "aws_ecs_cluster" "this" {
  name = "${var.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled" # 관측성: 태스크별 CPU/메모리/네트워크를 CloudWatch에서 바로 확인
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-cluster" })
}

# FARGATE_SPOT을 쓰려면 클러스터에 두 capacity provider를 모두 연결해둬야 한다.
# 실제 provider 조합(온디맨드:Spot 비율)은 서비스(ecs-service 모듈)마다 다르게 지정한다.
resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name = aws_ecs_cluster.this.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }
}

# BE <-> RAG 내부 통신용 Service Connect 네임스페이스 (BE가 "http://rag-server:8000"으로 호출)
resource "aws_service_discovery_private_dns_namespace" "this" {
  name = "${var.name_prefix}.local"
  vpc  = var.vpc_id
}
