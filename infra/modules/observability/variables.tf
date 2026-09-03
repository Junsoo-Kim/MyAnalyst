variable "name_prefix" {
  type = string
}

variable "alarm_email" {
  description = "알람을 받을 이메일. null이면 SNS 구독 없이 토픽만 생성(콘솔에서 나중에 구독 추가 가능)."
  type        = string
  default     = null
}

variable "alb_arn_suffix" {
  type = string
}

variable "be_target_group_arn_suffix" {
  type = string
}

variable "rds_instance_id" {
  type = string
}

variable "elasticache_cluster_id" {
  type = string
}

variable "ecs_cluster_name" {
  type = string
}

variable "ecs_service_names" {
  description = "CPU 알람을 걸 ECS 서비스 이름 목록 (be, rag-server)"
  type        = list(string)
}

variable "tags" {
  type    = map(string)
  default = {}
}
