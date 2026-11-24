## 1. TỔNG HỢP CÁC CÔNG VIỆC ĐÃ TRIỂN KHAI

1. **Khởi tạo hệ thống quản lý trạng thái hạ tầng dùng chung (Remote State Backend):**
   * Viết và thực thi kịch bản `scripts/bootstrap-state.sh` để tạo bucket Amazon S3 (`imgflow-tfstate-016170038020`) tại region `ap-southeast-2`, kích hoạt tính năng lưu phiên bản (`Versioning`).
   * Cấu hình `infra/providers.tf` sử dụng S3 backend kết hợp cơ chế khóa trạng thái (`use_lockfile = true`, `encrypt = true`) giúp 4 thành viên trong nhóm làm việc song song mà không xảy ra xung đột state.
2. **Thiết kế và dựng hạ tầng mạng phân tầng (`infra/network.tf`):**
   * Triển khai VPC `imgflow-vpc` (`10.0.0.0/16`) trải đều trên 2 Availability Zone (`ap-southeast-2a` và `ap-southeast-2b`) với 4 tầng subnet độc lập (`public`, `web`, `worker`, `data`).
   * Thiết lập Internet Gateway, NAT Gateway (có cờ điều khiển `enable_nat` để tối ưu chi phí credits) và S3 Gateway VPC Endpoint miễn phí.
3. **Thiết lập kiến trúc bảo mật nhiều lớp (`infra/security.tf`):**
   * Xây dựng 5 Security Group tách biệt (`imgflow-alb`, `imgflow-web`, `imgflow-worker`, `imgflow-rds`, `imgflow-efs`) với các quy tắc tách rời (`aws_vpc_security_group_*_rule`) để tránh khóa chéo khi cập nhật/xóa hạ tầng.
   * Loại bỏ hoàn toàn cổng SSH (`22`) và không cấp Public IPv4 cho toàn bộ máy chủ nội bộ.
4. **Triển khai Application Load Balancer & Auto Scaling Group Web (`infra/web.tf`):**
   * Cấu hình ALB `imgflow-alb` trên các Public Subnet, chuyển tiếp lưu lượng HTTP cổng `80` vào Target Group `imgflow-web-tg` cổng `8000` (kiểm tra sức khỏe định kỳ qua đường dẫn `/healthz`).
   * Xây dựng Launch Template sử dụng AMI Amazon Linux 2023 mới nhất, bắt buộc chuẩn bảo mật **IMDSv2** (`http_tokens = "required"`), gắn IAM Role `imgflow-web-role` và tự động cài đặt mã nguồn ứng dụng qua `user_data`.
   * Cấu hình Auto Scaling Group `imgflow-web-asg` (tối thiểu 2, tối đa 4 máy `t3.micro`) kết hợp chính sách tự động mở rộng theo mức sử dụng CPU trung bình (`50%`).

---

## 2. HẠNG MỤC 1: THIẾT KẾ MẠNG RIÊNG (VPC, SUBNET CÔNG KHAI & RIÊNG TƯ TRÊN 2 AVAILABILITY ZONE)

### 2.1. Kiến trúc mạng thực tế (`infra/network.tf`)

Hệ thống sử dụng một mạng riêng ảo độc lập (**Amazon VPC** `imgflow-vpc`, dải địa chỉ `10.0.0.0/16`, bật `enable_dns_support` và `enable_dns_hostnames`). Không gian địa chỉ được chia thành **8 subnet thuộc 4 tầng chức năng**, phân bổ đều qua **2 Availability Zone** (`ap-southeast-2a` và `ap-southeast-2b`):

| Tầng mạng (Tier) | Tên tài nguyên | Dải địa chỉ CIDR | Availability Zone | Định tuyến mạng (Route Table) | Vai trò trong hệ thống |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Public Tier** | `imgflow-public-1`<br>`imgflow-public-2` | `10.0.1.0/24`<br>`10.0.2.0/24` | `ap-southeast-2a`<br>`ap-southeast-2b` | `imgflow-rt-public`<br>(`0.0.0.0/0` $\rightarrow$ IGW) | Đặt Application Load Balancer (`imgflow-alb`) và NAT Gateway (`imgflow-nat`). |
| **Web Tier** | `imgflow-web-1`<br>`imgflow-web-2` | `10.0.11.0/24`<br>`10.0.12.0/24` | `ap-southeast-2a`<br>`ap-southeast-2b` | `imgflow-rt-private`<br>(`0.0.0.0/0` $\rightarrow$ NAT) | Đặt cụm máy chủ ứng dụng Web (`imgflow-web-asg`). |
| **Worker Tier** | `imgflow-worker-1`<br>`imgflow-worker-2` | `10.0.21.0/24`<br>`10.0.22.0/24` | `ap-southeast-2a`<br>`ap-southeast-2b` | `imgflow-rt-private`<br>(`0.0.0.0/0` $\rightarrow$ NAT) | Đặt cụm máy chủ xử lý ảnh bất đồng bộ (`imgflow-worker-asg`). |
| **Data Tier** | `imgflow-data-1`<br>`imgflow-data-2` | `10.0.31.0/24`<br>`10.0.32.0/24` | `ap-southeast-2a`<br>`ap-southeast-2b` | `imgflow-rt-data`<br>(Chỉ định tuyến nội bộ) | Đặt cơ sở dữ liệu Amazon RDS PostgreSQL (`imgflow-db`), hoàn toàn cô lập với Internet. |

Ngoài ra, hạ tầng cấu hình thêm **S3 Gateway VPC Endpoint** (`imgflow-s3-endpoint`) gắn trực tiếp vào bảng định tuyến `imgflow-rt-private` để lưu lượng tải/ghi ảnh giữa Worker và Amazon S3 đi trực tiếp qua mạng nội bộ AWS.

### 2.2. Lý giải lựa chọn công nghệ (Đáp ứng CLO2)

* **Vì sao phân tách 4 tầng subnet thay vì chỉ dùng 2 tầng (Public / Private) thông thường?**
  * Việc tách riêng `web`, `worker` và `data` giúp áp đặt ranh giới kiểm soát lưu lượng chặt chẽ theo từng chức năng. Đặc biệt, tầng `data` sử dụng bảng định tuyến riêng (`imgflow-rt-data`) không có đường ra `0.0.0.0/0`, đảm bảo cơ sở dữ liệu PostgreSQL không thể bị truy cập từ bên ngoài và cũng không thể tự gửi dữ liệu ra Internet ngay cả khi bị khai thác lỗ hổng.
* **Vì sao trải đều trên 2 Availability Zone (`ap-southeast-2a` và `ap-southeast-2b`)?**
  * Đảm bảo khả năng chịu lỗi vật lý ở mức trung tâm dữ liệu (High Availability). Nếu một Availability Zone gặp sự cố mất điện hoặc gián đoạn mạng, Application Load Balancer và Auto Scaling Group vẫn duy trì dịch vụ liên tục trên AZ còn lại.
* **Vì sao sử dụng S3 Gateway VPC Endpoint kết hợp NAT Gateway có cờ điều khiển (`enable_nat`)?**
  * Lưu lượng truyền tải ảnh giữa EC2 Worker và hai bucket S3 (`originals`, `processed`) chiếm băng thông lớn nhất hệ thống. S3 Gateway Endpoint hoàn toàn miễn phí, giúp lưu lượng này đi trực tiếp trong mạng backbone của AWS thay vì đi vòng qua NAT Gateway (vốn tính phí theo mỗi GB dữ liệu xử lý), đồng thời giảm độ trễ và tăng tính bảo mật.
  * Biến `enable_nat` cho phép bật NAT Gateway khi khởi tạo máy (để tải gói Python từ Internet và kết nối AWS Systems Manager) và tắt đi khi không vận hành để tiết kiệm chi phí định kỳ.

### 2.3. Bằng chứng kiểm chứng (HM1)

* **VPC & Subnets:** Xác nhận 8 subnet hoạt động trên 2 AZ (`ap-southeast-2a`, `ap-southeast-2b`) với trạng thái `Available` (lưu tại `docs/evidence/HM1/`).
* **Route Tables & VPC Endpoint:** Xác nhận `imgflow-rt-public` trỏ ra `igw-...`, `imgflow-rt-private` trỏ ra `nat-...` cùng prefix list của S3 Endpoint, và `imgflow-rt-data` chỉ chứa route cục bộ `10.0.0.0/16`.

---

## 3. HẠNG MỤC 2: MÁY CHỦ ỨNG DỤNG TRONG SUBNET RIÊNG TƯ, KHÔNG PHƠI RA INTERNET

### 3.1. Kiến trúc triển khai & Kiểm soát truy cập (`infra/security.tf`, `infra/web.tf`)

Toàn bộ máy chủ xử lý ứng dụng của ImgFlow đều được triển khai bên trong các Private Subnet và tuân thủ nghiêm ngặt các nguyên tắc cô lập mạng:

1. **Không gán địa chỉ IP công cộng:**
   * Trong `aws_launch_template.web` và `aws_launch_template.worker`, tham số `associate_public_ip_address = false` được thiết lập cứng. Các máy EC2 chỉ sở hữu địa chỉ IP nội bộ thuộc dải `10.0.11-12.0/24` (Web) và `10.0.21-22.0/24` (Worker).
2. **Kiểm soát luồng truy cập theo chuỗi khép kín (Security Group Chaining):**

| Security Group | Tài nguyên gắn | Quy tắc Inbound (Luồng vào) | Quy tắc Outbound (Luồng ra) |
| :--- | :--- | :--- | :--- |
| **`imgflow-alb`** | Application Load Balancer | Cho phép TCP cổng `80` từ Internet (`0.0.0.0/0`). | Mở toàn bộ (`-1`) ra ngoài để chuyển tiếp tới Web. |
| **`imgflow-web`** | EC2 Web (`imgflow-web-asg`) | **Chỉ** nhận TCP cổng `8000` từ Security Group `imgflow-alb`. | Mở toàn bộ (`-1`) qua NAT/VPC Endpoint. |
| **`imgflow-worker`** | EC2 Worker (`imgflow-worker-asg`) | **Không mở bất kỳ cổng Inbound nào** (chủ động kéo message từ SQS). | Mở toàn bộ (`-1`) qua NAT/VPC Endpoint. |
| **`imgflow-rds`** | RDS PostgreSQL (`imgflow-db`) | **Chỉ** nhận TCP cổng `5432` từ `imgflow-web` và `imgflow-worker`. | Không cấu hình outbound bổ sung. |
| **`imgflow-efs`** | EFS File System | **Chỉ** nhận TCP cổng `2049` (NFS) từ `imgflow-worker`. | Không cấu hình outbound bổ sung. |

3. **Quản trị máy chủ không mở cổng SSH (`22`) và bắt buộc IMDSv2:**
   * Không tạo SSH Key Pair và không mở cổng `22` trên bất kỳ Security Group nào. Quản trị viên truy cập vào terminal của EC2 thông qua **AWS Systems Manager (SSM) Session Manager** dựa trên IAM Instance Profile (`AmazonSSMManagedInstanceCore`).
   * Cấu hình `metadata_options` bắt buộc sử dụng **IMDSv2** (`http_tokens = "required"`, `http_put_response_hop_limit = 1`) để ngăn chặn các cuộc tấn công SSRF đánh cắp thông tin xác thực tạm thời của IAM Role.

### 3.2. Lý giải lựa chọn công nghệ (Đáp ứng CLO2)

* **Vì sao đặt EC2 trong Private Subnet sau ALB thay vì đặt trực tiếp ở Public Subnet?**
  * Nếu đặt EC2 ở Public Subnet, máy chủ sẽ có Public IP và đối mặt trực tiếp với các cuộc tấn công quét cổng, DDoS lớp mạng hoặc khai thác trực tiếp vào tiến trình ứng dụng. Khi đặt sau Application Load Balancer (`imgflow-alb`), ALB đóng vai trò điểm tiếp nhận duy nhất từ Internet, tự động lọc bỏ các gói tin HTTP không hợp lệ và chỉ chuyển tiếp lưu lượng chuẩn vào đúng cổng `8000` của cụm Web.
* **Vì sao dùng AWS Systems Manager (SSM) Session Manager thay cho Bastion Host và SSH?**
  * Việc dựng thêm một máy chủ Bastion Host ở Public Subnet vừa làm tăng chi phí vận hành hàng tháng, vừa tạo thêm một bề mặt tấn công cần quản lý khóa SSH (`.pem`) và vá lỗi bảo mật. Session Manager cho phép kết nối shell an toàn thông qua kênh mã hóa HTTPS xuất phát từ bên trong EC2 ra dịch vụ AWS, không cần mở bất kỳ cổng Inbound nào và tự động ghi nhật ký phiên làm việc trên AWS CloudTrail.
* **Vì sao tách riêng các rule của Security Group thành tài nguyên độc lập (`aws_vpc_security_group_ingress_rule`)?**
  * Trong Terraform, việc viết quy tắc `ingress`/`egress` lồng bên trong `aws_security_group` dễ gây lỗi phụ thuộc vòng tròn (circular dependency) khi hai Security Group tham chiếu lẫn nhau. Tách riêng từng rule giúp Terraform tạo, cập nhật và hủy hạ tầng ổn định, không bị treo khi xóa tài nguyên.

### 3.3. Bằng chứng kiểm chứng (HM2)

* **Chi tiết EC2 Instance:** Xác nhận các máy `imgflow-web` và `imgflow-worker` nằm tại subnet `10.0.11.x` / `10.0.21.x`, cột *Public IPv4 address* trống (`-`), trạng thái `Running` và vượt qua kiểm tra `3/3 checks passed` (lưu tại `docs/evidence/HM2/`).
* **Quy tắc Security Group & Truy cập ứng dụng:** Xác nhận `imgflow-web` chỉ nhận nguồn từ `sg-... (imgflow-alb)` tại cổng `8000`; kiểm tra truy cập thực tế qua DNS của ALB (`http://imgflow-alb-1869531157.ap-southeast-2.elb.amazonaws.com/login`) hiển thị thành công giao diện ứng dụng ImgFlow trong khi không thể truy cập trực tiếp vào IP của máy chủ Web.