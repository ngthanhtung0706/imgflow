# Phụ trách: Phong (Tùng chốt tham số và review) – Hạng mục 6, 7
#
# CẦN LÀM:
# [ ] SQS aws_sqs_queue.dlq (giữ 4 ngày)
# [ ] SQS aws_sqs_queue.jobs: visibility timeout 60s, long polling 20s,
#     redrive sang DLQ sau 3 lần nhận
# [ ] Queue policy cho phép s3.amazonaws.com gửi vào (điều kiện SourceArn = bucket originals)
# [ ] aws_s3_bucket_notification: ObjectCreated trên bucket originals -> SQS jobs
#
# XONG KHI: upload 1 file vào originals thì thấy 1 message trong queue.
