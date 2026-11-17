# Phụ trách: Thanh – Hạng mục 2, 6
#
# CẦN LÀM:
# [ ] ALB đặt ở aws_subnet.public[*].id, SG aws_security_group.alb.id, listener cổng 80
# [ ] Target group cổng 8000, health check đường dẫn /healthz
# [ ] Launch template: Amazon Linux 2023, t3.micro, KHÔNG gán IP public, IMDSv2,
#     SG aws_security_group.web.id, instance profile aws_iam_instance_profile.web (Phong làm)
# [ ] User data: cài Python, tải code app/web, chạy service cổng 8000
# [ ] ASG web: subnet aws_subnet.web[*].id, min 2 / max 4, target tracking CPU 50%
#
# XONG KHI: mở DNS của ALB thấy trang web; cột Public IPv4 của EC2 trống;
#           vào được máy bằng SSM Session Manager.
