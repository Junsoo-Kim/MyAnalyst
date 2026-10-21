output "vpc_id" {
  value = module.network.vpc_id
}

output "private_subnet_ids" {
  value = module.network.private_subnet_ids
}

output "alb_dns_name" {
  description = "FE가 API 호출에 쓸 주소 (http://<이 값>). 받는 것은 api-gateway 하나다."
  value       = module.alb.dns_name
}

output "ecr_repository_urls" {
  description = "서비스 이름 -> ECR 리포지토리 URL"
  value       = { for name, repo in module.ecr : name => repo.repository_url }
}

output "rds_endpoint" {
  value = module.rds.endpoint
}

output "redis_endpoint" {
  value = module.elasticache.redis_endpoint
}

output "kafka_bootstrap_servers" {
  value = module.kafka_ec2.bootstrap_servers
}

output "search_data_private_ip" {
  value = module.milvus_ec2.private_ip
}

output "secret_arns" {
  description = "값을 직접 넣어야 하는 시크릿 (infra/README.md \"비밀 값 넣기\")"
  value = {
    internal_gateway_token = aws_secretsmanager_secret.internal_gateway_token.arn
    jwt_signing_key        = aws_secretsmanager_secret.jwt_signing_key.arn
  }
}

output "database_init_command" {
  description = "서비스별 database를 만드는 일회성 태스크 실행 명령 (여러 번 실행해도 된다)"
  value = join(" ", [
    "aws ecs run-task",
    "--cluster ${module.ecs_cluster.cluster_name}",
    "--task-definition ${aws_ecs_task_definition.database_init.family}",
    "--launch-type FARGATE",
    "--network-configuration 'awsvpcConfiguration={subnets=[${join(",", module.network.private_subnet_ids)}],securityGroups=[${module.network.services_security_group_id}],assignPublicIp=DISABLED}'",
  ])
}

output "github_actions_deploy_role_arn" {
  description = ".github/workflows/deploy.yml의 role-to-assume 값으로 사용"
  value       = module.github_oidc.deploy_role_arn
}
