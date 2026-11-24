"""ImgFlow worker: lấy message S3 event từ SQS, tạo 4 bản ảnh có watermark, cập nhật job.

Chạy:  cd app && python -m worker.worker      (cần QUEUE_URL, ORIGINALS/PROCESSED_BUCKET, DB)

Thứ tự bảo đảm không mất việc: ghi đủ 4 file lên S3 -> đánh dấu job DONE -> mới xoá message.
Nếu worker chết giữa chừng, message hiện lại sau visibility timeout và job được làm lại
(ghi đè cùng key nên làm lại vô hại).
"""
import io
import json
import logging
import socket
import time
import urllib.parse

import boto3
from PIL import Image, ImageDraw, ImageFont, ImageOps

from common import config, db, naming

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("imgflow.worker")

WORKER_NAME = socket.gethostname()
WATERMARK_TEXT = "ImgFlow"
MAX_PIXELS = 60_000_000  # chặn ảnh "bom giải nén"
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

_s3 = boto3.client("s3", region_name=config.REGION)
_sqs = boto3.client("sqs", region_name=config.REGION)


class PermanentError(Exception):
    """Lỗi thử lại cũng không hết (ảnh hỏng, key sai tên...)."""


class AlreadyFailed(Exception):
    """Job đã FAILED ở lần nhận trước: không xử lý lại, chỉ để message đi tiếp sang DLQ."""


# ---------------------------------------------------------------- ảnh
def _load_font(size):
    path = config.EFS_ROOT / "font.ttf"
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default(size)  # chạy laptop / EFS chưa mount


MAX_LOGO_PIXELS = 4_000_000  # logo to hơn mức này bị bỏ qua cho đỡ tốn RAM


def _open_logo(source):
    """Mở logo từ đường dẫn hoặc file-like. Trả về None nếu không dùng được."""
    try:
        logo = Image.open(source)
        if logo.width * logo.height > MAX_LOGO_PIXELS:
            return None
        return logo.convert("RGBA")
    except Exception:  # Pillow ném nhiều loại lỗi cho file hỏng
        return None


def _load_logo(shop_id=None):
    """Logo riêng của shop (RDS) -> logo mặc định trên EFS -> None (đóng dấu bằng chữ)."""
    if shop_id is not None:
        try:
            with db.connect() as conn:
                row = conn.execute("SELECT logo FROM shops WHERE id = %s", (shop_id,)).fetchone()
            if row and row["logo"]:
                logo = _open_logo(io.BytesIO(bytes(row["logo"])))
                if logo is not None:
                    return logo
                log.warning("logo cua shop %s hong, dung logo mac dinh", shop_id)
        except Exception:
            log.exception("khong doc duoc logo shop %s, dung logo mac dinh", shop_id)
    return _open_logo(config.EFS_ROOT / "logo.png")


def add_watermark(img, logo=None):
    """Đóng dấu ở góc phải dưới: logo nếu có, không thì chữ."""
    img = img.convert("RGBA")
    w, h = img.size
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    margin = max(6, w // 50)
    if logo is not None:
        target_w = max(24, w // 5)
        lg = logo.resize((target_w, max(1, int(logo.height * target_w / logo.width))), Image.LANCZOS)
        alpha = lg.getchannel("A").point(lambda a: int(a * 0.6))
        lg.putalpha(alpha)
        layer.paste(lg, (w - lg.width - margin, h - lg.height - margin), lg)
    else:
        font = _load_font(max(12, w // 20))
        draw = ImageDraw.Draw(layer)
        box = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
        x = w - (box[2] - box[0]) - margin
        y = h - (box[3] - box[1]) - margin
        draw.text((x + 1, y + 1), WATERMARK_TEXT, font=font, fill=(0, 0, 0, 110))
        draw.text((x, y), WATERMARK_TEXT, font=font, fill=(255, 255, 255, 170))
    return Image.alpha_composite(img, layer).convert("RGB")


def make_variants(data, shop_id=None):
    """bytes ảnh gốc -> {tên bản: bytes JPEG}. Có shop_id thì dùng logo riêng của shop nếu có."""
    try:
        src = Image.open(io.BytesIO(data))
        src.load()
    except Exception as exc:  # Pillow ném nhiều loại lỗi khác nhau cho file hỏng
        log.warning("Pillow khong doc duoc anh: %s", exc)  # chi tiet ky thuat chi ghi vao log
        raise PermanentError("Không đọc được ảnh: file bị hỏng hoặc không phải ảnh.") from exc

    src = ImageOps.exif_transpose(src)
    if src.mode in ("RGBA", "LA", "P"):
        rgba = src.convert("RGBA")
        base = Image.new("RGB", rgba.size, (255, 255, 255))  # PNG trong suốt -> nền trắng
        base.paste(rgba, mask=rgba.getchannel("A"))
        src = base
    else:
        src = src.convert("RGB")

    logo = _load_logo(shop_id)
    out = {}
    for name, max_side, quality in naming.VARIANTS:
        img = src.copy()
        if max_side and max(img.size) > max_side:
            img.thumbnail((max_side, max_side), Image.LANCZOS)
        img = add_watermark(img, logo)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, optimize=True)
        out[name] = buf.getvalue()
    return out


# ---------------------------------------------------------------- job
def claim_job(job_id):
    """Đánh dấu PROCESSING và tăng attempts. Trả về None nếu job đã DONE.

    Job FAILED là trạng thái cuối: raise AlreadyFailed để không xử lý lại (và không nháy
    PROCESSING trên gallery) trong khi message đi nốt các lần nhận còn lại rồi sang DLQ.
    """
    with db.connect() as conn:
        row = conn.execute(
            "UPDATE jobs SET status = 'PROCESSING', attempts = attempts + 1, worker = %s, "
            "started_at = now(), error = NULL "
            "WHERE id = %s AND status IN ('PENDING', 'PROCESSING') RETURNING attempts",
            (WORKER_NAME, job_id),
        ).fetchone()
        if row:
            return row["attempts"]
        exists = conn.execute("SELECT status FROM jobs WHERE id = %s", (job_id,)).fetchone()
    if exists is None:
        raise RuntimeError(f"chua thay job {job_id} trong DB")  # có thể do trễ, cho thử lại
    if exists["status"] == "FAILED":
        raise AlreadyFailed(job_id)
    return None  # đã DONE


def finish_job(job_id, status, error=None):
    with db.connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = %s, error = %s, finished_at = now() WHERE id = %s",
            (status, (error or "")[:500] or None, job_id),
        )


def process_object(bucket, key):
    """Xử lý một ảnh gốc. Trả về True nếu đã làm, False nếu job đã xong từ trước."""
    parsed = naming.parse_original_key(key)
    if parsed is None:
        raise PermanentError(f"key khong dung quy uoc: {key}")
    shop_id, job_id = parsed

    if claim_job(job_id) is None:
        log.info("job %s da DONE, bo qua", job_id)
        return False

    data = _s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    variants = make_variants(data, shop_id)
    for name, body in variants.items():
        _s3.put_object(
            Bucket=config.PROCESSED_BUCKET,
            Key=naming.processed_key(shop_id, job_id, name),
            Body=body,
            ContentType="image/jpeg",
        )
    finish_job(job_id, "DONE")
    log.info("job %s xong (%s)", job_id, ", ".join(f"{n}={len(b) // 1024}KB" for n, b in variants.items()))
    return True


def _records(body):
    """Lấy (bucket, key) từ message. Bỏ qua s3:TestEvent và event không phải ObjectCreated."""
    try:
        data = json.loads(body)
    except ValueError:
        raise PermanentError("message khong phai JSON")
    if data.get("Event") == "s3:TestEvent":
        return []
    out = []
    for rec in data.get("Records", []):
        if not rec.get("eventName", "").startswith("ObjectCreated"):
            continue
        out.append(
            (rec["s3"]["bucket"]["name"], urllib.parse.unquote_plus(rec["s3"]["object"]["key"]))
        )
    return out


def _retry_later(msg):
    """Cho message hiện lại sau RETRY_VISIBILITY giây. Nhận đủ maxReceiveCount lần thì SQS tự chuyển sang DLQ."""
    _sqs.change_message_visibility(
        QueueUrl=config.QUEUE_URL,
        ReceiptHandle=msg["ReceiptHandle"],
        VisibilityTimeout=config.RETRY_VISIBILITY,
    )


def _job_ids(msg):
    try:
        ids = []
        for _, key in _records(msg["Body"]):
            parsed = naming.parse_original_key(key)
            if parsed:
                ids.append(parsed[1])
        return ids
    except Exception:
        return []


def handle_message(msg):
    """Xử lý một message SQS. Trả về True nếu được phép xoá message.

    Ảnh hỏng (lỗi vĩnh viễn): job FAILED nhưng KHÔNG xoá message, để SQS giao lại đủ 3 lần rồi
    chuyển sang DLQ, alarm DLQ mới gửi được email. Chỉ message không gắn với job nào
    (key lạ, không phải JSON) mới bị xoá vì thử lại hay vào DLQ cũng không giúp gì.
    """
    receives = int(msg.get("Attributes", {}).get("ApproximateReceiveCount", 1))
    try:
        for bucket, key in _records(msg["Body"]):
            process_object(bucket, key)
        return True
    except AlreadyFailed:
        log.info("job da FAILED tu lan nhan truoc (lan %d), giu message de sang DLQ", receives)
        _retry_later(msg)
        return False
    except Exception as exc:
        permanent = isinstance(exc, PermanentError)
        log.warning("loi (lan nhan %d, %s): %s", receives, "vinh vien" if permanent else "tam thoi", exc)
        if permanent and not _job_ids(msg):
            return True
        if permanent or receives >= config.MAX_RECEIVES:
            # Lỗi tạm quá số lần thử: chi tiết kỹ thuật đã ghi log ở trên, người dùng chỉ thấy câu dễ hiểu
            _mark_failed(msg, str(exc) if permanent else "Xử lý thất bại sau nhiều lần thử. Hãy tải ảnh lên lại.")
        _retry_later(msg)
        return False


def _mark_failed(msg, error):
    try:
        for _, key in _records(msg["Body"]):
            parsed = naming.parse_original_key(key)
            if parsed:
                finish_job(parsed[1], "FAILED", error)
    except Exception:
        log.exception("khong ghi duoc FAILED")


def run():
    db.init_schema()
    log.info("worker %s bat dau, queue=%s", WORKER_NAME, config.QUEUE_URL)
    while True:
        try:
            resp = _sqs.receive_message(
                QueueUrl=config.QUEUE_URL,
                MaxNumberOfMessages=5,
                WaitTimeSeconds=20,
                AttributeNames=["ApproximateReceiveCount"],
            )
        except Exception:
            log.exception("receive_message loi, thu lai sau 5s")
            time.sleep(5)
            continue
        for msg in resp.get("Messages", []):
            if handle_message(msg):
                _sqs.delete_message(QueueUrl=config.QUEUE_URL, ReceiptHandle=msg["ReceiptHandle"])


if __name__ == "__main__":
    run()
