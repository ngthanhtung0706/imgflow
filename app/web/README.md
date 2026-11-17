# Web/API – Phụ trách: Tùng (Quyền phụ giao diện)

CẦN LÀM:
- [ ] Đăng nhập shop demo (lưu bằng cookie có ký, KHÔNG lưu session trong RAM vì có 2 máy web)
- [ ] API tạo job PENDING trong RDS + trả presigned URL để trình duyệt PUT ảnh lên S3
- [ ] API xem trạng thái job; trang gallery tự cập nhật 2-3 giây/lần
- [ ] /healthz trả 200 (cho ALB kiểm tra)
- [ ] Đọc cấu hình từ biến môi trường; mật khẩu DB lấy từ Secrets Manager, không ghi vào code

XONG KHI: chọn 3 ảnh upload thì 3 ảnh lên bucket originals và có 3 job PENDING.
