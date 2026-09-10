variable "name_prefix" {
  description = "리소스 이름 접두사 (예: myanalyst-prod)"
  type        = string
}

variable "vpc_cidr" {
  description = "VPC CIDR 블록"
  type        = string
  default     = "10.0.0.0/16"
}

variable "azs" {
  description = "사용할 가용영역 목록 (public/private subnet cidr 리스트와 같은 개수/순서여야 함, 최소 2개 권장)"
  type        = list(string)
}

variable "public_subnet_cidrs" {
  description = "퍼블릭 서브넷(ALB용) CIDR 목록 - azs와 같은 순서"
  type        = list(string)
}

variable "private_subnet_cidrs" {
  description = "프라이빗 서브넷(BE/RAG/Milvus/RDS용) CIDR 목록 - azs와 같은 순서"
  type        = list(string)
}

variable "single_nat_gateway" {
  description = <<-EOT
    true  : NAT Gateway를 1개만 만들어 모든 프라이빗 서브넷이 공유 (비용 절감, 개인/데모 프로젝트 기본값).
            해당 AZ 장애 시 다른 AZ의 프라이빗 서브넷도 아웃바운드가 끊길 수 있음.
    false : AZ마다 1개씩 생성 (고가용성 우선, NAT Gateway 비용이 AZ 수만큼 증가).
  EOT
  type        = bool
  default     = true
}

variable "management_cidr" {
  description = "Milvus EC2 SSH(22) 접근을 허용할 IP 대역 (예: 본인 공인 IP의 /32). null이면 SSH를 열지 않음."
  type        = string
  default     = null
}

variable "tags" {
  description = "모든 리소스에 공통으로 붙일 태그"
  type        = map(string)
  default     = {}
}
