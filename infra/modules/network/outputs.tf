output "vpc_id" {
  value = aws_vpc.this.id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "alb_security_group_id" {
  description = "ALB에 붙일 SG"
  value       = aws_security_group.alb.id
}

output "gateway_security_group_id" {
  description = "api-gateway ECS 서비스에 services SG와 함께 붙일 SG (ALB -> 8080)"
  value       = aws_security_group.gateway.id
}

output "services_security_group_id" {
  description = "모든 ECS 서비스에 붙일 SG (서비스 간 Service Connect 트래픽)"
  value       = aws_security_group.services.id
}

output "kafka_security_group_id" {
  description = "Kafka EC2 인스턴스에 붙일 SG"
  value       = aws_security_group.kafka.id
}

output "milvus_security_group_id" {
  description = "검색 데이터 EC2(Milvus, OpenSearch)에 붙일 SG"
  value       = aws_security_group.milvus.id
}

output "rds_security_group_id" {
  description = "RDS(PostgreSQL) 인스턴스에 붙일 SG"
  value       = aws_security_group.rds.id
}

output "elasticache_security_group_id" {
  description = "ElastiCache(Redis) 클러스터에 붙일 SG"
  value       = aws_security_group.elasticache.id
}
