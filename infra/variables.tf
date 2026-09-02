variable "aws_region" {
  description = "Single AWS region for this build, per BUILD-PROMPT.md §11."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short name used as a prefix for all resource names and tags."
  type        = string
  default     = "polst-cs"
}

variable "environment" {
  description = "Deployment environment: staging or production. Local dev never touches AWS."
  type        = string
  default     = "staging"

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be \"staging\" or \"production\"."
  }
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "availability_zone_count" {
  description = "Number of AZs to spread public/private subnets across."
  type        = number
  default     = 2
}

variable "db_name" {
  description = "Name of the application Postgres database."
  type        = string
  default     = "polst_cs"
}

variable "db_username" {
  description = "Master username for RDS. Password is generated and stored in Secrets Manager, never set here."
  type        = string
  default     = "polst_app"
}

variable "db_instance_class" {
  description = "RDS instance class. Small on purpose — a 40-account portfolio does not need much (BUILD-PROMPT.md §11)."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage_gb" {
  type    = number
  default = 20
}

variable "container_port" {
  description = "Port the FastAPI app listens on inside the container."
  type        = number
  default     = 8000
}

variable "container_image" {
  description = "Full ECR image URI (with tag) for the API service. Defaults to a placeholder so `terraform plan` runs before the first image is ever pushed; CI updates this via a task-definition-only deploy, not by re-running this whole config."
  type        = string
  default     = null
}

variable "fargate_cpu" {
  type    = number
  default = 256
}

variable "fargate_memory" {
  type    = number
  default = 512
}

variable "desired_count" {
  description = "Number of Fargate tasks to run. One is enough at this stage."
  type        = number
  default     = 1
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "github_repository" {
  description = "GitHub \"owner/repo\" allowed to assume the deploy role via OIDC."
  type        = string
  default     = "aravindnunsavathu/polst-customer-success-agent"
}
