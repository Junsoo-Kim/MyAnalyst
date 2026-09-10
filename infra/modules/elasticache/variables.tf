variable "name_prefix" {
  description = "리소스 이름 접두사 (예: myanalyst-prod)"
  type        = string
}

variable "private_subnet_ids" {
  description = "Redis를 배치할 프라이빗 서브넷 ID 목록 (network 모듈의 private_subnet_ids)"
  type        = list(string)
}

variable "security_group_id" {
  description = "Redis에 붙일 보안그룹 (network 모듈의 elasticache_security_group_id)"
  type        = string
}

variable "node_type" {
  description = "캐시 노드 인스턴스 타입. 캐시 용도라 데이터 유실을 감수할 수 있으므로 가장 저렴한 버스터블 타입을 기본값으로 둔다."
  type        = string
  default     = "cache.t4g.micro"
}

variable "engine_version" {
  description = "Redis 엔진 버전"
  type        = string
  default     = "7.1"
}

variable "tags" {
  type    = map(string)
  default = {}
}
