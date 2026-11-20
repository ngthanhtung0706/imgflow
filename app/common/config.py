"""Đọc cấu hình từ biến môi trường. Không có giá trị bí mật nào nằm trong code.

Trên EC2, user data ghi các biến này vào /etc/imgflow/imgflow.env (chỉ là tên bucket,
URL queue, host DB... không phải mật khẩu). Mật khẩu DB lấy từ Secrets Manager lúc chạy.
Trên laptop, copy app/.env.example thành app/.env rồi điền.
"""
import hashlib
import hmac
import json
import os
import time
from pathlib import Path


def _load_dotenv():
    """Nạp app/.env nếu có (chỉ để chạy trên laptop). Không ghi đè biến đã có."""
    path = Path(__file__).resolve().parent.parent / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
ORIGINALS_BUCKET = os.environ.get("ORIGINALS_BUCKET", "")
PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET", "")
QUEUE_URL = os.environ.get("QUEUE_URL", "")
CDN_DOMAIN = os.environ.get("CDN_DOMAIN", "")

# Hoặc DATABASE_URL (laptop, Postgres trong Docker),
# hoặc DB_HOST + DB_SECRET_ARN (trên AWS, mật khẩu do RDS tự quản lý trong Secrets Manager).
DATABASE_URL = os.environ.get("DATABASE_URL", "")
DB_HOST = os.environ.get("DB_HOST", "")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ.get("DB_NAME", "imgflow")
DB_SECRET_ARN = os.environ.get("DB_SECRET_ARN", "")

EFS_ROOT = Path(os.environ.get("EFS_ROOT", "/mnt/efs"))

# Số lần nhận tối đa trước khi SQS chuyển message sang DLQ (khớp maxReceiveCount ở queue.tf)
MAX_RECEIVES = int(os.environ.get("MAX_RECEIVES", "3"))
# Khi xử lý lỗi, cho message hiện lại sau bấy nhiêu giây để thử lại nhanh
RETRY_VISIBILITY = int(os.environ.get("RETRY_VISIBILITY", "10"))

PRESIGN_EXPIRES = int(os.environ.get("PRESIGN_EXPIRES", "600"))
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))


_secret_cache = {"value": None, "at": 0.0}
_SECRET_TTL = 300  # RDS có thể xoay vòng mật khẩu, nên chỉ nhớ 5 phút


def db_credentials(force_refresh=False):
    """Trả về (username, password) từ secret RDS tự quản lý: {"username": ..., "password": ...}."""
    now = time.time()
    if force_refresh or _secret_cache["value"] is None or now - _secret_cache["at"] > _SECRET_TTL:
        import boto3

        sm = boto3.client("secretsmanager", region_name=REGION)
        raw = sm.get_secret_value(SecretId=DB_SECRET_ARN)["SecretString"]
        data = json.loads(raw)
        _secret_cache["value"] = (data["username"], data["password"])
        _secret_cache["at"] = now
    return _secret_cache["value"]


def session_secret_key():
    """Khoá ký cookie đăng nhập. Mọi máy web phải dùng CHUNG một khoá.

    Không thêm secret mới: suy ra từ mật khẩu DB (HMAC), nên mọi máy web đều có cùng
    khoá mà khoá không nằm trong repo hay user data. Trên laptop có thể đặt SECRET_KEY.
    """
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    if DATABASE_URL:
        material = DATABASE_URL
    else:
        material = db_credentials()[1]
    return hmac.new(material.encode(), b"imgflow-session-v1", hashlib.sha256).hexdigest()
