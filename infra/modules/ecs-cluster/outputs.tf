output "cluster_arn" {
  value = aws_ecs_cluster.this.arn
}

output "cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "service_connect_namespace_arn" {
  value = aws_service_discovery_private_dns_namespace.this.arn
}
