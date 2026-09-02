output "alb_dns_name" {
  description = "Public DNS name of the ALB — hit this at /health once applied and deployed."
  value       = aws_lb.main.dns_name
}

output "ecr_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  value = aws_ecs_service.api.name
}

output "github_deploy_role_arn" {
  description = "Set this as the AWS_ROLE_ARN GitHub Actions variable."
  value       = aws_iam_role.github_deploy.arn
}

output "db_credentials_secret_arn" {
  value = aws_secretsmanager_secret.db_credentials.arn
}

output "db_endpoint" {
  value     = aws_db_instance.main.address
  sensitive = false
}
