# app – Code ứng dụng ImgFlow

Phụ trách: Tùng. Hạ tầng AWS nằm ở `infra/`, thư mục này chỉ chứa code Python chạy trên EC2.

## Có gì trong thư mục này

```
app/
├── common/          # Code dùng chung cho web và worker
│   ├── config.py    #   đọc cấu hình từ biến môi trường / file .env, lấy mật khẩu DB từ Secrets Manager
│   ├── db.py        #   kết nối PostgreSQL và tạo bảng (shops, products, images, jobs)
│   └── naming.py    #   quy ước tên key S3 và 4 bản ảnh (full, 1080, 600, thumb)
├── web/             # Web + API (Flask, chạy bằng gunicorn, cổng 8000)
│   ├── app.py       #   đăng nhập, tạo job + presigned URL, xem trạng thái job, /healthz
│   ├── templates/   #   trang HTML (login, register, gallery, lỗi)
│   └── static/      #   CSS và JavaScript của gallery
├── worker/          # Worker xử lý ảnh nền (Pillow)
│   ├── worker.py    #   lấy message từ SQS, tạo 4 bản ảnh có watermark, cập nhật job
│   └── test_worker.py # test tự động bằng moto + Postgres thật
├── .env.example     # Mẫu cấu hình để chạy trên laptop (copy thành .env)
└── README.md
```

Mỗi phần có README riêng nói chi tiết: [web](web/README.md), [worker](worker/README.md).

## Luồng hoạt động

```
Trình duyệt ──(1) xin upload──▶ web ──▶ RDS: tạo job PENDING
     │                           │
     │◀──── presigned URL ───────┘
     │
     └─(2) PUT ảnh──▶ S3 originals ──(S3 event)──▶ SQS ──▶ worker
                                                              │ (3) tạo 4 bản + watermark
                                          S3 processed ◀──────┤
                                          RDS: job DONE ◀─────┘
Trình duyệt ◀──(4) gallery hỏi trạng thái 3 giây/lần, ảnh lấy qua CloudFront
```

Web không nhận file ảnh, ảnh đi thẳng từ trình duyệt lên S3. Web và worker không gọi nhau,
chúng chỉ liên lạc qua RDS (trạng thái job) và SQS (báo có ảnh mới).

## Chạy trên laptop

Cần Python 3.12, Docker (cho Postgres) và AWS credentials nếu muốn upload lên S3 thật.

```bash
docker run -d --name imgflow-pg -p 5432:5432 -e POSTGRES_PASSWORD=dev postgres:16

cd app
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r web/requirements.txt -r worker/requirements.txt
cp .env.example .env                                  # điền tên bucket, QUEUE_URL nếu có

flask --app web.app run --port 8000 --debug           # web: http://localhost:8000
python -m worker.worker                               # worker (cần QUEUE_URL + AWS thật)
python -m pytest worker -q                            # test worker (pip install pytest "moto[s3,sqs]")
```

## Trạng thái hiện tại

- Web và worker đã viết xong và test cục bộ (API web chạy được với Postgres, worker 6/6 test qua).
- Chưa thử với S3/SQS thật vì hạ tầng (`storage.tf`, `queue.tf`, `database.tf`) đang chờ Phong.
- Chưa có script cài lên EC2 và `worker.tf`.
