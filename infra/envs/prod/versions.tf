terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # 상태 파일을 S3 + DynamoDB 락으로 관리합니다.
  # 최초 1회는 아래 backend 블록을 주석 처리한 채로 로컬 state에 apply해서
  # S3 버킷/DynamoDB 테이블을 먼저 만든 뒤(별도 부트스트랩 스택 또는 콘솔),
  # 이 블록을 열고 `terraform init -migrate-state`로 옮기세요.
  # backend "s3" {
  #   bucket         = "myanalyst-terraform-state"
  #   key            = "prod/network.tfstate"
  #   region         = "ap-northeast-2"
  #   dynamodb_table = "myanalyst-terraform-lock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "myanalyst"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
