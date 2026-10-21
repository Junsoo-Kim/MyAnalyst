# 보안그룹 체인 (description은 AWS 제약상 ASCII만 쓴다): 인터넷 → ALB → api-gateway → (Service Connect) 서비스들 → 데이터 계층.
# ECS 서비스는 모두 services SG를 갖고 서로의 서비스 포트(8000/8080)와 지표 포트(9100)만 열어 둔다.
# api-gateway만 gateway SG를 하나 더 가져 ALB에서 들어오는 8080을 받는다.
# 데이터 계층(RDS, Redis, Kafka, Milvus/OpenSearch)은 services SG에서 오는 해당 포트만 받는다.

resource "aws_security_group" "alb" {
  name_prefix = "${var.name_prefix}-alb-"
  description = "Public ALB: HTTP/HTTPS from the internet"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-alb-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "gateway" {
  name_prefix = "${var.name_prefix}-gateway-"
  description = "api-gateway: 8080 from the ALB only"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "ALB to api-gateway"
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-gateway-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "services" {
  name_prefix = "${var.name_prefix}-services-"
  description = "ECS services: service ports (8000 Python, 8080 Java) and metrics (9100) within this SG"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "service to Python service"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    self        = true
  }

  ingress {
    description = "service to Java service"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    self        = true
  }

  ingress {
    description = "metrics (generation-worker)"
    from_port   = 9100
    to_port     = 9100
    protocol    = "tcp"
    self        = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-services-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "milvus" {
  name_prefix = "${var.name_prefix}-search-data-"
  description = "Search data EC2 (Milvus, OpenSearch): 19530/9091/9200 from ECS services"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "services to Milvus gRPC"
    from_port       = 19530
    to_port         = 19530
    protocol        = "tcp"
    security_groups = [aws_security_group.services.id]
  }

  ingress {
    description     = "services to Milvus health"
    from_port       = 9091
    to_port         = 9091
    protocol        = "tcp"
    security_groups = [aws_security_group.services.id]
  }

  ingress {
    description     = "services to OpenSearch"
    from_port       = 9200
    to_port         = 9200
    protocol        = "tcp"
    security_groups = [aws_security_group.services.id]
  }

  dynamic "ingress" {
    for_each = var.management_cidr == null ? [] : [var.management_cidr]
    content {
      description = "Admin SSH (management_cidr)"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-search-data-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "kafka" {
  name_prefix = "${var.name_prefix}-kafka-"
  description = "Kafka EC2 (single KRaft broker): 9092 from ECS services"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "services to Kafka"
    from_port       = 9092
    to_port         = 9092
    protocol        = "tcp"
    security_groups = [aws_security_group.services.id]
  }

  dynamic "ingress" {
    for_each = var.management_cidr == null ? [] : [var.management_cidr]
    content {
      description = "Admin SSH (management_cidr)"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-kafka-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "rds" {
  name_prefix = "${var.name_prefix}-rds-"
  description = "RDS (PostgreSQL): 5432 from ECS services"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "services to RDS"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.services.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-rds-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "elasticache" {
  name_prefix = "${var.name_prefix}-elasticache-"
  description = "ElastiCache (Redis): 6379 from ECS services"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "services to Redis"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.services.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-elasticache-sg" })

  lifecycle {
    create_before_destroy = true
  }
}
