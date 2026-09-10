output "private_ip" {
  description = "RAG 서버의 MILVUS_HOST에 넣을 사설 IP (인스턴스가 교체되면 바뀔 수 있음 - 안정적인 이름이 필요하면 Route53 private hosted zone 레코드를 추가로 붙이는 걸 권장)"
  value       = aws_instance.milvus.private_ip
}

output "instance_id" {
  value = aws_instance.milvus.id
}
