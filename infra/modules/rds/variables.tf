variable "name_prefix" {
  type = string
}

variable "private_subnet_ids" {
  description = "RDS를 배치할 프라이빗 서브넷 ID 목록 (2개 이상, network 모듈의 private_subnet_ids)"
  type        = list(string)
}

variable "security_group_id" {
  description = "network 모듈의 rds_security_group_id"
  type        = string
}

variable "instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "allocated_storage_gb" {
  type    = number
  default = 20
}

variable "engine_version" {
  type    = string
  default = "16.4"
}

variable "db_name" {
  type    = string
  default = "myanalystdb"
}

variable "username" {
  type    = string
  default = "postgres"
}

variable "multi_az" {
  description = "true면 RDS를 Multi-AZ로 (고가용성, 비용 2배). 개인 프로젝트 기본값은 false."
  type        = bool
  default     = false
}

variable "tags" {
  type    = map(string)
  default = {}
}
