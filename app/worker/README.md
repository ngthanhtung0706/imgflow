# Worker – Phụ trách: Tùng

CẦN LÀM:
- [ ] Long polling SQS; bỏ qua message s3:TestEvent
- [ ] Tải ảnh gốc, tạo 4 bản: full (nén), 1080 px, 600 px, thumb 200 px, có watermark
      (logo + font đọc từ /mnt/efs)
- [ ] Ghi vào bucket processed theo key {shop_id}/{job_id}/{ten}.jpg, cập nhật job DONE,
      rồi mới xoá message
- [ ] Lỗi: retry nhanh; quá 3 lần thì job FAILED (message tự sang DLQ)

XONG KHI: 1 ảnh vào thì ra đủ 4 file có watermark; file hỏng nằm trong DLQ.
