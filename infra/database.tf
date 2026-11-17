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
