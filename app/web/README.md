# Web/API – Phụ trách: Tùng

Flask + gunicorn, cổng 8000. Code dùng chung với worker nằm ở `app/common/`
(cấu hình, kết nối DB, quy ước tên key S3 – xem `docs/contracts.md`).

CẦN LÀM:
- [x] Đăng nhập shop (cookie có ký, KHÔNG lưu session trong RAM vì có 2 máy web) + `/register` tạo shop
- [x] API tạo job PENDING trong RDS + trả presigned URL để trình duyệt PUT ảnh lên S3 (`POST /api/uploads`)
- [x] API xem trạng thái job (`GET /api/jobs`, `/api/jobs/<id>`); gallery tự cập nhật 3 giây/lần
- [x] /healthz trả 200 (cho ALB kiểm tra, không đụng DB)
- [x] Đọc cấu hình từ biến môi trường; mật khẩu DB lấy từ Secrets Manager, không ghi vào code
- [ ] Chạy thử trên laptop với bucket + Postgres thật (chưa test)
- [ ] Script cài đặt + systemd cho EC2 (chờ Thanh chốt cách đưa code lên máy, task 2.5)

XONG KHI: chọn 3 ảnh upload thì 3 ảnh lên bucket originals và có 3 job PENDING.

## Chạy trên laptop

```bash
cd app
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r web/requirements.txt
cp .env.example .env          # điền tên bucket; AWS credentials lấy từ `aws configure sso` / env, không ghi vào repo
flask --app web.app run --port 8000 --debug
```

Cần Postgres cục bộ (`DATABASE_URL` trong `.env`). Bảng tự tạo ở request đầu tiên.

## Biến môi trường (trên EC2 do user data ghi)

| Biến | Ý nghĩa | Lấy từ |
|---|---|---|
| `ORIGINALS_BUCKET` | bucket ảnh gốc | Phong: output `originals_bucket` |
| `PROCESSED_BUCKET` | bucket ảnh đã xử lý | Phong: output `processed_bucket` |
| `CDN_DOMAIN` | domain CloudFront | Phong: output `cloudfront_domain` |
| `DB_HOST`, `DB_SECRET_ARN` | RDS + secret mật khẩu (RDS tự quản lý) | Phong: output `rds_endpoint`, secret ARN |

Web cần quyền IAM: `s3:PutObject` trên originals, `secretsmanager:GetSecretValue` trên secret DB
(đã có trong `iam.tf` của Phong). Nếu `CDN_DOMAIN` trống, web ký URL xem ảnh bằng presigned GET và
cần thêm `s3:GetObject` trên processed – chỉ dùng khi chạy laptop.
