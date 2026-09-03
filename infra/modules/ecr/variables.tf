variable "name" {
  description = "리포지토리 이름 (예: myanalyst-prod-be)"
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
