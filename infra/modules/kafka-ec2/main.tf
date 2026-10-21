terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# 단일 KRaft 브로커(broker + controller 겸용). 로컬 docker-compose의 kafka 서비스와 같은 설정이다.
# 브로커 자동 토픽 생성은 끄고, 토픽은 발행하는 서비스가 만든다.
# 클라이언트는 advertised_host(Cloud Map에 등록한 DNS 이름)로 접속하므로 인스턴스가 바뀌어도 서비스 설정은 그대로다.

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}

data "aws_region" "current" {}

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = "${var.name_prefix}-kafka"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
  tags               = var.tags
}

# 접속은 SSH 대신 SSM Session Manager로도 할 수 있게 한다.
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "metrics" {
  statement {
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = [var.metrics_namespace]
    }
  }
}

resource "aws_iam_role_policy" "metrics" {
  name   = "put-kafka-metrics"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.metrics.json
}

resource "aws_iam_instance_profile" "this" {
  name = "${var.name_prefix}-kafka"
  role = aws_iam_role.this.name
}

locals {
  user_data = templatefile("${path.module}/templates/user-data.sh.tftpl", {
    advertised_host   = var.advertised_host
    kafka_image       = var.kafka_image
    heap_mb           = var.heap_mb
    region            = data.aws_region.current.name
    metrics_namespace = var.metrics_namespace
    metrics_script    = file("${path.module}/templates/kafka-metrics.sh")
  })
}

resource "aws_instance" "kafka" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = [var.security_group_id]
  key_name               = var.key_name
  iam_instance_profile   = aws_iam_instance_profile.this.name
  user_data              = local.user_data

  metadata_options {
    http_tokens = "required"
  }

  root_block_device {
    volume_size = var.root_volume_size_gb
    volume_type = "gp3"
    encrypted   = true
  }

  # 로그(토픽 데이터)가 루트 볼륨에 있으므로 새 AMI가 나왔다고 인스턴스를 바꾸지 않는다.
  lifecycle {
    ignore_changes = [ami]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-kafka" })
}
