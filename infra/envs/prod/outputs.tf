output "vpc_id" {
  value = module.network.vpc_id
}

output "public_subnet_ids" {
  value = module.network.public_subnet_ids
}

output "private_subnet_ids" {
  value = module.network.private_subnet_ids
}

output "alb_security_group_id" {
  value = module.network.alb_security_group_id
}

output "be_security_group_id" {
  value = module.network.be_security_group_id
}

output "rag_security_group_id" {
  value = module.network.rag_security_group_id
}

output "milvus_security_group_id" {
  value = module.network.milvus_security_group_id
}

output "rds_security_group_id" {
  value = module.network.rds_security_group_id
}

output "alb_dns_name" {
  description = "FE가 API 호출에 쓸 주소 (http://<이 값>)"
  value       = module.alb.dns_name
}

output "ecr_be_repository_url" {
  value = module.ecr_be.repository_url
}

output "ecr_rag_repository_url" {
  value = module.ecr_rag.repository_url
}

output "rds_endpoint" {
  value = module.rds.endpoint
}

output "redis_endpoint" {
  value = module.elasticache.redis_endpoint
}

output "milvus_private_ip" {
  value = module.milvus_ec2.private_ip
}

output "github_actions_deploy_role_arn" {
  description = ".github/workflows/deploy.yml의 role-to-assume 값으로 사용"
  value       = module.github_oidc.deploy_role_arn
}
