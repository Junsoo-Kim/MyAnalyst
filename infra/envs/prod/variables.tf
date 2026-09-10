variable "aws_region" {
  description = "배포 리전"
  type        = string
  default     = "ap-northeast-2"
}

variable "environment" {
  description = "환경 이름 (리소스 이름/태그에 사용)"
  type        = string
  default     = "prod"
}

variable "management_cidr" {
  description = "Milvus EC2 SSH 접근을 허용할 본인 공인 IP (예: 1.2.3.4/32). 비워두면(null) SSH를 열지 않습니다."
  type        = string
  default     = null
}

variable "milvus_key_name" {
  description = "Milvus EC2에 붙일 SSH 키페어 이름. null이면 키 없이 생성(콘솔 EC2 Instance Connect로만 접근)."
  type        = string
  default     = null
}

variable "openai_api_key_secret_arn" {
  description = <<-EOT
    RAG 서버가 쓸 OPENAI_API_KEY가 저장된 Secrets Manager 시크릿의 ARN.
    Terraform이 만들지 않고 미리 콘솔/CLI로 직접 만들어서 값을 여기 var로만 참조한다
    (API 키 평문이 tfvars나 state에 새로 기록되지 않게 하기 위함):
      aws secretsmanager create-secret --name myanalyst-prod/openai-api-key \
        --secret-string "sk-..."
  EOT
  type        = string
}

variable "be_image_tag" {
  description = "ECR에 푸시된 BE 이미지 태그. 첫 apply 시점엔 리포지토리만 만들어지고 이미지가 없으므로,\nCI에서 이미지를 푸시한 뒤 ECS 서비스가 정상 기동한다."
  type        = string
  default     = "latest"
}

variable "rag_image_tag" {
  type    = string
  default = "latest"
}

variable "fe_origin" {
  description = "BE의 CORS 허용 Origin. FE를 S3/CloudFront 등으로 배포하면 그 주소로 바꿀 것."
  type        = string
  default     = "http://localhost:3000"
}

variable "alarm_email" {
  description = "CloudWatch 알람을 받을 이메일. null이면 SNS 구독 없이 토픽만 생성."
  type        = string
  default     = null
}

variable "acm_certificate_arn" {
  description = "도메인을 붙이고 발급받은 ACM 인증서 ARN. null(기본값)이면 HTTP:80만 연다."
  type        = string
  default     = null
}

variable "github_repo" {
  description = "GitHub Actions OIDC 배포 역할을 쓸 수 있는 repo (owner/repo)"
  type        = string
  default     = "Junsoo-Kim/MyAnalyst"
}
