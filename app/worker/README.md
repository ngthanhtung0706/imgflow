# Worker – Phụ trách: Tùng

Lấy message S3 event từ SQS, tạo 4 bản ảnh có watermark, ghi lên bucket processed và cập nhật job.
Code dùng chung với web nằm ở `app/common/`.

CẦN LÀM:
- [x] Long polling SQS (20s); bỏ qua message s3:TestEvent
- [x] Tải ảnh gốc, tạo 4 bản: full (nén), 1080 px, 600 px, thumb 200 px, có watermark
      (logo `logo.png` + font `font.ttf` đọc từ /mnt/efs; thiếu thì dùng chữ "ImgFlow" mặc định)
- [x] Ghi vào bucket processed theo key {shop_id}/{job_id}/{ten}.jpg, cập nhật job DONE,
      rồi mới xoá message
- [x] Lỗi: retry nhanh (đổi visibility về `RETRY_VISIBILITY`); lần nhận thứ 3 thì job FAILED
      (message tự sang DLQ). File hỏng thì FAILED ngay và xoá message
- [x] Test tự động (`test_worker.py`, moto + Postgres thật): 6 test qua
- [ ] Chạy thử với SQS/S3 thật (chưa có hạ tầng của Phong)
- [ ] Script cài đặt + systemd cho EC2, `worker.tf` (launch template, ASG, scaling theo SQS)

XONG KHI: 1 ảnh vào thì ra đủ 4 file có watermark; file hỏng nằm trong DLQ.

## Chạy trên laptop

```bash
cd app
pip install -r worker/requirements.txt
# .env cần thêm QUEUE_URL, ORIGINALS_BUCKET, PROCESSED_BUCKET (xem .env.example)
python -m worker.worker
```

Chạy test (không cần AWS thật, chỉ cần Postgres như web):

```bash
pip install pytest "moto[s3,sqs]"
python -m pytest worker -q
```

## Biến môi trường

Như web (xem `app/web/README.md`) và thêm:

| Biến | Ý nghĩa |
|---|---|
| `QUEUE_URL` | URL queue jobs (output của Phong) |
| `EFS_ROOT` | nơi mount EFS, mặc định `/mnt/efs` |
| `MAX_RECEIVES`, `RETRY_VISIBILITY` | mặc định 3 và 10s; `MAX_RECEIVES` phải khớp `maxReceiveCount` ở `queue.tf` |

Quyền IAM worker cần: `sqs:ReceiveMessage/DeleteMessage/ChangeMessageVisibility` trên queue,
`s3:GetObject` trên originals, `s3:PutObject` trên processed, `secretsmanager:GetSecretValue` trên secret DB.
