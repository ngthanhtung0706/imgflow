#!/usr/bin/env bash
# Dựng lại toàn bộ hạ tầng ImgFlow từ đầu (mục tiêu <= 45 phút)
set -euo pipefail

MULTI_AZ="${1:-false}" # Truyền "true" khi chạy demo thật để bật RDS Multi-AZ
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="${SCRIPT_DIR}/../infra"

echo "=== [1/4] Khoi tao Terraform ==="
cd "$INFRA_DIR"
terraform init

echo "=== [2/4] Dung ha tang (NAT=true, RDS=true, Multi-AZ=${MULTI_AZ}) ==="
terraform apply -auto-approve \
  -var="enable_nat=true" \
  -var="enable_rds=true" \
  -var="db_multi_az=${MULTI_AZ}"

echo "=== [3/4] Lam moi ASG Web va Worker de nhan endpoint moi ==="
aws autoscaling start-instance-refresh --region ap-southeast-2 --auto-scaling-group-name imgflow-web-asg || true
aws autoscaling start-instance-refresh --region ap-southeast-2 --auto-scaling-group-name imgflow-worker-asg || true

echo "=== [4/4] Hoan tat! Kiem tra URL truy cap ben duoi ==="
terraform output alb_dns_name
terraform output cloudfront_domain