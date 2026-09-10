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
  user_data = <<-EOF
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
