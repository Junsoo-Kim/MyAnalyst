output "endpoint" {
  description = "BE의 SPRING_DATASOURCE_URL에 쓸 호스트명"
  value       = aws_db_instance.this.address
}

output "port" {
  value = aws_db_instance.this.port
}

output "db_name" {
  value = aws_db_instance.this.db_name
}

output "master_user_secret_arn" {
  description = "Secrets Manager에 저장된 마스터 비밀번호 시크릿 ARN - ECS 태스크 정의에서 이 ARN을 secrets로 참조"
  value       = aws_db_instance.this.master_user_secret[0].secret_arn
}
