"""Quy ước đặt tên object trên S3 (xem docs/contracts.md).

originals : {shop_id}/{job_id}/original.{ext}
processed : {shop_id}/{job_id}/{variant}.jpg   variant thuộc VARIANTS

Worker chỉ nhận được bucket + key từ S3 event, nên shop_id và job_id phải nằm trong key.
"""
import re
import uuid

# (tên, cạnh dài tối đa theo px – None là giữ nguyên kích thước, chất lượng JPEG)
VARIANTS = [
    ("full", None, 85),
    ("1080", 1080, 85),
    ("600", 600, 82),
    ("thumb", 200, 80),
]

ALLOWED_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

_ORIGINAL_RE = re.compile(
    r"^(?P<shop_id>\d+)/(?P<job_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"/original\.(?P<ext>[a-z0-9]+)$"
)


def original_key(shop_id, job_id, content_type):
    return f"{shop_id}/{job_id}/original.{ALLOWED_TYPES[content_type]}"


def processed_key(shop_id, job_id, variant):
    return f"{shop_id}/{job_id}/{variant}.jpg"


def parse_original_key(key):
    """Trả về (shop_id, job_id) hoặc None nếu key không đúng quy ước."""
    m = _ORIGINAL_RE.match(key)
    if not m:
        return None
    return int(m.group("shop_id")), str(uuid.UUID(m.group("job_id")))
