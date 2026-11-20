# Phụ trách: Phong – Hạng mục 5 (IAM role, không nhúng khoá)
# LÀM ĐẦU TIÊN: Thanh và Tùng cần instance profile để bật máy.
#
# CẦN LÀM:
# [ ] Role web + aws_iam_instance_profile.web:
#     AmazonSSMManagedInstanceCore; s3:PutObject bucket originals;
#     secretsmanager:GetSecretValue secret DB
# [ ] Role worker + aws_iam_instance_profile.worker:
#     AmazonSSMManagedInstanceCore; s3:GetObject originals; s3:PutObject processed;
#     sqs:ReceiveMessage/DeleteMessage/ChangeMessageVisibility/GetQueueAttributes;
#     secretsmanager:GetSecretValue
# [ ] Không dùng Resource "*" (trừ policy SSM có sẵn)
#
# XONG KHI: có 2 instance profile; máy gắn role vào được SSM.


# Phụ trách: Phong – Hạng mục 5 (IAM role gắn vào instance, không nhúng access key)
#
# Quyền tối thiểu: web chỉ ghi vào originals (để ký presigned URL);
# worker đọc originals, ghi processed, nhận việc từ SQS, mount EFS.
# Cả hai được đọc đúng 1 secret mật khẩu DB. Hai role đều có SSM để vào máy, không mở SSH.

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

# ---------- WEB ----------
data "aws_iam_policy_document" "web" {
  statement {
    sid       = "PresignUploadToOriginals"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.originals.arn}/*"]
  }

  # Chỉ có khi RDS đang bật
  dynamic "statement" {
    for_each = var.enable_rds ? [1] : []

    content {
      sid       = "ReadDbSecret"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = [aws_db_instance.main[0].master_user_secret[0].secret_arn]
    }
  }
}

resource "aws_iam_policy" "web" {
  name   = "imgflow-web-policy"
  policy = data.aws_iam_policy_document.web.json
}

resource "aws_iam_role" "web" {
  name               = "imgflow-web-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "web_custom" {
  role       = aws_iam_role.web.name
  policy_arn = aws_iam_policy.web.arn
}

resource "aws_iam_role_policy_attachment" "web_ssm" {
  role       = aws_iam_role.web.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "web" {
  name = "imgflow-web-role"
  role = aws_iam_role.web.name
}

# ---------- WORKER ----------
data "aws_iam_policy_document" "worker" {
  statement {
    sid       = "ReadOriginals"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.originals.arn}/*"]
  }

  statement {
    sid       = "WriteProcessed"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.processed.arn}/*"]
  }

  statement {
    sid = "ConsumeQueue"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
      "sqs:ChangeMessageVisibility",
    ]
    resources = [aws_sqs_queue.main.arn]
  }

  statement {
    sid = "MountEfs"
    actions = [
      "elasticfilesystem:ClientMount",
      "elasticfilesystem:ClientWrite",
    ]
    resources = [aws_efs_file_system.main.arn]
  }

  # Chỉ có khi RDS đang bật
  dynamic "statement" {
    for_each = var.enable_rds ? [1] : []

    content {
      sid       = "ReadDbSecret"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = [aws_db_instance.main[0].master_user_secret[0].secret_arn]
    }
  }
}

resource "aws_iam_policy" "worker" {
  name   = "imgflow-worker-policy"
  policy = data.aws_iam_policy_document.worker.json
}

resource "aws_iam_role" "worker" {
  name               = "imgflow-worker-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "worker_custom" {
  role       = aws_iam_role.worker.name
  policy_arn = aws_iam_policy.worker.arn
}

resource "aws_iam_role_policy_attachment" "worker_ssm" {
  role       = aws_iam_role.worker.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "worker_cloudwatch" {
  role       = aws_iam_role.worker.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

resource "aws_iam_instance_profile" "worker" {
  name = "imgflow-worker-role"
  role = aws_iam_role.worker.name
}

output "web_instance_profile" {
  value = aws_iam_instance_profile.web.name
}

output "worker_instance_profile" {
  value = aws_iam_instance_profile.worker.name
}