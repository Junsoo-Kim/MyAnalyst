variable "name_prefix" {
  type = string
}

variable "github_repo" {
  description = "GitHub owner/repo (예: Junsoo-Kim/MyAnalyst). 이 repo에서 실행되는 워크플로우만 역할을 assume할 수 있다."
  type        = string
}

variable "allowed_branches" {
  description = "이 역할을 쓸 수 있는 브랜치. main에 머지된 워크플로우만 실제 배포 권한을 갖게 하기 위함."
  type        = list(string)
  default     = ["main"]
}

variable "ecr_repository_arns" {
  type = list(string)
}

variable "ecs_service_arns" {
  type = list(string)
}

variable "passable_role_arns" {
  description = "ECS가 새 태스크 정의를 등록할 때 필요한 execution/task role ARN 목록 (iam:PassRole 대상)"
  type        = list(string)
}

variable "tags" {
  type    = map(string)
  default = {}
}
