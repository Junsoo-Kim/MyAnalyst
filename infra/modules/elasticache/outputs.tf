output "redis_endpoint" {
  description = "BE의 REDIS_HOST에 넣을 엔드포인트"
  value       = aws_elasticache_cluster.this.cache_nodes[0].address
}

output "redis_port" {
  value = aws_elasticache_cluster.this.port
}
