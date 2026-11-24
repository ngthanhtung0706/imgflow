#!/usr/bin/env bash
# Che do "idle": tat NAT + RDS (giu VPC/ALB/S3, chi phi cuc thap)
# Che do "destroy": xoa toan bo ha tang (0$ chi phi, tru S3 state)
set -euo pipefail

MODE="${1:-idle}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="${SCRIPT_DIR}/../infra"

cd "$INFRA_DIR"
if [ "$MODE" = "destroy" ]; then
  echo "=== Xoa toan bo ha tang AWS (tru S3 tfstate) ==="
  terraform destroy -auto-approve \
    -var="enable_nat=false" \
    -var="enable_rds=false"
else
  echo "=== Tat NAT Gateway va RDS Database de tiet kiem credits ==="
  terraform apply -auto-approve \
    -var="enable_nat=false" \
    -var="enable_rds=false"
fi