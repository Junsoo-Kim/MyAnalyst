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

variable "gateway_target_group_arn_suffix" {
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
  description = "CPU 알람을 걸 ECS 서비스 이름 목록"
  type        = list(string)
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "kafka_metrics_namespace" {
  description = "kafka-ec2 모듈의 지표 네임스페이스"
  type        = string
}

variable "kafka_lag_thresholds" {
  description = "consumer group -> 10분 연속 넘으면 알릴 lag"
  type        = map(number)
}

variable "kafka_dlt_topics" {
  description = "새 메시지가 들어오면 알릴 DLT 토픽"
  type        = list(string)
}

variable "ec2_instance_ids" {
  description = "상태 검사 알람을 걸 EC2 (이름 -> 인스턴스 ID)"
  type        = map(string)
}
