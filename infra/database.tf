# Phụ trách: Phong – Hạng mục 4, 5
#
# CẦN LÀM:
# [ ] DB subnet group từ aws_subnet.data[*].id
# [ ] RDS PostgreSQL db.t3.micro, 20 GB gp3, mã hoá, publicly_accessible = false,
#     SG aws_security_group.rds.id
# [ ] count = var.enable_rds ? 1 : 0 để tắt được khi không dùng
# [ ] manage_master_user_password = true (mật khẩu tự nằm trong Secrets Manager)
# [ ] skip_final_snapshot = true, deletion_protection = false
# [ ] Multi-AZ: để false khi đang làm, bật true từ 20/11 (demo)
#
# XONG KHI: từ máy web/worker kết nối được DB bằng mật khẩu lấy từ Secrets Manager.

# Phụ trách: Phong – Hạng mục 4 (RDS PostgreSQL, mật khẩu ở Secrets Manager)
#
# CẢNH BÁO: enable_rds = false sẽ XOÁ database (không giữ snapshot) => mất bảng và dữ liệu.
# Lần bật lại là database trống, cần chạy lại script tạo bảng.

variable "db_multi_az" {
  description = "Dev: false (re hon). Bat true gan ngay demo de chung minh failover"
  type        = bool
  default     = true
}

# Subnet group miễn phí nên luôn tạo
resource "aws_db_subnet_group" "main" {
  name        = "imgflow-db-subnet-group"
  description = "Data subnets for ImgFlow RDS"
  subnet_ids  = aws_subnet.data[*].id
}

resource "aws_db_instance" "main" {
  count      = var.enable_rds ? 1 : 0
  identifier = "imgflow-db"

  engine         = "postgres"
  instance_class = "db.t3.micro"

  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true
  # không đặt max_allocated_storage => tắt storage autoscaling

  db_name  = "imgflow"
  username = "postgres"

  # RDS tự sinh mật khẩu và lưu vào Secrets Manager: không có mật khẩu trong code hay state
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  multi_az               = var.db_multi_az

  backup_retention_period    = 1
  auto_minor_version_upgrade = true
  deletion_protection        = false
  skip_final_snapshot        = true
  apply_immediately          = true
}

output "rds_endpoint" {
  value = var.enable_rds ? aws_db_instance.main[0].address : null
}

output "rds_secret_arn" {
  description = "ARN secret mat khau DB, app doc luc chay"
  value       = var.enable_rds ? aws_db_instance.main[0].master_user_secret[0].secret_arn : null
}
