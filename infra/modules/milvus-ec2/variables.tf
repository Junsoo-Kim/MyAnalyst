variable "name_prefix" {
  type = string
}

variable "subnet_id" {
  description = "Milvus를 배치할 프라이빗 서브넷 1개 (network 모듈의 private_subnet_ids[0])"
  type        = string
}

variable "security_group_id" {
  description = "network 모듈의 milvus_security_group_id"
  type        = string
}

variable "instance_type" {
  description = "etcd+minio+milvus standalone을 한 인스턴스에서 같이 돌리기 위한 최소 권장 사양(8GB RAM 이상)"
  type        = string
  default     = "t3.large"
}

variable "root_volume_size_gb" {
  description = "루트 볼륨 크기. Milvus 데이터/etcd/minio가 전부 이 볼륨에 저장된다."
  type        = number
  default     = 100
}

variable "key_name" {
  description = "SSH 접속용 EC2 키페어 이름. null이면 키 없이 생성(콘솔 EC2 Instance Connect/SSM으로만 접근)."
  type        = string
  default     = null
}

variable "tags" {
  type    = map(string)
  default = {}
}
