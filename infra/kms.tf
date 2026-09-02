# Customer-managed key per §14. One key for this build's stateful services
# (RDS, Secrets Manager now; S3 joins when object storage is introduced in
# a later phase) — separate keys per service are not worth the operational
# overhead at this scale, but a single Terraform-managed CMK means nothing
# rides on the AWS-managed default key, and rotation is explicit.
resource "aws_kms_key" "main" {
  description             = "${var.project_name} ${var.environment} CMK for RDS + Secrets Manager"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_kms_alias" "main" {
  name          = "alias/${var.project_name}-${var.environment}"
  target_key_id = aws_kms_key.main.key_id
}
