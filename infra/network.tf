# Phụ trách: Thanh – Hạng mục 1 (mạng riêng, public/private, 2 AZ)
#
# 4 tầng, mỗi tầng 2 subnet ở 2 AZ:
#   public  10.0.1-2.0/24   ALB, NAT          -> ra Internet qua IGW
#   web     10.0.11-12.0/24 máy web           -> ra ngoài qua NAT
#   worker  10.0.21-22.0/24 máy xử lý ảnh     -> ra ngoài qua NAT, S3 qua endpoint
#   data    10.0.31-32.0/24 RDS               -> không có đường ra Internet

locals {
  azs = ["${var.region}a", "${var.region}b"]
}

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "imgflow-vpc" }
}

resource "aws_subnet" "public" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.${count.index + 1}.0/24"
  availability_zone = local.azs[count.index]
  tags              = { Name = "imgflow-public-${count.index + 1}" }
}

resource "aws_subnet" "web" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.${count.index + 11}.0/24"
  availability_zone = local.azs[count.index]
  tags              = { Name = "imgflow-web-${count.index + 1}" }
}

resource "aws_subnet" "worker" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.${count.index + 21}.0/24"
  availability_zone = local.azs[count.index]
  tags              = { Name = "imgflow-worker-${count.index + 1}" }
}

resource "aws_subnet" "data" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.${count.index + 31}.0/24"
  availability_zone = local.azs[count.index]
  tags              = { Name = "imgflow-data-${count.index + 1}" }
}

# ---------- Public: ra Internet trực tiếp ----------
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "imgflow-igw" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = { Name = "imgflow-rt-public" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# ---------- NAT: chỉ tồn tại khi enable_nat = true ----------
resource "aws_eip" "nat" {
  count  = var.enable_nat ? 1 : 0
  domain = "vpc"
  tags   = { Name = "imgflow-nat-ip" }
}

resource "aws_nat_gateway" "main" {
  count         = var.enable_nat ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public[0].id
  tags          = { Name = "imgflow-nat" }
  depends_on    = [aws_internet_gateway.main]
}

# ---------- Web + worker: ra ngoài qua NAT ----------
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "imgflow-rt-private" }
}

resource "aws_route" "private_to_nat" {
  count                  = var.enable_nat ? 1 : 0
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.main[0].id
}

resource "aws_route_table_association" "web" {
  count          = 2
  subnet_id      = aws_subnet.web[count.index].id
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "worker" {
  count          = 2
  subnet_id      = aws_subnet.worker[count.index].id
  route_table_id = aws_route_table.private.id
}

# ---------- Data: không có đường ra Internet ----------
resource "aws_route_table" "data" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "imgflow-rt-data" }
}

resource "aws_route_table_association" "data" {
  count          = 2
  subnet_id      = aws_subnet.data[count.index].id
  route_table_id = aws_route_table.data.id
}

# ---------- Đường tắt miễn phí tới S3 (không qua NAT) ----------
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]
  tags              = { Name = "imgflow-s3-endpoint" }
}
