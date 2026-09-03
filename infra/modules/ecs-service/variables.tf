variable "name_prefix" {
  type = string
}

variable "service_name" {
  description = "예: be, rag-server. Service Connect 내부 DNS 이름(예: http://rag-server:8000)으로도 쓰인다."
  type        = string
}

variable "cluster_arn" {
  type = string
}

variable "cluster_name" {
  type = string
}

variable "service_connect_namespace_arn" {
  type = string
}

variable "subnets" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}

variable "image" {
  description = "ECR 이미지 URI:tag (예: aws_ecr_repository.this.repository_url + \":latest\")"
  type        = string
}

variable "container_port" {
  type = number
}

variable "cpu" {
  type    = number
  default = 512
}

variable "memory" {
  type    = number
  default = 1024
}

variable "environment" {
  description = "컨테이너 환경변수 (평문)"
  type        = map(string)
  default     = {}
}

variable "secrets" {
  description = "Secrets Manager/SSM Parameter Store ARN에서 주입할 환경변수 (name -> valueFrom ARN)"
  type        = map(string)
  default     = {}
}

variable "desired_count" {
  type    = number
  default = 1
}

variable "min_capacity" {
  description = "오토스케일링 최소 태스크 수. 1이면 스케일인 시 해당 서비스가 잠깐 단일 인스턴스가 될 수 있다 (비용 vs 가용성 트레이드오프)."
  type        = number
  default     = 1
}

variable "max_capacity" {
  type    = number
  default = 4
}

variable "cpu_target_value" {
  description = "오토스케일링 목표 평균 CPU 사용률(%)"
  type        = number
  default     = 60
}

variable "capacity_provider_strategy" {
  description = "FARGATE(온디맨드)/FARGATE_SPOT 비율. base로 지정한 개수는 항상 그 provider로 뜬다."
  type = list(object({
    capacity_provider = string
    weight            = number
    base              = optional(number, 0)
  }))
  default = [{ capacity_provider = "FARGATE", weight = 1, base = 1 }]
}

variable "target_group_arn" {
  description = "ALB에 붙는 서비스(BE)만 지정. 내부 전용 서비스(RAG)는 null로 둔다."
  type        = string
  default     = null
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "tags" {
  type    = map(string)
  default = {}
}
