# Phụ trách: Phong – Hạng mục 3 (>= 2 loại lưu trữ)
#
# CẦN LÀM:
# [ ] Bucket aws_s3_bucket.originals (ảnh gốc): chặn public, force_destroy = true,
#     CORS cho phép trình duyệt PUT bằng presigned URL,
#     lifecycle chuyển sang Standard-IA sau 30 ngày
# [ ] Bucket aws_s3_bucket.processed (ảnh đã xử lý): chặn public, force_destroy = true
# [ ] EFS (mã hoá) + mount target ở aws_subnet.worker[*].id, SG aws_security_group.efs.id
#     Đặt logo + font watermark lên EFS
#
# XONG KHI: upload được bằng presigned URL; worker ở 2 AZ cùng đọc được logo trên EFS.
