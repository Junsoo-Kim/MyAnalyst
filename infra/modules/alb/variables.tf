variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  description = "network 모듈의 alb_security_group_id"
  type        = string
}

variable "acm_certificate_arn" {
  description = "도메인을 붙이고 발급받은 ACM 인증서 ARN. null(기본값)이면 HTTP:80만 열고, 값을 주면 HTTPS:443을 추가로 열고 HTTP는 그쪽으로 리다이렉트한다."
  type        = string
  default     = null
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "idle_timeout_seconds" {
  description = "ALB 유휴 연결 타임아웃. SSE 구독이 섹션 생성 사이에 끊기지 않도록 기본값(60)보다 길게 둔다."
  type        = number
  default     = 300
}
