# Cấu hình gunicorn trên EC2 (t3.micro: 2 vCPU, 1 GB RAM)
bind = "0.0.0.0:8000"
workers = 2
threads = 4
timeout = 30
accesslog = "-"
errorlog = "-"
