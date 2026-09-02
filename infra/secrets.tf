resource "random_password" "db" {
  length  = 32
  special = false # avoid characters that need URL-encoding in a Postgres DSN
}

resource "aws_secretsmanager_secret" "db_credentials" {
  name       = "${var.project_name}/${var.environment}/db-credentials"
  kms_key_id = aws_kms_key.main.arn
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.db.result
    dbname   = var.db_name
    host     = aws_db_instance.main.address
    port     = aws_db_instance.main.port
  })
}

# Non-secret config (model choice, weights, thresholds per §11) lands here
# starting in Phase 2 alongside the metrics engine. One placeholder now to
# establish the naming convention: /{project}/{environment}/{key}.
resource "aws_ssm_parameter" "log_level" {
  name  = "/${var.project_name}/${var.environment}/log_level"
  type  = "String"
  value = "INFO"
}
