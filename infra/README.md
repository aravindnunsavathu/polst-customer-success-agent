# Infrastructure — Phase 0

Terraform for the Phase 0 slice of BUILD-PROMPT.md §12: VPC, RDS Postgres, ECR, one
ECS Fargate service behind an ALB, Secrets Manager, and the IAM wiring GitHub Actions
needs to deploy without long-lived AWS access keys.

**This has been authored but not applied.** No AWS credentials were available in the
build environment, and `terraform apply` is real billed spend — that's your call to
make, not mine. Everything below is what to do when you're ready.

## What's included

- VPC: 2 public + 2 private subnets across 2 AZs, one NAT gateway (not one per AZ —
  a deliberate cost/availability trade-off at this stage)
- Security groups: internet → ALB (port 80 only) → ECS (container port only) → RDS
  (5432 only). Nothing else is open to `0.0.0.0/0`.
- RDS Postgres 16, private subnets, not publicly accessible, Multi-AZ off, KMS-encrypted,
  `rds.force_ssl` enforced
- A customer-managed KMS key for RDS + Secrets Manager
- ECR repo with scan-on-push and a lifecycle policy (expire untagged after 14 days,
  keep the last 20 tagged images)
- ECS Fargate cluster, task definition, and service (1 task) behind an ALB
- Separate ECS **execution** role (pull image, write logs, read the DB secret) and
  **task** role (empty for now — future phases attach narrowly scoped app permissions
  here, per §14's "ingestion worker cannot read tables it doesn't need")
- GitHub Actions OIDC provider + a deploy role scoped to
  `aravindnunsavathu/polst-customer-success-agent` on the `main` branch only —
  no AWS access keys stored anywhere

## What's deliberately NOT included yet

Out of Phase 0's stated scope (§12: "VPC, RDS, ECR, one Fargate service, secrets, and
a CI pipeline... do not spend more than a day here"). These land with the phases that
actually need them:

- SES, SQS, EventBridge Scheduler — arrive with ingestion/actions (Phase 1/3)
- S3 buckets, CloudFront/Amplify — arrive when value-doc evidence and the console exist
- CloudTrail, account-level budget alarms — account-wide security/cost baseline from
  §14, not tied to this one service; do this as its own pass before real customer data
  ever touches this account
- HTTPS on the ALB — HTTP-only placeholder is fine for a synthetic-data demo; add an
  ACM certificate before anything real flows through it
- Remote Terraform state (S3 + DynamoDB lock table) — state is local for now, which is
  fine for one engineer on one machine; migrate before that stops being true

## Prerequisites

- An AWS account and credentials with permission to create the resources above
- Terraform >= 1.5 (`terraform version` — 1.15.2 was used to author this)
- `terraform.tfvars` copied from `terraform.tfvars.example` and adjusted

## Applying

```
cd infra
terraform init
terraform validate
terraform plan
terraform apply
```

### Bootstrap sequence (chicken-and-egg on the first apply)

The ECS task definition needs *some* image to reference, but the ECR repo this same
config creates is empty until CI pushes to it. The default `container_image` is a
public placeholder (`nginx`) that will **fail the `/health` check** — that's expected,
not a bug. Sequence:

1. `terraform apply` — creates everything, service comes up with the placeholder image
   showing unhealthy targets
2. Push to `main` — CI builds the real image, pushes to ECR, and updates the running
   task definition directly (Terraform is told to `ignore_changes` on the task
   definition for exactly this reason — it does not fight CI's deploys)
3. `curl http://$(terraform output -raw alb_dns_name)/health` should now return
   `{"status": "ok"}`

### After applying, set these as GitHub Actions repository variables

| Variable | Value |
|---|---|
| `AWS_ROLE_ARN` | `terraform output github_deploy_role_arn` |
| `AWS_REGION` | `us-east-1` |
| `ECR_REPOSITORY` | `terraform output ecr_repository_url` |
| `ECS_CLUSTER` | `terraform output ecs_cluster_name` |
| `ECS_SERVICE` | `terraform output ecs_service_name` |

## Migrations

Per §11, database migrations run as a separate task before deploy, never on container
start. There's no schema yet (that's Phase 1) — this note is here so the CI pipeline's
shape doesn't need revisiting when Alembic shows up.
