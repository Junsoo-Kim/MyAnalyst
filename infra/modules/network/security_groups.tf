
resource "aws_security_group" "alb" {
  name_prefix = "${var.name_prefix}-alb-"
  description = "Public ALB: 인터넷의 HTTP/HTTPS만 허용"
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

resource "aws_security_group" "be" {
  name_prefix = "${var.name_prefix}-be-"
  description = "BE(Spring Boot): ALB에서만 8080 인바운드 허용"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "ALB -> BE"
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

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-be-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "rag" {
  name_prefix = "${var.name_prefix}-rag-"
  description = "RAG(FastAPI): BE에서만 8000 인바운드 허용"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "BE -> RAG"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.be.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-rag-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "milvus" {
  name_prefix = "${var.name_prefix}-milvus-"
  description = "Milvus: RAG에서만 19530/9091 인바운드 허용"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "RAG -> Milvus gRPC"
    from_port       = 19530
    to_port         = 19530
    protocol        = "tcp"
    security_groups = [aws_security_group.rag.id]
  }

  ingress {
    description     = "RAG -> Milvus health"
    from_port       = 9091
    to_port         = 9091
    protocol        = "tcp"
    security_groups = [aws_security_group.rag.id]
  }

  dynamic "ingress" {
    for_each = var.management_cidr == null ? [] : [var.management_cidr]
    content {
      description = "관리자 SSH (management_cidr)"
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

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-milvus-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "rds" {
  name_prefix = "${var.name_prefix}-rds-"
  description = "RDS(PostgreSQL): BE에서만 5432 인바운드 허용"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "BE -> RDS"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.be.id]
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
  description = "ElastiCache(Redis): BE에서만 6379 인바운드 허용"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "BE -> Redis"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.be.id]
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
