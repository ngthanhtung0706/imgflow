"""Kết nối PostgreSQL và tạo bảng.

Mỗi lần cần DB thì mở một kết nối mới (lượng truy cập nhỏ, RDS cùng VPC). Cách này
không phải giữ pool, nên sau khi RDS failover sang AZ khác thì request tiếp theo tự
kết nối lại được, không cần khởi động lại app.
"""
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from . import config

JOB_STATUSES = ("PENDING", "PROCESSING", "DONE", "FAILED")

SCHEMA = """
CREATE TABLE IF NOT EXISTS shops (
    id            SERIAL PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    display_name  TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS products (
    id         SERIAL PRIMARY KEY,
    shop_id    INT NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (shop_id, name)
);

CREATE TABLE IF NOT EXISTS images (
    id            UUID PRIMARY KEY,
    shop_id       INT NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    product_id    INT REFERENCES products(id) ON DELETE SET NULL,
    original_name TEXT NOT NULL,
    original_key  TEXT NOT NULL UNIQUE,
    content_type  TEXT NOT NULL,
    size_bytes    BIGINT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS jobs (
    id          UUID PRIMARY KEY,
    image_id    UUID NOT NULL UNIQUE REFERENCES images(id) ON DELETE CASCADE,
    shop_id     INT NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'PENDING'
                CHECK (status IN ('PENDING', 'PROCESSING', 'DONE', 'FAILED')),
    attempts    INT NOT NULL DEFAULT 0,
    error       TEXT,
    worker      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS jobs_shop_created_idx ON jobs (shop_id, created_at DESC);
"""


def _connect():
    if config.DATABASE_URL:
        return psycopg.connect(config.DATABASE_URL, row_factory=dict_row, connect_timeout=5)
    user, password = config.db_credentials()
    kwargs = dict(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=user,
        connect_timeout=5,
        sslmode="require",
        row_factory=dict_row,
    )
    try:
        return psycopg.connect(password=password, **kwargs)
    except psycopg.OperationalError as exc:
        # Mật khẩu vừa được RDS xoay vòng -> lấy lại secret rồi thử 1 lần nữa
        if "password authentication failed" not in str(exc):
            raise
        user, password = config.db_credentials(force_refresh=True)
        return psycopg.connect(password=password, **{**kwargs, "user": user})


@contextmanager
def connect():
    """with db.connect() as conn: ... – tự commit khi thành công, rollback khi lỗi."""
    conn = _connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_schema():
    """Tạo bảng nếu chưa có. An toàn khi nhiều máy cùng gọi lúc khởi động."""
    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(731901)")
        conn.execute(SCHEMA)
