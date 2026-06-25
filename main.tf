terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region                      = "us-east-1"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  s3_use_path_style           = true

  endpoints {
    s3  = "http://localhost:4566"
    ec2 = "http://localhost:4566"
    sts = "http://localhost:4566"
  }
}

resource "aws_s3_bucket" "city_brain_storage" {
  bucket_prefix = "mini-city-brain-storage-"
  force_destroy = true
}

resource "aws_security_group" "api_sg" {
  name        = "mini-city-brain-sg"
  description = "Allow inbound web traffic to FastAPI"

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "api_server" {
  ami           = "ami-0c7217cdde317cfec"
  instance_type = "t2.micro"

  security_groups = [aws_security_group.api_sg.name]

  tags = {
    Name = "MiniCityBrain-Backend"
  }
}

output "s3_bucket_name" {
  value = aws_s3_bucket.city_brain_storage.id
}

output "ec2_public_ip" {
  value = aws_instance.api_server.public_ip
}
