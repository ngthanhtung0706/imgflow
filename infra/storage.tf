# Phụ trách: Phong – Hạng mục 3 (>= 2 loại lưu trữ)
#
# CẦN LÀM:
# [ ] Bucket aws_s3_bucket.originals (ảnh gốc): chặn public, force_destroy = true,
#     CORS cho phép trình duyệt PUT bằng presigned URL,
#     lifecycle chuyển sang Standard-IA sau 30 ngày
# [ ] Bucket aws_s3_bucket.processed (ảnh đã xử lý): chặn public, force_destroy = true
# [ ] EFS (mã hoá) + mount target ở aws_subnet.worker[*].id, SG aws_security_group.efs.id
#     Đặt logo + font watermark lên EFS
#
# XONG KHI: upload được bằng presigned URL; worker ở 2 AZ cùng đọc được logo trên EFS.

# Phụ trách: Phong – Hạng mục 3 (>= 2 loại lưu trữ: S3 object + EFS file)
#
#   originals  ảnh gốc người bán upload (trình duyệt PUT thẳng lên đây bằng presigned URL)
#   processed  4 phiên bản ảnh đã xử lý, chỉ CloudFront đọc được (xem cdn.tf)
#   EFS        logo/font watermark dùng chung cho mọi worker ở cả 2 AZ

data "aws_caller_identity" "me" {}

variable "cors_allowed_origins" {
  description = "Nguon duoc phep PUT anh len S3. Doi sang DNS cua ALB khi da co"
  type        = list(string)
  default     = ["*"]
}

# Tên bucket có account id để không đụng tên với tài khoản khác (S3 dùng chung 1 không gian tên toàn cầu)
resource "aws_s3_bucket" "originals" {
  bucket        = "imgflow-originals-${data.aws_caller_identity.me.account_id}"
  force_destroy = true # cho phép terraform destroy kể cả khi còn ảnh
}

resource "aws_s3_bucket" "processed" {
  bucket        = "imgflow-processed-${data.aws_caller_identity.me.account_id}"
  force_destroy = true
}

locals {
  s3_buckets = {
    originals = aws_s3_bucket.originals.id
    processed = aws_s3_bucket.processed.id
  }
}

# Cả hai bucket đều private hoàn toàn
resource "aws_s3_bucket_public_access_block" "this" {
  for_each = local.s3_buckets
  bucket   = each.value

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = local.s3_buckets
  bucket   = each.value

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# CORS: trình duyệt ở trang web (ALB) được phép PUT sang S3
resource "aws_s3_bucket_cors_configuration" "originals" {
  bucket = aws_s3_bucket.originals.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT"]
    allowed_origins = var.cors_allowed_origins
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

# Ảnh gốc cũ chuyển sang Standard-IA (rẻ hơn), dọn upload dở dang
resource "aws_s3_bucket_lifecycle_configuration" "originals" {
  bucket = aws_s3_bucket.originals.id

  rule {
    id     = "originals-to-standard-ia"
    status = "Enabled"

    filter {}

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

# ---------- EFS ----------
resource "aws_efs_file_system" "main" {
  creation_token   = "imgflow-efs"
  encrypted        = true
  performance_mode = "generalPurpose"
  throughput_mode  = "elastic"
  tags             = { Name = "imgflow-efs" }
}

resource "aws_efs_backup_policy" "main" {
  file_system_id = aws_efs_file_system.main.id

  backup_policy {
    status = "ENABLED"
  }
}

# Mỗi AZ một mount target, nằm ở subnet data; SG efs chỉ cho worker (NFS 2049)
resource "aws_efs_mount_target" "this" {
  count           = 2
  file_system_id  = aws_efs_file_system.main.id
  subnet_id       = aws_subnet.data[count.index].id
  security_groups = [aws_security_group.efs.id]
}

output "originals_bucket" {
  value = aws_s3_bucket.originals.id
}

output "processed_bucket" {
  value = aws_s3_bucket.processed.id
}

output "efs_id" {
  description = "Worker mount EFS vao /mnt/efs"
  value       = aws_efs_file_system.main.id
}