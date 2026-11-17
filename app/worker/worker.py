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


# ---------------------------------------------------------------- ảnh
def _load_font(size):
    path = config.EFS_ROOT / "font.ttf"
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default(size)  # chạy laptop / EFS chưa mount


def _load_logo():
    try:
        return Image.open(config.EFS_ROOT / "logo.png").convert("RGBA")
    except OSError:
        return None


def add_watermark(img, logo=None):
    """Đóng dấu ở góc phải dưới: logo từ EFS nếu có, không thì chữ."""
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


def make_variants(data):
    """bytes ảnh gốc -> {tên bản: bytes JPEG}."""
    try:
        src = Image.open(io.BytesIO(data))
        src.load()
    except Exception as exc:  # Pillow ném nhiều loại lỗi khác nhau cho file hỏng
        raise PermanentError(f"khong doc duoc anh: {exc}") from exc

    src = ImageOps.exif_transpose(src)
    if src.mode in ("RGBA", "LA", "P"):
        rgba = src.convert("RGBA")
        base = Image.new("RGB", rgba.size, (255, 255, 255))  # PNG trong suốt -> nền trắng
        base.paste(rgba, mask=rgba.getchannel("A"))
        src = base
    else:
        src = src.convert("RGB")

    logo = _load_logo()
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
    """Đánh dấu PROCESSING và tăng attempts. Trả về None nếu job không cần làm nữa."""
    with db.connect() as conn:
        row = conn.execute(
            "UPDATE jobs SET status = 'PROCESSING', attempts = attempts + 1, worker = %s, "
            "started_at = now(), error = NULL "
            "WHERE id = %s AND status IN ('PENDING', 'PROCESSING', 'FAILED') RETURNING attempts",
            (WORKER_NAME, job_id),
        ).fetchone()
        if row:
            return row["attempts"]
        exists = conn.execute("SELECT status FROM jobs WHERE id = %s", (job_id,)).fetchone()
    if exists is None:
        raise RuntimeError(f"chua thay job {job_id} trong DB")  # có thể do trễ, cho thử lại
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
    variants = make_variants(data)
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


def handle_message(msg):
    """Xử lý một message SQS. Trả về True nếu được phép xoá message."""
    receives = int(msg.get("Attributes", {}).get("ApproximateReceiveCount", 1))
    try:
        for bucket, key in _records(msg["Body"]):
            process_object(bucket, key)
        return True
    except Exception as exc:
        permanent = isinstance(exc, PermanentError)
        log.warning("loi (lan nhan %d, %s): %s", receives, "vinh vien" if permanent else "tam thoi", exc)
        if permanent or receives >= config.MAX_RECEIVES:
            _mark_failed(msg, str(exc))
        if permanent:
            return True  # thử lại vô ích; không xoá thì cũng chỉ chạy lại 3 lần rồi vào DLQ
        # Lỗi tạm: cho message hiện lại sớm. Quá MAX_RECEIVES thì SQS tự chuyển sang DLQ.
        _sqs.change_message_visibility(
            QueueUrl=config.QUEUE_URL,
            ReceiptHandle=msg["ReceiptHandle"],
            VisibilityTimeout=config.RETRY_VISIBILITY,
        )
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
