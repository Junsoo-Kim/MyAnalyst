output "private_ip" {
  description = "Cloud Map 인스턴스 등록에 쓰는 사설 IP"
  value       = aws_instance.kafka.private_ip
}

output "instance_id" {
  value = aws_instance.kafka.id
}

output "bootstrap_servers" {
  description = "서비스의 KAFKA_BOOTSTRAP_SERVERS 값"
  value       = "${var.advertised_host}:9092"
}

output "metrics_namespace" {
  value = var.metrics_namespace
}
