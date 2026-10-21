variable "name_prefix" {
  type = string
}

variable "subnet_id" {
  description = "브로커를 둘 프라이빗 서브넷 1개"
  type        = string
}

variable "security_group_id" {
  description = "network 모듈의 kafka_security_group_id"
  type        = string
}

variable "advertised_host" {
  description = "클라이언트에 알려 줄 브로커 주소(Cloud Map DNS 이름, 예: kafka.myanalyst-prod.local)"
  type        = string
}

variable "kafka_image" {
  description = "로컬 docker-compose와 같은 이미지"
  type        = string
  default     = "apache/kafka:3.9.1"
}

variable "instance_type" {
  type    = string
  default = "t3.medium"
}

variable "heap_mb" {
  description = "브로커 JVM 힙(MB). 인스턴스 메모리의 절반 이하로 둔다(나머지는 페이지 캐시)."
  type        = number
  default     = 1024
}

variable "root_volume_size_gb" {
  description = "토픽 데이터가 저장되는 루트 볼륨 크기"
  type        = number
  default     = 50
}

variable "key_name" {
  description = "SSH 키페어 이름. null이면 키 없이 생성(SSM Session Manager로 접속)."
  type        = string
  default     = null
}

variable "metrics_namespace" {
  description = "consumer lag·DLT 지표를 올릴 CloudWatch 네임스페이스"
  type        = string
  default     = "MyAnalyst/Kafka"
}

variable "tags" {
  type    = map(string)
  default = {}
}
