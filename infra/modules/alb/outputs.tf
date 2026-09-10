output "dns_name" {
  description = "FE가 API를 호출할 주소 (도메인 연결 전까지는 이 DNS 이름을 그대로 사용)"
  value       = aws_lb.this.dns_name
}

output "be_target_group_arn" {
  value = aws_lb_target_group.be.arn
}

output "arn_suffix" {
  value = aws_lb.this.arn_suffix
}

output "be_target_group_arn_suffix" {
  value = aws_lb_target_group.be.arn_suffix
}
