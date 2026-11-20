# Giả định ước tính chi phí ImgFlow

Đơn vị USD. Chọn Sydney cho dịch vụ theo region. Điền ngày lập, link estimate, giá và số đo thực tế trước khi nộp. Các số giờ bên dưới là ví dụ đầu vào.

| Dịch vụ | Chạy cả tháng | Demo theo lịch mẫu | Dữ liệu cần bổ sung |
|---|---|---|---|
| EC2 web | 2 `t3.micro` × 730 giờ | 2 × 730 giờ nếu giữ ASG suốt tháng | EBS và thời gian tăng thêm nếu có |
| EC2 worker | 1 `t3.small` × 730 giờ, cộng giờ scale-out | Cùng baseline nếu giữ ASG, cộng giờ máy tăng tải thực tế | Giờ tăng tải = tổng giờ của từng máy bổ sung |
| ALB | 1 × 730 giờ | 1 × 730 giờ nếu vẫn giữ ALB | LCU dựa trên kết nối, byte và rule |
| NAT Gateway | 1 × 730 giờ | 1 × 12 giờ nếu bật 4 buổi, mỗi buổi 3 giờ | GB xử lý và public IPv4 theo thực tế |
| RDS | `db.t3.micro`, PostgreSQL, 20 GB gp3, 730 giờ | 12 giờ nếu thực sự tạo/xóa theo lịch mẫu | Mô hình Single-AZ hoặc Multi-AZ, storage và Secrets Manager |
| S3 | Originals và processed, theo dữ liệu lưu trong tháng | Theo số lượt upload thử nghiệm và thời gian giữ ảnh | GB lưu, PUT, GET, lifecycle và request |
| EFS | GB lưu trữ, throughput và backup theo cấu hình | Theo thời gian duy trì và mức sử dụng | Logo/font, throughput, backup |
| CloudFront | Theo khu vực người xem và GB tải | Theo lượt xem demo | HTTPS requests, cache và dữ liệu gửi tới người xem |
| SQS | Tổng request tháng | Theo số job và thời gian worker long polling | Send, receive, delete, retry, polling |
| CloudWatch và SNS | Dashboard, bốn alarm kể cả hai alarm scaling, thông báo | Theo tài nguyên giữ trong tháng và email dự kiến | Tính theo AWS Pricing Calculator, ghi rõ giả định |

Ví dụ cách nhập S3. Nếu dùng 201 upload, gồm 200 ảnh × 2 MiB và một file hỏng nhỏ, originals tăng khoảng 400 MiB. Nếu 4 biến thể của mỗi job DONE có tổng kích thước đo được 0,8 MiB, processed tăng khoảng 160 MiB. Đây là giả định minh họa, thay bằng số đo của ảnh mẫu.

| Kịch bản | Tổng ước tính USD/tháng | Link estimate | Tệp xuất |
|---|---:|---|---|
| Chạy cả tháng | [điền] | [điền] | [điền] |
| Demo theo lịch | [điền] | [điền] | [điền] |
