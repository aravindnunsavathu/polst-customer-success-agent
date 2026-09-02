resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.name}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_cluster" "main" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = "disabled" # turn on if/when portfolio-scale traffic makes it worth the extra cost
  }
}

locals {
  # Placeholder image so the very first `terraform apply` — before CI has
  # ever pushed a real image to the ECR repo created in this same config —
  # has something valid to reference. The task will not pass the /health
  # check on this image; that's expected. Push a real image via CI
  # immediately after the first apply (see infra/README.md).
  container_image = coalesce(var.container_image, "public.ecr.aws/docker/library/nginx:1.27-alpine")
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.fargate_cpu
  memory                   = var.fargate_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = local.container_image
      essential = true
      portMappings = [
        { containerPort = var.container_port, protocol = "tcp" }
      ]
      secrets = [
        {
          name      = "DB_CREDENTIALS"
          valueFrom = aws_secretsmanager_secret.db_credentials.arn
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "api" {
  name            = "${local.name}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.ecs_service.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = var.container_port
  }

  # Give the placeholder-image bootstrap case room to fail health checks
  # without ECS immediately cycling the task.
  health_check_grace_period_seconds = 60

  depends_on = [aws_lb_listener.http]

  lifecycle {
    ignore_changes = [task_definition] # CI updates this directly; don't fight it on the next `terraform apply`
  }
}
