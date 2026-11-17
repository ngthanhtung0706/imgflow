# Phụ trách: Thanh
terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # State dùng chung cả nhóm, có khoá: 2 người không thể apply cùng lúc.
  # Bucket do scripts/bootstrap-state.sh tạo. Tên bucket = imgflow-tfstate-<account id>.
  backend "s3" {
    bucket       = "imgflow-tfstate-016170038020"
    key          = "imgflow.tfstate"
    region       = "ap-southeast-2"
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = { Project = "ImgFlow" }
  }
}
