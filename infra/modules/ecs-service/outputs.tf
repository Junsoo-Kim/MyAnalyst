output "service_name" {
  value = aws_ecs_service.this.name
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.this.name
}

output "task_role_arn" {
  value = aws_iam_role.task.arn
}

output "execution_role_arn" {
  value = aws_iam_role.execution.arn
}

output "service_arn" {
  description = "GitHub Actions 배포 역할(github-oidc 모듈)이 ecs:UpdateService 권한을 이 ARN으로만 한정하는 데 쓴다"
  value       = "arn:aws:ecs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:service/${var.cluster_name}/${aws_ecs_service.this.name}"
}
