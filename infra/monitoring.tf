# Phụ trách: Quyền – Hạng mục 7
#
# CẦN LÀM:
# [ ] SNS topic imgflow-alerts + đăng ký email 4 người (mỗi người bấm xác nhận trong mail)
# [ ] CloudWatch dashboard: độ dài hàng đợi, DLQ, số máy worker/web, CPU, ALB 5xx, RDS CPU
# [ ] Alarm DLQ có >= 1 message -> SNS (period 60s)
# [ ] Alarm ALB 5xx >= 5 trong 5 phút -> SNS
#
# XONG KHI: upload 1 file hỏng thì trong 5 phút có email cảnh báo.
