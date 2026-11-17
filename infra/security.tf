# Phụ trách: Thanh – Hạng mục 2 (máy chủ trong subnet riêng, không mở SSH)
#
#   alb    <- Internet, cổng 80
#   web    <- chỉ từ alb, cổng 8000
#   worker <- không ai (worker tự đi lấy việc từ SQS)
#   rds    <- chỉ từ web và worker, cổng 5432
#   efs    <- chỉ từ worker, cổng 2049
# Lưu ý: description phải viết KHÔNG DẤU, có dấu AWS báo lỗi.
# Rule được tách riêng (aws_vpc_security_group_*_rule) để các SG không khoá nhau khi xoá.

resource "aws_security_group" "alb" {
  name        = "imgflow-alb"
  description = "ALB nhan HTTP tu Internet"
  vpc_id      = aws_vpc.main.id
}

resource "aws_security_group" "web" {
  name        = "imgflow-web"
  description = "Web chi nhan tu ALB"
  vpc_id      = aws_vpc.main.id
}

resource "aws_security_group" "worker" {
  name        = "imgflow-worker"
  description = "Worker khong nhan ket noi vao"
  vpc_id      = aws_vpc.main.id
}

resource "aws_security_group" "rds" {
  name        = "imgflow-rds"
  description = "Postgres chi nhan tu web va worker"
  vpc_id      = aws_vpc.main.id
}

resource "aws_security_group" "efs" {
  name        = "imgflow-efs"
  description = "EFS chi nhan tu worker"
  vpc_id      = aws_vpc.main.id
}

# ---------- Inbound ----------
resource "aws_vpc_security_group_ingress_rule" "alb_http" {
  security_group_id = aws_security_group.alb.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_vpc_security_group_ingress_rule" "web_from_alb" {
  security_group_id            = aws_security_group.web.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_web" {
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = aws_security_group.web.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_worker" {
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = aws_security_group.worker.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_ingress_rule" "efs_from_worker" {
  security_group_id            = aws_security_group.efs.id
  referenced_security_group_id = aws_security_group.worker.id
  ip_protocol                  = "tcp"
  from_port                    = 2049
  to_port                      = 2049
}

# ---------- Outbound: alb, web, worker được đi ra mọi nơi ----------
resource "aws_vpc_security_group_egress_rule" "alb_out" {
  security_group_id = aws_security_group.alb.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_vpc_security_group_egress_rule" "web_out" {
  security_group_id = aws_security_group.web.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_vpc_security_group_egress_rule" "worker_out" {
  security_group_id = aws_security_group.worker.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}
