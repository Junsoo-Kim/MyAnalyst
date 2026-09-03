terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}

locals {
  # cloud-init: Docker + Compose 플러그인 설치 후 Milvus 스택을 기동한다.
  # NOTE: 실습/개인 프로젝트 수준의 부트스트랩이다. 운영 수준으로 가려면
  # systemd 유닛으로 재부팅 시 자동 기동을 보장하고, CloudWatch 에이전트로
  # 인스턴스 자체 지표(디스크 사용량 등)까지 관측성에 포함시켜야 한다.
  user_data = <<-EOF
    #!/bin/bash
    set -eux
    dnf install -y docker
    systemctl enable --now docker

    curl -SL https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64 \
      -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose

    mkdir -p /opt/milvus /data/etcd /data/minio /data/milvus
    cat > /opt/milvus/docker-compose.yml <<'COMPOSE'
    ${file("${path.module}/templates/milvus-compose.yml")}
    COMPOSE

    cd /opt/milvus
    /usr/local/bin/docker-compose up -d
  EOF
}

resource "aws_instance" "milvus" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = [var.security_group_id]
  key_name               = var.key_name
  user_data              = local.user_data

  root_block_device {
    volume_size = var.root_volume_size_gb
    volume_type = "gp3"
    encrypted   = true
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-milvus" })
}
