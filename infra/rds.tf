resource "aws_db_subnet_group" "main" {
  name       = "${local.name}-db"
  subnet_ids = aws_subnet.private[*].id

  tags = { Name = "${local.name}-db" }
}

# Enforces SSL/TLS in transit (rds.force_ssl) per §14.
resource "aws_db_parameter_group" "main" {
  name   = "${local.name}-pg16"
  family = "postgres16"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
}

resource "aws_db_instance" "main" {
  identifier     = "${local.name}-db"
  engine         = "postgres"
  engine_version = "16"

  instance_class    = var.db_instance_class
  allocated_storage = var.db_allocated_storage_gb
  storage_type      = "gp3"
  storage_encrypted = true
  kms_key_id        = aws_kms_key.main.arn

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.main.name

  # Not Aurora, Multi-AZ off — a 40-account portfolio does not justify the
  # cost or operational surface yet (BUILD-PROMPT.md §11).
  multi_az = false

  publicly_accessible = false
  skip_final_snapshot = var.environment != "production"
  deletion_protection = var.environment == "production"

  backup_retention_period = var.environment == "production" ? 7 : 1

  tags = { Name = "${local.name}-db" }
}
