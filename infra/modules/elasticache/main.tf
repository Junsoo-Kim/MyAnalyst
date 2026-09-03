terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# 단일 노드 캐시 클러스터.
# 여기 저장되는 건 뉴스/주가 조회 결과의 짧은 TTL(1~5분) 캐시뿐이라, 유실돼도
# BE가 원본(RAG 서버 -> 네이버 크롤링)으로 그대로 폴백한다 - 그래서 복제/Multi-AZ 없는
# 단일 노드로 비용을 아꼈다. 세션 저장소 등 유실되면 안 되는 용도로 넓어지면
# aws_elasticache_replication_group(Multi-AZ)으로 바꿔야 한다.
resource "aws_elasticache_subnet_group" "this" {
  name       = "${var.name_prefix}-redis-subnets"
  subnet_ids = var.private_subnet_ids
}

resource "aws_elasticache_cluster" "this" {
  cluster_id           = "${var.name_prefix}-redis"
  engine               = "redis"
  engine_version       = var.engine_version
  node_type            = var.node_type
  num_cache_nodes      = 1
  port                 = 6379
  parameter_group_name = "default.redis7"
  subnet_group_name    = aws_elasticache_subnet_group.this.name
  security_group_ids   = [var.security_group_id]

  tags = merge(var.tags, { Name = "${var.name_prefix}-redis" })
}
