# Phụ trách: Phong – Hạng mục 3, 5
#
# CẦN LÀM:
# [ ] CloudFront distribution trỏ vào bucket processed, dùng OAC
# [ ] Bucket policy của processed chỉ cho cloudfront.amazonaws.com (SourceArn = distribution này)
#
# XONG KHI: mở ảnh qua link CloudFront được; mở thẳng link S3 bị 403.

# Phụ trách: Phong – CloudFront + OAC
# Bucket processed vẫn private; chỉ distribution này đọc được.

resource "aws_cloudfront_origin_access_control" "processed" {
  name                              = "imgflow-processed-oac"
  description                       = "OAC cho bucket anh da xu ly"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

resource "aws_cloudfront_distribution" "cdn" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "CDN for bucket ImgFlow processed"
  price_class     = "PriceClass_200" # có châu Á, không gồm các vùng đắt nhất

  origin {
    domain_name              = aws_s3_bucket.processed.bucket_regional_domain_name
    origin_id                = "processed-s3"
    origin_access_control_id = aws_cloudfront_origin_access_control.processed.id
  }

  default_cache_behavior {
    target_origin_id       = "processed-s3"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
    compress               = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# Chỉ đúng distribution này được đọc object trong bucket processed
data "aws_iam_policy_document" "processed_from_cloudfront" {
  statement {
    sid       = "AllowCloudFrontRead"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.processed.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.cdn.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "processed" {
  bucket = aws_s3_bucket.processed.id
  policy = data.aws_iam_policy_document.processed_from_cloudfront.json

  depends_on = [aws_s3_bucket_public_access_block.this]
}

output "cloudfront_domain" {
  description = "Tung ghep domain nay voi key anh de tao URL xem anh"
  value       = aws_cloudfront_distribution.cdn.domain_name
}