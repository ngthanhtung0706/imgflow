# Phụ trách: Thanh – Hạng mục 2, 6
#
# CẦN LÀM:
# [x] ALB đặt ở aws_subnet.public[*].id, SG aws_security_group.alb.id, listener cổng 80
# [x] Target group cổng 8000, health check đường dẫn /healthz
# [x] Launch template: Amazon Linux 2023, t3.micro, KHÔNG gán IP public, IMDSv2,
#     SG aws_security_group.web.id, instance profile aws_iam_instance_profile.web (Phong làm)
# [x] User data: cài Python, tải code app/web, chạy service cổng 8000
# [x] ASG web: subnet aws_subnet.web[*].id, min 2 / max 4, target tracking CPU 50%

# Lấy tự động AMI mới nhất của Amazon Linux 2023 (x86_64) tại Sydney
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ---------- 1. Application Load Balancer (ALB) ----------
resource "aws_lb" "web" {
  name               = "imgflow-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  tags = { Name = "imgflow-alb" }
}

resource "aws_lb_target_group" "web" {
  name     = "imgflow-web-tg"
  port     = 8000
  protocol = "HTTP"
  vpc_id   = aws_vpc.main.id

  health_check {
    path                = "/healthz"
    protocol            = "HTTP"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = { Name = "imgflow-web-tg" }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.web.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

# ---------- 2. Launch Template cho EC2 Web ----------
resource "aws_launch_template" "web" {
  name_prefix   = "imgflow-web-"
  image_id      = data.aws_ami.al2023.id
  instance_type = "t3.micro"

  # Gắn IAM Instance Profile do Phong tạo trong iam.tf
  iam_instance_profile {
    name = aws_iam_instance_profile.web.name
  }

  # Bắt buộc IMDSv2 để tăng cường bảo mật
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  # Tắt Public IP và gắn Security Group của Web
  network_interfaces {
    associate_public_ip_address = false
    security_groups             = [aws_security_group.web.id]
  }

  # Cài Python, clone repo public, chạy gunicorn cổng 8000 (/healthz không đụng DB)
  # Cần enable_nat = true để cài gói và clone; enable_rds = true để web dùng được DB.
  user_data = base64encode(<<-EOF
    #!/bin/bash
    set -ex
    dnf install -y python3.12 python3.12-pip git

    # Cấu hình (không có mật khẩu: mật khẩu DB lấy từ Secrets Manager lúc chạy)
    mkdir -p /etc/imgflow
    cat > /etc/imgflow/imgflow.env <<ENVEOF
    AWS_REGION=${var.region}
    ORIGINALS_BUCKET=${aws_s3_bucket.originals.id}
    PROCESSED_BUCKET=${aws_s3_bucket.processed.id}
    CDN_DOMAIN=${var.cdn_domain}
    DB_HOST=${local.db_host}
    DB_SECRET_ARN=${local.db_secret_arn}
    ENVEOF

    git clone --depth 1 --branch ${var.app_git_ref} ${var.app_git_url} /opt/imgflow
    python3.12 -m venv /opt/imgflow/venv
    /opt/imgflow/venv/bin/pip install -r /opt/imgflow/app/web/requirements.txt

    cat > /etc/systemd/system/imgflow-web.service <<SVCEOF
    [Unit]
    Description=ImgFlow Web Service
    After=network-online.target

    [Service]
    WorkingDirectory=/opt/imgflow/app
    EnvironmentFile=/etc/imgflow/imgflow.env
    ExecStart=/opt/imgflow/venv/bin/gunicorn -c web/gunicorn.conf.py web.app:app
    Restart=always
    RestartSec=5

    [Install]
    WantedBy=multi-user.target
    SVCEOF

    systemctl daemon-reload
    systemctl enable --now imgflow-web
  EOF
  )

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "imgflow-web"
    }
  }
}

# ---------- 3. Auto Scaling Group (ASG) Web ----------
resource "aws_autoscaling_group" "web" {
  name                      = "imgflow-web-asg"
  vpc_zone_identifier       = aws_subnet.web[*].id
  target_group_arns         = [aws_lb_target_group.web.arn]
  health_check_type         = "ELB"
  health_check_grace_period = 120

  min_size         = 2
  max_size         = 4
  desired_capacity = 2

  launch_template {
    id      = aws_launch_template.web.id
    version = "$Latest"
  }

  tag {
    key                 = "Name"
    value               = "imgflow-web"
    propagate_at_launch = true
  }
}

resource "aws_autoscaling_policy" "web_cpu" {
  name                   = "imgflow-web-cpu-target"
  autoscaling_group_name = aws_autoscaling_group.web.name
  policy_type            = "TargetTrackingScaling"

  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }
    target_value = 50.0
  }
}