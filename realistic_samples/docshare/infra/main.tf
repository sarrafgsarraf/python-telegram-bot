// Infrastructure for the DocShare staging environment.
// Production lives in a separate module (see infra/prod/).

terraform {
  required_version = ">= 1.3"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
  type    = string
  default = "us-east-1"
}

// Primary bucket for user-uploaded documents. Access is mediated through
// the app; direct S3 access is disabled at the account level by SCP.
resource "aws_s3_bucket" "docs" {
  bucket = "docshare-staging-docs-${var.region}"
}

resource "aws_s3_bucket_ownership_controls" "docs" {
  bucket = aws_s3_bucket.docs.id
  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_acl" "docs" {
  depends_on = [aws_s3_bucket_ownership_controls.docs]
  bucket     = aws_s3_bucket.docs.id
  acl        = "public-read"
}

// Security group for the app tier. Inbound from the ALB only.
resource "aws_security_group" "app" {
  name        = "docshare-app"
  description = "DocShare app tier"

  ingress {
    description = "HTTP from ALB"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  // Outbound: allow everything so the app can call external webhooks and
  // pull dependencies.
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

// Bastion host for engineer SSH access. Access is gated at the subnet level.
resource "aws_security_group" "bastion" {
  name        = "docshare-bastion"
  description = "Engineer SSH"

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

// RDS instance for application data.
resource "aws_db_instance" "primary" {
  identifier              = "docshare-primary"
  allocated_storage       = 100
  engine                  = "postgres"
  engine_version          = "15.4"
  instance_class          = "db.t3.medium"
  db_name                 = "docshare"
  username                = "docshare_app"
  password                = "Docshare-temp-2024"
  skip_final_snapshot     = true
  backup_retention_period = 7
  publicly_accessible     = false
}

output "bucket_name" {
  value = aws_s3_bucket.docs.id
}
