# EC2로 띄운 상태 저장 계층을 ECS Service Connect와 같은 Cloud Map 네임스페이스에 DNS 이름으로 등록한다.
#   kafka.<namespace>        → Kafka 브로커 (advertised listener도 이 이름)
#   search-data.<namespace>  → Milvus(19530), OpenSearch(9200)
# 서비스는 IP 대신 이 이름을 쓰므로 인스턴스가 바뀌어도 태스크 정의를 고칠 필요가 없다.

resource "aws_service_discovery_service" "ec2" {
  for_each = toset(["kafka", "search-data"])

  name = each.key

  dns_config {
    namespace_id   = module.ecs_cluster.namespace_id
    routing_policy = "MULTIVALUE"

    dns_records {
      type = "A"
      ttl  = 10
    }
  }

  tags = local.tags
}

resource "aws_service_discovery_instance" "kafka" {
  instance_id = module.kafka_ec2.instance_id
  service_id  = aws_service_discovery_service.ec2["kafka"].id

  attributes = {
    AWS_INSTANCE_IPV4 = module.kafka_ec2.private_ip
  }
}

resource "aws_service_discovery_instance" "search_data" {
  instance_id = module.milvus_ec2.instance_id
  service_id  = aws_service_discovery_service.ec2["search-data"].id

  attributes = {
    AWS_INSTANCE_IPV4 = module.milvus_ec2.private_ip
  }
}
