# Giám sát, kiểm thử tải, chi phí và kịch bản demo

## HM7 — Giám sát và cảnh báo

CloudWatch dashboard theo dõi SQS chính, DLQ, số máy và CPU web/worker, lỗi 5xx và CPU RDS khi database được bật. Alarm DLQ dùng số message visible với ngưỡng 1, chu kỳ 60 giây. Alarm ALB đếm lỗi 5xx do ALB phát sinh với ngưỡng 5 trong chu kỳ 300 giây. Hai alarm gửi thông báo qua SNS.

| Mốc kiểm thử | Giá trị đo được | Minh chứng |
|---|---|---|
| Số email đã xác nhận SNS | [điền] | [điền] |
| Job ảnh hỏng chuyển FAILED | [điền thời điểm UTC] | [điền] |
| Gửi sự kiện redrive giả lập | [điền thời điểm UTC] | [điền] |
| DLQ có message | [điền thời điểm UTC] | [điền] |
| Alarm chuyển ALARM | [điền thời điểm UTC] | [điền] |
| Nhận email | [điền thời điểm UTC] | [điền] |

## Bằng chứng tải cho HM6

| Chỉ số | Lần chạy 200 ảnh + 1 lỗi |
|---|---|
| Size và độ phân giải ảnh | [điền] |
| Số luồng và ID lần chạy | [điền] |
| Thời gian cấp URL và PUT | [điền] |
| PUT thành công / tổng | [điền] |
| DONE, FAILED, chưa kết thúc | [điền] |
| Backlog visible cao nhất | [điền] |
| Worker Desired/InService trước, trong, sau | [điền] |
| Thời điểm scale-out và scale-in | [điền từ ASG Activity] |

## HM8 — Chi phí và demo

1. Mở gallery, trình bày một job DONE và bốn bản ảnh trên CloudFront.
2. Trình bày log của đợt 200 ảnh, đồ thị queue và ASG Activity theo cùng khoảng thời gian.
3. Mở job ảnh hỏng, rồi trình bày ca redrive giả lập, alarm history và email SNS tương ứng.
4. Mở hai estimate. So sánh giờ chạy và các dịch vụ còn phát sinh khi chỉ tắt RDS/NAT.

Ngày lập estimate, tổng hai kịch bản và chênh lệch: [điền theo Pricing Calculator]. Dẫn tới bảng giả định tại [docs/cost/assumptions.md](../cost/assumptions.md).
