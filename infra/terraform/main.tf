terraform {
  required_version = ">= 1.15.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.22.1"
    }
  }
}

# Every call goes to the local AWS emulator. There is no real-cloud path here.
provider "aws" {
  region     = var.region
  access_key = "test"
  secret_key = "test"

  s3_use_path_style           = true
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  skip_region_validation      = true

  endpoints {
    s3  = var.endpoint_url
    sqs = var.endpoint_url
  }
}

resource "aws_s3_bucket" "raw" {
  bucket = var.raw_bucket
}

resource "aws_s3_bucket" "curated" {
  bucket = var.curated_bucket
}

resource "aws_sqs_queue" "dead_letter" {
  name                      = var.dead_letter_queue_name
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "ingest" {
  name                       = var.ingest_queue_name
  visibility_timeout_seconds = var.visibility_timeout_seconds

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter.arn
    maxReceiveCount     = 3
  })
}
