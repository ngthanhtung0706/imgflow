variable "alert_emails" {
  description = "Email nhan canh bao ImgFlow"
  type        = set(string)
  default     = []
}

resource "aws_sns_topic" "alerts" {
  name = "imgflow-alerts"
}

resource "aws_sns_topic_subscription" "alerts_email" {
  for_each  = var.alert_emails
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = each.value
}

resource "aws_cloudwatch_metric_alarm" "dlq_visible" {
  alarm_name          = "imgflow-dlq-visible"
  alarm_description   = "DLQ co it nhat mot message dang cho"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dlq.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "imgflow-alb-5xx"
  alarm_description   = "ALB phat sinh it nhat 5 loi 5xx trong 5 phut"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_ELB_5XX_Count"
  dimensions          = { LoadBalancer = aws_lb.web.arn_suffix }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

locals {
  monitoring_widgets = [
    {
      title  = "Jobs SQS"
      period = 60
      stat   = "Maximum"
      metrics = [
        ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.main.name],
        ["AWS/SQS", "ApproximateNumberOfMessagesNotVisible", "QueueName", aws_sqs_queue.main.name],
      ]
    },
    {
      title  = "Worker ASG"
      period = 60
      stat   = "Maximum"
      metrics = [
        ["AWS/AutoScaling", "GroupDesiredCapacity", "AutoScalingGroupName", aws_autoscaling_group.worker.name],
        ["AWS/AutoScaling", "GroupInServiceInstances", "AutoScalingGroupName", aws_autoscaling_group.worker.name],
      ]
    },
    {
      title  = "Dead-letter queue"
      period = 60
      stat   = "Maximum"
      metrics = [
        ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.dlq.name],
      ]
    },
    {
      title  = "Web ASG"
      period = 60
      stat   = "Maximum"
      metrics = [
        ["AWS/AutoScaling", "GroupDesiredCapacity", "AutoScalingGroupName", aws_autoscaling_group.web.name],
        ["AWS/AutoScaling", "GroupInServiceInstances", "AutoScalingGroupName", aws_autoscaling_group.web.name],
      ]
    },
    {
      title  = "ALB and target 5xx"
      period = 300
      stat   = "Sum"
      metrics = [
        ["AWS/ApplicationELB", "HTTPCode_ELB_5XX_Count", "LoadBalancer", aws_lb.web.arn_suffix],
        ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", aws_lb.web.arn_suffix],
      ]
    },
    {
      title  = "EC2 CPU (%)"
      period = 300
      stat   = "Average"
      metrics = [
        ["AWS/EC2", "CPUUtilization", "AutoScalingGroupName", aws_autoscaling_group.web.name],
        ["AWS/EC2", "CPUUtilization", "AutoScalingGroupName", aws_autoscaling_group.worker.name],
      ]
    },
  ]

  monitoring_rds_widgets = var.enable_rds ? [
    {
      title  = "RDS CPU (%)"
      period = 60
      stat   = "Average"
      metrics = [
        ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", aws_db_instance.main[0].identifier],
      ]
    },
  ] : []
}

resource "aws_cloudwatch_dashboard" "ops" {
  dashboard_name = "imgflow-ops"

  dashboard_body = jsonencode({
    widgets = [
      for i, widget in concat(local.monitoring_widgets, local.monitoring_rds_widgets) : {
        type   = "metric"
        x      = i % 2 * 12
        y      = floor(i / 2) * 6
        width  = 12
        height = 6
        properties = {
          title   = widget.title
          period  = widget.period
          stat    = widget.stat
          metrics = widget.metrics
          region  = var.region
          view    = "timeSeries"
        }
      }
    ]
  })
}
