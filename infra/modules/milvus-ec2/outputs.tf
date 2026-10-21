output "private_ip" {
  description = "사설 IP. 서비스는 이 IP로 Cloud Map에 등록한 DNS 이름(search-data.<namespace>)으로 접속한다."
  value       = aws_instance.milvus.private_ip
}

output "instance_id" {
  value = aws_instance.milvus.id
}
