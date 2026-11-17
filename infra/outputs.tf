# In ra các giá trị quan trọng sau mỗi lần apply. Xem lại bằng: terraform output
# Mỗi người thêm output của phần mình vào cuối file.

output "vpc_id"            { value = aws_vpc.main.id }
output "public_subnet_ids" { value = aws_subnet.public[*].id }
output "web_subnet_ids"    { value = aws_subnet.web[*].id }
output "worker_subnet_ids" { value = aws_subnet.worker[*].id }
output "data_subnet_ids"   { value = aws_subnet.data[*].id }
output "nat_enabled"       { value = var.enable_nat }

# Phong:  originals_bucket, processed_bucket, queue_url, cloudfront_domain, rds_endpoint
# Thanh:  alb_dns_name
output "alb_dns_name" {
  description = "DNS cua ALB de truy cap web"
  value       = aws_lb.web.dns_name
}
# Tùng:   worker_asg_name
