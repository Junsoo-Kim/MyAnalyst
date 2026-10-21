# D9: 비밀 값은 Secrets Manager에 두고 ECS 태스크 정의의 secrets로 주입한다.
# Terraform은 시크릿(이름과 권한)만 만들고 값은 넣지 않는다. 값이 state에 남지 않게 하기 위해서다.
# 값을 넣는 명령은 infra/README.md "비밀 값 넣기" 참고. 값이 없으면 해당 태스크는 기동에 실패한다.
#
#   - OpenAI API 키: 미리 만든 시크릿의 ARN을 var.openai_api_key_secret_arn으로 받는다(기존 방식).
#   - DB 비밀번호: RDS가 관리하는 마스터 비밀번호 시크릿(manage_master_user_password).

resource "aws_secretsmanager_secret" "internal_gateway_token" {
  name        = "${local.name_prefix}/internal-gateway-token"
  description = "Shared secret api-gateway adds to forwarded requests (X-Internal-Token)"
  tags        = local.tags
}

resource "aws_secretsmanager_secret" "jwt_signing_key" {
  name        = "${local.name_prefix}/jwt-signing-key"
  description = "auth-service JWT signing key (RSA JWK JSON including the private key)"
  tags        = local.tags
}
