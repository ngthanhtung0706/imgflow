"""
Load test – Phụ trách: Quyền (Tùng review). Hạng mục 6, 7.

CẦN LÀM:
- Đăng nhập web, xin N presigned URL, PUT N ảnh song song (ThreadPool)
- Tham số: số ảnh N, số luồng, có/không kèm 1 file hỏng
- In ra thời gian bắt đầu/kết thúc
- Chạy từ AWS CloudShell (Sydney) để upload nhanh, dùng ảnh mẫu 1-3 MB

XONG KHI: đẩy 200 ảnh + 1 file hỏng trong khoảng 1 phút.
"""
