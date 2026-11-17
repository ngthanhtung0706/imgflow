#!/usr/bin/env bash
# Thanh chạy 1 lần duy nhất, TRƯỚC khi ai chạy terraform init.
# Tạo bucket S3 lưu Terraform state chung cho cả nhóm, ở Sydney.
# Sau khi chạy xong: sửa tên bucket trong infra/providers.tf cho khớp.
set -e
REGION=ap-southeast-2
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="imgflow-tfstate-${ACCOUNT}"

aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
  --create-bucket-configuration LocationConstraint="$REGION"
aws s3api put-bucket-versioning --bucket "$BUCKET" \
  --versioning-configuration Status=Enabled

echo "Da tao bucket: $BUCKET"
