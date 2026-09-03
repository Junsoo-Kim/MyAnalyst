# 서비스 계층별 최소 권한 보안그룹.
# 트래픽 경로: 인터넷 -> ALB -> BE -> RAG -> Milvus / RDS
# 각 SG는 "바로 앞 계층의 SG"에서만 인바운드를 허용합니다 (계층을 건너뛴 접근 차단).

# --- ALB: 인터넷 -> ALB ---
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

# --- BE(Spring Boot): ALB -> BE:8080 ---
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

# --- RAG(FastAPI): BE -> RAG:8000 ---
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

# --- Milvus(EC2): RAG -> Milvus:19530(gRPC)/9091(health), 선택적 관리자 SSH ---
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

# --- RDS(PostgreSQL): BE -> RDS:5432 ---
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

# --- ElastiCache(Redis): BE -> Redis:6379 ---
# BE의 뉴스/주가 조회(ReportService.getNewsByCompany/getStockByCompany)가
# @Cacheable로 실제 캐싱하도록 구현되어 있어, 이제 아래 SG를 쓰는 ElastiCache가 필요하다.
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
