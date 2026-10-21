# ECS 서비스 목록. 로컬 docker-compose.yml과 같은 서비스, 같은 환경 변수 이름이다.
# 서비스끼리는 Service Connect DNS(http://<서비스 이름>:<포트>)로, EC2로 띄운 Kafka와 검색 데이터는
# Cloud Map에 등록한 DNS 이름(discovery.tf)으로 찾는다.

locals {
  namespace = module.ecs_cluster.namespace_name
  jdbc_base = "jdbc:postgresql://${module.rds.endpoint}:${module.rds.port}"

  on_demand_strategy = [{ capacity_provider = "FARGATE", weight = 1, base = 1 }]
  # 중단돼도 다시 하면 되는 연산(검색·LLM 호출·생성 워커): 온디맨드 1개 + 나머지 Spot.
  # 워커가 Spot 회수로 죽으면 lease 만료 후 generation-service가 재시도하고, 섹션 체크포인트는 태스크와 함께 사라진다.
  spot_strategy = [
    { capacity_provider = "FARGATE", weight = 1, base = 1 },
    { capacity_provider = "FARGATE_SPOT", weight = 4, base = 0 },
  ]

  kafka_env = {
    KAFKA_BOOTSTRAP_SERVERS = module.kafka_ec2.bootstrap_servers
  }
  redis_env = {
    REDIS_HOST = module.elasticache.redis_endpoint
    REDIS_PORT = tostring(module.elasticache.redis_port)
  }
  # Gateway가 넘기는 공유 비밀(D10). 값은 secrets.tf의 시크릿.
  internal_token_secret = {
    INTERNAL_GATEWAY_TOKEN = aws_secretsmanager_secret.internal_gateway_token.arn
  }
  openai_secret = {
    OPENAI_API_KEY = var.openai_api_key_secret_arn
  }

  # Java 서비스 공통: 컨테이너 포트 8080, 자기 database.
  java_db = {
    for name, db in {
      "user-service"       = "user_db"
      "generation-service" = "generation_db"
      "report-service"     = "report_db"
      "dictionary-service" = "dictionary_db"
      "chat-service"       = "chat_db"
    } :
    name => {
      environment = {
        SPRING_DATASOURCE_URL      = "${local.jdbc_base}/${db}"
        SPRING_DATASOURCE_USERNAME = "postgres"
      }
      secrets = {
        SPRING_DATASOURCE_PASSWORD = "${module.rds.master_user_secret_arn}:password::"
      }
    }
  }

  services = {
    "api-gateway" = {
      port = 8080, cpu = 512, memory = 1024, public = true, spot = false, min_capacity = 1, max_capacity = 4
      environment = merge(local.redis_env, {
        PORT                     = "8080"
        AUTH_SERVICE_URL         = "http://auth-service:8080"
        USER_SERVICE_URL         = "http://user-service:8080"
        GENERATION_SERVICE_URL   = "http://generation-service:8080"
        REPORT_SERVICE_URL       = "http://report-service:8080"
        NOTIFICATION_SERVICE_URL = "http://notification-service:8080"
        DICTIONARY_SERVICE_URL   = "http://dictionary-service:8080"
        CHAT_SERVICE_URL         = "http://chat-service:8080"
        MARKET_DATA_SERVICE_URL  = "http://market-data:8000"
        CORS_ALLOWED_ORIGINS     = var.fe_origin
      })
      secrets = local.internal_token_secret
    }
    "auth-service" = {
      port = 8080, cpu = 256, memory = 512, public = false, spot = false, min_capacity = 1, max_capacity = 2
      environment = merge(local.redis_env, {
        PORT             = "8080"
        USER_SERVICE_URL = "http://user-service:8080"
      })
      # D9: 서명 키는 볼륨 대신 Secrets Manager에서 받는다(태스크가 여러 개여도 같은 키).
      secrets = merge(local.internal_token_secret, {
        JWT_SIGNING_KEY = aws_secretsmanager_secret.jwt_signing_key.arn
      })
    }
    "user-service" = {
      port        = 8080, cpu = 256, memory = 512, public = false, spot = false, min_capacity = 1, max_capacity = 2
      environment = merge(local.java_db["user-service"].environment, { PORT = "8080" })
      secrets     = merge(local.java_db["user-service"].secrets, local.internal_token_secret)
    }
    "generation-service" = {
      port        = 8080, cpu = 512, memory = 1024, public = false, spot = false, min_capacity = 1, max_capacity = 3
      environment = merge(local.java_db["generation-service"].environment, local.kafka_env, { PORT = "8080" })
      secrets     = merge(local.java_db["generation-service"].secrets, local.internal_token_secret)
    }
    "report-service" = {
      port        = 8080, cpu = 512, memory = 1024, public = false, spot = false, min_capacity = 1, max_capacity = 3
      environment = merge(local.java_db["report-service"].environment, local.kafka_env, { PORT = "8080" })
      secrets     = merge(local.java_db["report-service"].secrets, local.internal_token_secret)
    }
    "notification-service" = {
      port        = 8080, cpu = 256, memory = 512, public = false, spot = false, min_capacity = 1, max_capacity = 3
      environment = merge(local.kafka_env, { PORT = "8080" })
      secrets     = local.internal_token_secret
    }
    "dictionary-service" = {
      port        = 8080, cpu = 256, memory = 512, public = false, spot = false, min_capacity = 1, max_capacity = 2
      environment = merge(local.java_db["dictionary-service"].environment, local.kafka_env, { PORT = "8080" })
      secrets     = merge(local.java_db["dictionary-service"].secrets, local.internal_token_secret)
    }
    "chat-service" = {
      port = 8080, cpu = 256, memory = 512, public = false, spot = false, min_capacity = 1, max_capacity = 3
      environment = merge(local.java_db["chat-service"].environment, local.kafka_env, {
        PORT            = "8080"
        QA_SERVICE_URL  = "http://qa:8000"
        STT_SERVICE_URL = "http://stt:8000"
      })
      secrets = merge(local.java_db["chat-service"].secrets, local.internal_token_secret)
    }
    "knowledge" = {
      port = 8000, cpu = 2048, memory = 4096, public = false, spot = true, min_capacity = 1, max_capacity = 4
      environment = {
        MILVUS_HOST     = "search-data.${local.namespace}"
        MILVUS_PORT     = "19530"
        OPENSEARCH_HOST = "search-data.${local.namespace}"
        OPENSEARCH_PORT = "9200"
      }
      secrets = {}
    }
    # 생성 워커는 HTTP API가 없다. Service Connect에는 지표 포트(9100)를 등록한다.
    "generation-worker" = {
      port = 9100, cpu = 512, memory = 1024, public = false, spot = true, min_capacity = 1, max_capacity = 3
      environment = merge(local.kafka_env, {
        KNOWLEDGE_SERVICE_URL = "http://knowledge:8000"
        LLM_MODEL             = var.llm_model
      })
      secrets = local.openai_secret
    }
    "market-data" = {
      port        = 8000, cpu = 256, memory = 512, public = false, spot = false, min_capacity = 1, max_capacity = 2
      environment = local.redis_env
      secrets     = {}
    }
    "qa" = {
      port        = 8000, cpu = 256, memory = 512, public = false, spot = true, min_capacity = 1, max_capacity = 3
      environment = { LLM_MODEL = var.llm_model }
      secrets     = local.openai_secret
    }
    "stt" = {
      port        = 8000, cpu = 256, memory = 512, public = false, spot = true, min_capacity = 1, max_capacity = 2
      environment = {}
      secrets     = local.openai_secret
    }
  }
}
