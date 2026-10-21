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
  # cloud-init은 #!로 시작하는 user data만 스크립트로 실행한다(이전에는 shebang이 없어 실행되지 않았다).
  user_data = templatefile("${path.module}/templates/user-data.sh.tftpl", {
    compose_file = file("${path.module}/templates/milvus-compose.yml")
  })
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
