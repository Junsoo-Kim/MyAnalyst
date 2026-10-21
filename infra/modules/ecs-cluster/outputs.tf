output "cluster_arn" {
  value = aws_ecs_cluster.this.arn
}

output "cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "service_connect_namespace_arn" {
  value = aws_service_discovery_private_dns_namespace.this.arn
}

output "namespace_id" {
  description = "Cloud Map private DNS 네임스페이스 ID (EC2로 띄운 Kafka·검색 데이터의 DNS 이름도 여기에 등록한다)"
  value       = aws_service_discovery_private_dns_namespace.this.id
}

output "namespace_name" {
  value = aws_service_discovery_private_dns_namespace.this.name
}
