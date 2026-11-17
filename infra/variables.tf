# Phụ trách: Thanh. Ai cần biến chung mới thì thêm vào đây.

variable "region" {
  description = "Region AWS (Sydney - region duy nhat to chuc cho phep)"
  type        = string
  default     = "ap-southeast-2"
}

variable "enable_nat" {
  description = "true khi dang lam viec/demo; false de tat NAT cho do ton tien"
  type        = bool
  default     = false
}

variable "enable_rds" {
  description = "true khi can database; false de tat RDS cho do ton tien"
  type        = bool
  default     = false
}
