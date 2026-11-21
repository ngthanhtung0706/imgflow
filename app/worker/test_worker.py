"""Test worker bằng moto (S3/SQS giả) + Postgres thật (DATABASE_URL trong app/.env).

Chạy:  cd app && pip install pytest "moto[s3,sqs]" && python -m pytest worker -q
"""
import io
import json
import os
import uuid

os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ["AWS_DEFAULT_REGION"] = "ap-southeast-2"

import boto3
import pytest
from moto import mock_aws
from PIL import Image

from common import config, db, naming

config.ORIGINALS_BUCKET = "t-originals"
config.PROCESSED_BUCKET = "t-processed"


@pytest.fixture()
def env():
    with mock_aws():
        s3 = boto3.client("s3", region_name=config.REGION)
        sqs = boto3.client("sqs", region_name=config.REGION)
        loc = {"LocationConstraint": config.REGION}
        s3.create_bucket(Bucket=config.ORIGINALS_BUCKET, CreateBucketConfiguration=loc)
        s3.create_bucket(Bucket=config.PROCESSED_BUCKET, CreateBucketConfiguration=loc)
        config.QUEUE_URL = sqs.create_queue(QueueName="jobs")["QueueUrl"]

        from worker import worker

        worker._s3, worker._sqs = s3, sqs  # client tạo lúc import nằm ngoài mock_aws
        db.init_schema()
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO shops (username, display_name, password_hash) VALUES (%s, 't', 'x') "
                "ON CONFLICT (username) DO NOTHING",
                ("worker_test",),
            )
            shop_id = conn.execute("SELECT id FROM shops WHERE username = 'worker_test'").fetchone()["id"]
        yield worker, s3, sqs, shop_id


def _jpeg(size=(3000, 2000), fmt="JPEG", mode="RGB"):
    buf = io.BytesIO()
    Image.new(mode, size, (200, 80, 40)[: len(mode)] if mode != "RGBA" else (200, 80, 40, 0)).save(buf, fmt)
    return buf.getvalue()


def _new_job(shop_id, ext="jpg"):
    job_id = uuid.uuid4()
    key = f"{shop_id}/{job_id}/original.{ext}"
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO images (id, shop_id, original_name, original_key, content_type) "
            "VALUES (%s, %s, 'a', %s, 'image/jpeg')",
            (job_id, shop_id, key),
        )
        conn.execute("INSERT INTO jobs (id, image_id, shop_id) VALUES (%s, %s, %s)", (job_id, job_id, shop_id))
    return job_id, key


def _status(job_id):
    with db.connect() as conn:
        return conn.execute("SELECT status, attempts, error FROM jobs WHERE id = %s", (job_id,)).fetchone()


def _message(key, receives=1):
    event = {"Records": [{"eventName": "ObjectCreated:Put",
                          "s3": {"bucket": {"name": config.ORIGINALS_BUCKET}, "object": {"key": key}}}]}
    return {"Body": json.dumps(event), "ReceiptHandle": "rh",
            "Attributes": {"ApproximateReceiveCount": str(receives)}}


def test_tao_du_4_ban_co_watermark(env):
    worker, s3, _, shop_id = env
    job_id, key = _new_job(shop_id)
    original = _jpeg()
    s3.put_object(Bucket=config.ORIGINALS_BUCKET, Key=key, Body=original)

    assert worker.process_object(config.ORIGINALS_BUCKET, key) is True

    assert _status(job_id)["status"] == "DONE"
    sizes = {}
    for name, max_side, _ in naming.VARIANTS:
        body = s3.get_object(Bucket=config.PROCESSED_BUCKET,
                             Key=naming.processed_key(shop_id, job_id, name))["Body"].read()
        img = Image.open(io.BytesIO(body))
        assert img.format == "JPEG"
        sizes[name] = max(img.size)
        if max_side:
            assert max(img.size) <= max_side
    assert sizes["full"] == 3000 and sizes["1080"] == 1080 and sizes["thumb"] == 200
    # watermark thật sự được vẽ: góc phải dưới khác màu nền gốc
    full = Image.open(io.BytesIO(s3.get_object(Bucket=config.PROCESSED_BUCKET,
                                               Key=naming.processed_key(shop_id, job_id, "full"))["Body"].read()))
    corner = full.crop((full.width - 400, full.height - 150, full.width, full.height))
    assert len(set(corner.getdata())) > 20


def test_png_trong_suot_khong_vo(env):
    worker, s3, _, shop_id = env
    job_id, key = _new_job(shop_id, "png")
    s3.put_object(Bucket=config.ORIGINALS_BUCKET, Key=key, Body=_jpeg((400, 300), "PNG", "RGBA"))
    worker.process_object(config.ORIGINALS_BUCKET, key)
    assert _status(job_id)["status"] == "DONE"


def test_xu_ly_lai_message_trung_khong_lam_lai(env):
    worker, s3, _, shop_id = env
    job_id, key = _new_job(shop_id)
    s3.put_object(Bucket=config.ORIGINALS_BUCKET, Key=key, Body=_jpeg((500, 400)))
    assert worker.process_object(config.ORIGINALS_BUCKET, key) is True
    assert worker.process_object(config.ORIGINALS_BUCKET, key) is False
    assert _status(job_id)["attempts"] == 1


def test_file_hong_thanh_FAILED_va_xoa_message(env):
    worker, s3, _, shop_id = env
    job_id, key = _new_job(shop_id)
    s3.put_object(Bucket=config.ORIGINALS_BUCKET, Key=key, Body=b"khong phai anh")
    assert worker.handle_message(_message(key)) is True
    st = _status(job_id)
    assert st["status"] == "FAILED" and "anh" in st["error"]


def test_loi_tam_thoi_giu_message_den_lan_thu_3(env):
    worker, s3, sqs, shop_id = env
    job_id, key = _new_job(shop_id)  # chưa upload ảnh lên S3 -> NoSuchKey
    sqs.send_message(QueueUrl=config.QUEUE_URL, MessageBody="x")
    receipt = sqs.receive_message(QueueUrl=config.QUEUE_URL)["Messages"][0]["ReceiptHandle"]

    msg = _message(key, receives=1) | {"ReceiptHandle": receipt}
    assert worker.handle_message(msg) is False          # giữ lại để thử lại
    assert _status(job_id)["status"] == "PROCESSING"

    msg = _message(key, receives=config.MAX_RECEIVES) | {"ReceiptHandle": receipt}
    assert worker.handle_message(msg) is False          # message sang DLQ, job báo lỗi
    assert _status(job_id)["status"] == "FAILED"


def test_bo_qua_s3_test_event_va_key_la(env):
    worker, *_ = env
    assert worker.handle_message({"Body": json.dumps({"Event": "s3:TestEvent"}), "ReceiptHandle": "r"}) is True
    assert worker.handle_message(_message("linh-tinh/abc.jpg")) is True


# ---------------------------------------------------------------- logo watermark (không cần DB)
def _logo_png(color=(0, 255, 0, 255), size=(300, 100)):
    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, "PNG")
    return buf.getvalue()


def test_logo_rieng_duoc_dong_len_anh(monkeypatch):
    from worker import worker
    monkeypatch.setattr(worker, "_load_logo", lambda shop_id=None: Image.open(io.BytesIO(_logo_png())).convert("RGBA"))
    out = worker.make_variants(_jpeg((1000, 800)), shop_id=1)
    img = Image.open(io.BytesIO(out["full"]))
    corner = img.crop((img.width - 260, img.height - 100, img.width, img.height))
    # nền gốc là (200, 80, 40); logo xanh lá pha vào làm giảm đỏ, tăng xanh
    assert any(g > 95 and r < 160 for r, g, b in corner.getdata())


def test_logo_hong_hoac_qua_to_bi_bo_qua():
    from worker import worker
    assert worker._open_logo(io.BytesIO(b"khong phai png")) is None
    assert worker._open_logo(io.BytesIO(_logo_png(size=(3000, 2000)))) is None  # 6 triệu điểm ảnh > giới hạn
    assert worker._open_logo(io.BytesIO(_logo_png())) is not None
