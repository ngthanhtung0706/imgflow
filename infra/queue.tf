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

# Phụ trách: Phong – SQS + DLQ, và S3 event -> SQS
#
# Ảnh gốc vào bucket originals -> S3 gửi thông điệp vào hàng đợi chính.
# Worker xử lý lỗi quá 3 lần -> thông điệp tự chuyển sang DLQ (Quyền gắn alarm + SNS ở monitoring.tf).

resource "aws_sqs_queue" "dlq" {
  name                      = "imgflow-jobs-dlq"
  message_retention_seconds = 1209600 # 14 ngày
}

resource "aws_sqs_queue" "main" {
  name = "imgflow-jobs"

  # Phải lớn hơn thời gian xử lý tối đa 1 ảnh, nếu không ảnh bị xử lý 2 lần.
  # Tùng chỉnh số này nếu worker xử lý lâu hơn.
  visibility_timeout_seconds = 300

  receive_wait_time_seconds = 20 # long polling
  message_retention_seconds = 345600

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}

# Cho phép S3 (chỉ bucket originals của tài khoản này) gửi tin vào hàng đợi
data "aws_iam_policy_document" "queue_from_s3" {
  statement {
    sid       = "AllowS3SendMessage"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.main.arn]

    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_s3_bucket.originals.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.me.account_id]
    }
  }
}

resource "aws_sqs_queue_policy" "main" {
  queue_url = aws_sqs_queue.main.id
  policy    = data.aws_iam_policy_document.queue_from_s3.json
}

# Không đặt filter prefix: chỉ bucket originals có event nên không lo vòng lặp,
# và không phụ thuộc vào cách Tùng đặt tên key.
resource "aws_s3_bucket_notification" "originals" {
  bucket = aws_s3_bucket.originals.id

  queue {
    queue_arn = aws_sqs_queue.main.arn
    events    = ["s3:ObjectCreated:*"]
  }

  depends_on = [aws_sqs_queue_policy.main]
}

output "sqs_queue_url" {
  value = aws_sqs_queue.main.url
}

output "sqs_queue_arn" {
  value = aws_sqs_queue.main.arn
}

output "sqs_dlq_arn" {
  description = "Quyen dung de gan alarm DLQ"
  value       = aws_sqs_queue.dlq.arn
}