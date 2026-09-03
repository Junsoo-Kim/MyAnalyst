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

output "be_security_group_id" {
  description = "BE(Spring Boot) ECS 서비스에 붙일 SG"
  value       = aws_security_group.be.id
}

output "rag_security_group_id" {
  description = "RAG(FastAPI) ECS 서비스에 붙일 SG"
  value       = aws_security_group.rag.id
}

output "milvus_security_group_id" {
  description = "Milvus EC2 인스턴스에 붙일 SG"
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
