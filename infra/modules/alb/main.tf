terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

resource "aws_lb" "this" {
  name               = "${var.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  subnets            = var.public_subnet_ids
  security_groups    = [var.security_group_id]

  tags = merge(var.tags, { Name = "${var.name_prefix}-alb" })
}

# RAG는 ALB 뒤에 두지 않는다 (BE만 외부에 노출, RAG는 Service Connect로 BE에서만 접근).
resource "aws_lb_target_group" "be" {
  name        = "${var.name_prefix}-be-tg"
  port        = 8080
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip" # Fargate awsvpc 모드는 ip 타깃

  health_check {
    path                = "/actuator/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
    matcher             = "200"
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-be-tg" })
}

# acm_certificate_arn이 없으면(기본값) HTTP:80만 열고 그대로 BE로 포워딩한다.
# acm_certificate_arn을 주면 HTTP:80은 HTTPS:443으로 301 리다이렉트만 하고,
# 실제 트래픽은 아래 aws_lb_listener.https가 받는다 - 도메인 없이 시작해도 코드가
# 이미 완성돼 있어서, 나중에 도메인+ACM 인증서만 발급받아 var로 넘기면 바로 켜진다.
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  dynamic "default_action" {
    for_each = var.acm_certificate_arn == null ? [1] : []
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.be.arn
    }
  }

  dynamic "default_action" {
    for_each = var.acm_certificate_arn == null ? [] : [1]
    content {
      type = "redirect"
      redirect {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }
}

resource "aws_lb_listener" "https" {
  count = var.acm_certificate_arn == null ? 0 : 1

  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.be.arn
  }
}
