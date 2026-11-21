# Phụ trách: Tùng – Hạng mục 3, 6
#
# Worker xử lý ảnh chạy trong ASG riêng ở subnet worker (private, không IP public).
# Máy mới tự clone repo, mount EFS, chạy service lấy việc từ SQS.
# Cần enable_nat = true (và enable_rds = true) thì máy mới cài được gói và kết nối DB.

variable "app_git_url" {
  description = "Repo public chua code app (EC2 git clone, khong can khoa)"
  type        = string
  default     = "https://github.com/ngthanhtung0706/imgflow.git"
}

variable "app_git_ref" {
  description = "Nhanh/tag cua repo de deploy (main khi nop bai)"
  type        = string
  default     = "develop"
}

locals {
  # RDS có thể đang tắt (enable_rds = false) nên không được tham chiếu cứng [0]
  db_host       = var.enable_rds ? aws_db_instance.main[0].address : ""
  db_secret_arn = var.enable_rds ? aws_db_instance.main[0].master_user_secret[0].secret_arn : ""
}

# ---------- Launch template ----------
resource "aws_launch_template" "worker" {
  name_prefix   = "imgflow-worker-"
  image_id      = data.aws_ami.al2023.id
  instance_type = "t3.small"

  iam_instance_profile {
    name = aws_iam_instance_profile.worker.name
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  network_interfaces {
    associate_public_ip_address = false
    security_groups             = [aws_security_group.worker.id]
  }

  user_data = base64encode(<<-EOF
    #!/bin/bash
    set -ex
    dnf install -y python3.12 python3.12-pip git amazon-efs-utils

    # EFS chứa logo + font watermark, dùng chung cho mọi worker
    mkdir -p /mnt/efs
    echo "${aws_efs_file_system.main.id}:/ /mnt/efs efs _netdev,tls,nofail 0 0" >> /etc/fstab
    mount -a -t efs || true

    # Cấu hình (không có mật khẩu: mật khẩu DB lấy từ Secrets Manager lúc chạy)
    mkdir -p /etc/imgflow
    cat > /etc/imgflow/imgflow.env <<ENVEOF
    AWS_REGION=${var.region}
    ORIGINALS_BUCKET=${aws_s3_bucket.originals.id}
    PROCESSED_BUCKET=${aws_s3_bucket.processed.id}
    QUEUE_URL=${aws_sqs_queue.main.url}
    CDN_DOMAIN=${aws_cloudfront_distribution.cdn.domain_name}
    DB_HOST=${local.db_host}
    DB_SECRET_ARN=${local.db_secret_arn}
    EFS_ROOT=/mnt/efs
    ENVEOF

    # Code worker
    git clone --depth 1 --branch ${var.app_git_ref} ${var.app_git_url} /opt/imgflow
    python3.12 -m venv /opt/imgflow/venv
    /opt/imgflow/venv/bin/pip install -r /opt/imgflow/app/worker/requirements.txt

    # Logo mặc định lên EFS (chỉ khi EFS đã mount và chưa có logo). Shop có logo riêng thì dùng logo trong RDS
    mountpoint -q /mnt/efs && [ ! -f /mnt/efs/logo.png ] && cp /opt/imgflow/app/assets/logo.png /mnt/efs/logo.png || true

    cat > /etc/systemd/system/imgflow-worker.service <<SVCEOF
    [Unit]
    Description=ImgFlow Worker
    After=network-online.target remote-fs.target

    [Service]
    WorkingDirectory=/opt/imgflow/app
    EnvironmentFile=/etc/imgflow/imgflow.env
    ExecStart=/opt/imgflow/venv/bin/python -m worker.worker
    Restart=always
    RestartSec=5

    [Install]
    WantedBy=multi-user.target
    SVCEOF

    systemctl daemon-reload
    systemctl enable --now imgflow-worker
  EOF
  )

  tag_specifications {
    resource_type = "instance"
    tags          = { Name = "imgflow-worker" }
  }
}

# ---------- ASG worker ----------
resource "aws_autoscaling_group" "worker" {
  name                = "imgflow-worker-asg"
  vpc_zone_identifier = aws_subnet.worker[*].id
  health_check_type   = "EC2"

  min_size         = 1
  max_size         = 4
  desired_capacity = 1

  # Quyền cần để dashboard vẽ được số máy
  enabled_metrics = [
    "GroupMinSize",
    "GroupMaxSize",
    "GroupDesiredCapacity",
    "GroupInServiceInstances",
    "GroupTotalInstances",
  ]
  metrics_granularity = "1Minute"

  launch_template {
    id      = aws_launch_template.worker.id
    version = "$Latest"
  }

  tag {
    key                 = "Name"
    value               = "imgflow-worker"
    propagate_at_launch = true
  }

  # Để scaling policy tự đổi số máy, không bị terraform đặt lại
  lifecycle {
    ignore_changes = [desired_capacity]
  }
}

# ---------- Scaling theo độ dài hàng đợi ----------
# Tăng: >= 20 tin -> +2 máy, >= 100 tin -> +3 máy (nhảy thẳng 1 -> 4)
resource "aws_autoscaling_policy" "worker_out" {
  name                   = "imgflow-worker-scale-out"
  autoscaling_group_name = aws_autoscaling_group.worker.name
  policy_type            = "StepScaling"
  adjustment_type        = "ChangeInCapacity"

  # Khoảng tính theo chênh lệch so với ngưỡng alarm (20)
  step_adjustment {
    metric_interval_lower_bound = 0
    metric_interval_upper_bound = 80
    scaling_adjustment          = 2
  }

  step_adjustment {
    metric_interval_lower_bound = 80
    scaling_adjustment          = 3
  }
}

resource "aws_cloudwatch_metric_alarm" "worker_queue_high" {
  alarm_name          = "imgflow-worker-queue-high"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.main.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 20
  comparison_operator = "GreaterThanOrEqualToThreshold"
  alarm_actions       = [aws_autoscaling_policy.worker_out.arn]
}

# Giảm: < 5 tin liên tục 5 phút -> -1 máy
resource "aws_autoscaling_policy" "worker_in" {
  name                   = "imgflow-worker-scale-in"
  autoscaling_group_name = aws_autoscaling_group.worker.name
  policy_type            = "StepScaling"
  adjustment_type        = "ChangeInCapacity"

  step_adjustment {
    metric_interval_upper_bound = 0
    scaling_adjustment          = -1
  }
}

resource "aws_cloudwatch_metric_alarm" "worker_queue_low" {
  alarm_name          = "imgflow-worker-queue-low"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.main.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 5
  threshold           = 5
  comparison_operator = "LessThanThreshold"
  alarm_actions       = [aws_autoscaling_policy.worker_in.arn]
}

output "worker_asg_name" {
  value = aws_autoscaling_group.worker.name
}
