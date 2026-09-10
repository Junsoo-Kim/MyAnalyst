output "deploy_role_arn" {
  description = ".github/workflows/deploy.yml의 role-to-assume에 넣을 값"
  value       = aws_iam_role.deploy.arn
}
