# ImgFlow – Nền tảng xử lý ảnh sản phẩm bất đồng bộ trên AWS

Bài tập lớn INT3319 – Điện toán đám mây. Region: **Sydney (ap-southeast-2)**.

Luồng: Web (ALB + ASG) cấp presigned URL → trình duyệt upload ảnh lên S3 →
S3 event → SQS → Worker (ASG, Pillow, đọc logo từ EFS) → S3 processed →
CloudFront. Trạng thái job lưu trong RDS PostgreSQL.

## Cấu trúc repo

```
imgflow/
├── infra/                 # Toàn bộ Terraform, chạy trong thư mục này
│   ├── providers.tf       # Thanh  – AWS provider, nơi lưu state
│   ├── variables.tf       # Thanh  – biến chung (region, bật/tắt NAT, RDS)
│   ├── network.tf         # Thanh  – VPC, 8 subnet, IGW, NAT, S3 endpoint   (ĐÃ CÓ CODE)
│   ├── security.tf        # Thanh  – security group                           (ĐÃ CÓ CODE)
│   ├── web.tf             # Thanh  – ALB, launch template, ASG web
│   ├── iam.tf             # Phong  – IAM role + instance profile web/worker
│   ├── storage.tf         # Phong  – 2 bucket S3, EFS
│   ├── queue.tf           # Phong  – SQS + DLQ, S3 event → SQS
│   ├── database.tf        # Phong  – RDS PostgreSQL, mật khẩu ở Secrets Manager
│   ├── cdn.tf             # Phong  – CloudFront + OAC
│   ├── worker.tf          # Tùng   – launch template, ASG worker, scaling theo SQS
│   ├── monitoring.tf      # Quyền  – dashboard, alarm, SNS email
│   └── outputs.tf         # Mỗi người thêm output của phần mình
├── app/
│   ├── common/            # Tùng   – cấu hình, DB, quy ước tên key S3 (web + worker dùng chung)
│   ├── web/               # Tùng   – web/API (đăng nhập, presign, trạng thái, gallery)
│   └── worker/            # Tùng   – worker Pillow
├── scripts/
│   ├── bootstrap-state.sh # Thanh  – tạo bucket lưu state (chạy 1 lần)
│   └── loadtest.py        # Quyền  – đẩy N ảnh để test co giãn
└── docs/
    ├── report/            # Cả nhóm – báo cáo, mỗi người một mục
    ├── cost/              # Quyền  – bảng chi phí, file xuất Pricing Calculator
    └── evidence/HM1..HM8/ # Ảnh chụp bằng chứng cho 8 hạng mục
```

Terraform đọc **tất cả** file `.tf` trong `infra/` như một file. Vì vậy:
- Mỗi người chỉ sửa file của mình.
- Muốn dùng thứ người khác tạo thì gọi thẳng tên, ví dụ `aws_subnet.worker[*].id`,
  `aws_security_group.rds.id`. Không cần module hay output phức tạp.

## Bắt đầu (mỗi người làm 1 lần)

1. Cài Terraform (>= 1.10), AWS CLI, Git.
2. Đăng nhập AWS trên máy, hoặc dùng AWS CloudShell ở region Sydney.
   Kiểm tra: `aws sts get-caller-identity`.
3. Clone repo:
   ```bash
   git clone <link repo>
   cd imgflow/infra
   terraform init
   ```

## Quy tắc chung

1. **Không push thẳng vào `main`.** Mỗi việc một branch (`ten/viec`, ví dụ `phong/rds`),
   mở Pull Request, 1 người khác duyệt rồi mới merge.
2. **Trước khi `terraform apply` luôn `git pull` nhánh `main`.** Cả nhóm dùng chung
   1 state: nếu máy bạn thiếu file của ai, Terraform sẽ đề nghị XOÁ phần của người đó.
3. **Đọc dòng `Plan: X to add, Y to change, Z to destroy` trước khi gõ yes.**
   Thấy destroy lạ thì gõ no và hỏi nhóm.
4. **Không bao giờ để access key, mật khẩu trong repo.**
5. **Không tạo tài nguyên bằng tay trên console.** Mọi thứ đi qua Terraform.
6. **Ai bật thì người đó tắt.** Cuối buổi chạy
   `terraform apply -var="enable_nat=false" -var="enable_rds=false"`
   (hoặc `terraform destroy` nếu nghỉ dài), báo vào group trước 23:30.

## Bật / tắt hạ tầng

```bash
cd infra
# Bật đủ để làm việc / demo
terraform apply -var="enable_nat=true" -var="enable_rds=true"
# Tắt phần tốn tiền theo giờ (giữ VPC, S3...)
terraform apply
```
