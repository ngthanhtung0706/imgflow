"""ImgFlow web/API.

Chạy trên laptop:   cd app && flask --app web.app run --port 8000 --debug
Chạy trên EC2:      gunicorn -c web/gunicorn.conf.py web.app:app   (xem deploy/install_web.sh)

Đăng nhập lưu trong cookie có ký (session của Flask), không lưu trong RAM,
nên request rơi vào máy web nào sau ALB cũng vẫn nhận ra người dùng.
"""
import logging
import uuid
from functools import wraps

import boto3
from botocore.config import Config
from flask import Flask, Response, abort, jsonify, redirect, render_template, request, session, url_for
from flask.sessions import SecureCookieSessionInterface
from werkzeug.security import check_password_hash, generate_password_hash

from common import config, db, naming

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("imgflow.web")

app = Flask(__name__)
app.config.update(
    SESSION_COOKIE_NAME="imgflow_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=7 * 24 * 3600,
    MAX_CONTENT_LENGTH=1024 * 1024,  # chỉ nhận JSON nhỏ, ảnh đi thẳng lên S3
)

# Dùng endpoint theo region + SigV4, nếu không presigned URL có thể bị chuyển hướng và lỗi CORS
_s3 = boto3.client(
    "s3",
    region_name=config.REGION,
    endpoint_url=f"https://s3.{config.REGION}.amazonaws.com",
    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
)

class _LazyKeySessionInterface(SecureCookieSessionInterface):
    """Lấy khoá ký cookie ở request đầu tiên thay vì lúc import.

    Nhờ vậy app vẫn khởi động và /healthz vẫn trả 200 khi RDS/secret chưa có.
    """

    def get_signing_serializer(self, app):
        if not app.secret_key:
            try:
                app.secret_key = config.session_secret_key()
            except Exception:
                log.exception("chua lay duoc khoa ky cookie (RDS dang tat?)")
                return None
        return super().get_signing_serializer(app)


app.session_interface = _LazyKeySessionInterface()

_schema_ready = False


@app.before_request
def _before():
    """Tạo bảng ở request đầu tiên. /healthz không đụng DB để ALB vẫn thấy máy khoẻ."""
    global _schema_ready
    if request.endpoint in ("healthz", "static") or _schema_ready:
        return
    db.init_schema()
    _schema_ready = True


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "shop_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify(error="chua dang nhap"), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapper


def _cdn_url(key):
    if config.CDN_DOMAIN:
        return f"https://{config.CDN_DOMAIN}/{key}"
    # Trên laptop chưa có CloudFront: dùng presigned GET (cần quyền đọc bucket processed)
    return _s3.generate_presigned_url(
        "get_object", Params={"Bucket": config.PROCESSED_BUCKET, "Key": key}, ExpiresIn=3600
    )


def _job_json(row):
    data = {
        "job_id": str(row["id"]),
        "status": row["status"],
        "name": row["original_name"],
        "product": row.get("product_name"),
        "attempts": row["attempts"],
        "error": row["error"],
        "worker": row.get("worker"),
        "size_bytes": row.get("size_bytes"),
        "created_at": row["created_at"].isoformat(),
        "started_at": row["started_at"].isoformat() if row.get("started_at") else None,
        "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
        "duration_s": None,
        "urls": None,
    }
    if row.get("started_at") and row["finished_at"]:
        data["duration_s"] = round((row["finished_at"] - row["started_at"]).total_seconds(), 1)
    if row["status"] == "DONE":
        data["urls"] = {
            v: _cdn_url(naming.processed_key(row["shop_id"], row["id"], v)) for v, _, _ in naming.VARIANTS
        }
    return data


# ---------------------------------------------------------------- trang HTML
@app.get("/healthz")
def healthz():
    return "ok", 200


@app.get("/")
def index():
    return redirect(url_for("gallery" if "shop_id" in session else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        form = request.get_json(silent=True) or request.form
        username = (form.get("username") or "").strip().lower()
        password = form.get("password") or ""
        with db.connect() as conn:
            shop = conn.execute("SELECT * FROM shops WHERE username = %s", (username,)).fetchone()
        if shop and check_password_hash(shop["password_hash"], password):
            session.clear()
            session.permanent = True
            session["shop_id"] = shop["id"]
            session["shop_name"] = shop["display_name"]
            if request.is_json:
                return jsonify(shop_id=shop["id"])
            return redirect(url_for("gallery"))
        error = "Sai tên đăng nhập hoặc mật khẩu"
        if request.is_json:
            return jsonify(error=error), 401
    return render_template("login.html", error=error)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Tạo shop mới. Không có tài khoản mặc định trong code để không lộ mật khẩu trong repo."""
    error = None
    if request.method == "POST":
        form = request.get_json(silent=True) or request.form
        username = (form.get("username") or "").strip().lower()
        display_name = (form.get("display_name") or "").strip() or username
        password = form.get("password") or ""
        if not username.isascii() or not username.replace("_", "").replace("-", "").isalnum():
            error = "Tên đăng nhập chỉ gồm chữ không dấu, số, - và _"
        elif len(password) < 6:
            error = "Mật khẩu tối thiểu 6 ký tự"
        else:
            with db.connect() as conn:
                row = conn.execute(
                    "INSERT INTO shops (username, display_name, password_hash) VALUES (%s, %s, %s) "
                    "ON CONFLICT (username) DO NOTHING RETURNING id",
                    (username, display_name[:60], generate_password_hash(password)),
                ).fetchone()
            if row is None:
                error = "Tên đăng nhập đã tồn tại"
            else:
                session.clear()
                session.permanent = True
                session["shop_id"] = row["id"]
                session["shop_name"] = display_name[:60]
                if request.is_json:
                    return jsonify(shop_id=row["id"]), 201
                return redirect(url_for("gallery"))
        if request.is_json:
            return jsonify(error=error), 400
    return render_template("register.html", error=error)


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/gallery")
@login_required
def gallery():
    return render_template("gallery.html", shop_name=session.get("shop_name"))


# ---------------------------------------------------------------- API
@app.post("/api/uploads")
@login_required
def create_uploads():
    """Tạo job PENDING cho mỗi file và trả presigned URL để trình duyệt PUT thẳng lên S3.

    Body: {"product": "Áo thun" (tuỳ chọn), "files": [{"name": "a.jpg", "type": "image/jpeg", "size": 123}]}
    Trả:  {"uploads": [{"job_id", "name", "url", "headers": {"Content-Type": ...}}]}
    """
    body = request.get_json(silent=True) or {}
    files = body.get("files") or []
    if not isinstance(files, list) or not 1 <= len(files) <= 500:
        return jsonify(error="can 1-500 file"), 400

    for f in files:
        if f.get("type") not in naming.ALLOWED_TYPES:
            return jsonify(error=f"khong ho tro dinh dang {f.get('type')} ({f.get('name')})"), 400
        size = f.get("size")
        if size is not None and not (isinstance(size, int) and 0 < size <= config.MAX_UPLOAD_BYTES):
            return jsonify(error=f"file {f.get('name')} rong hoac qua lon"), 400

    shop_id = session["shop_id"]
    product_name = (body.get("product") or "").strip()[:100]
    uploads = []
    with db.connect() as conn:
        product_id = None
        if product_name:
            product_id = conn.execute(
                "INSERT INTO products (shop_id, name) VALUES (%s, %s) "
                "ON CONFLICT (shop_id, name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
                (shop_id, product_name),
            ).fetchone()["id"]

        for f in files:
            job_id = uuid.uuid4()
            content_type = f["type"]
            key = naming.original_key(shop_id, job_id, content_type)
            name = (f.get("name") or "image")[:200]
            # job_id dùng luôn làm id của image để dễ đối chiếu
            conn.execute(
                "INSERT INTO images (id, shop_id, product_id, original_name, original_key, content_type, size_bytes) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (job_id, shop_id, product_id, name, key, content_type, f.get("size")),
            )
            conn.execute(
                "INSERT INTO jobs (id, image_id, shop_id, status) VALUES (%s, %s, %s, 'PENDING')",
                (job_id, job_id, shop_id),
            )
            url = _s3.generate_presigned_url(
                "put_object",
                Params={"Bucket": config.ORIGINALS_BUCKET, "Key": key, "ContentType": content_type},
                ExpiresIn=config.PRESIGN_EXPIRES,
            )
            uploads.append(
                {"job_id": str(job_id), "name": name, "url": url, "headers": {"Content-Type": content_type}}
            )

    log.info("shop=%s tao %d job", shop_id, len(uploads))
    return jsonify(uploads=uploads), 201


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_LOGO_BYTES = 512 * 1024


@app.get("/api/logo")
@login_required
def get_logo():
    """Trả logo PNG của shop đang đăng nhập, 404 nếu shop chưa có (worker sẽ dùng logo mặc định)."""
    with db.connect() as conn:
        row = conn.execute("SELECT logo FROM shops WHERE id = %s", (session["shop_id"],)).fetchone()
    if not row or not row["logo"]:
        abort(404)
    return Response(
        bytes(row["logo"]),
        mimetype="image/png",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.post("/api/logo")
@login_required
def upload_logo():
    """Shop upload logo watermark riêng (form-data, trường 'logo', PNG tối đa 512 KB)."""
    f = request.files.get("logo")
    if f is None:
        return jsonify(error="Chưa chọn file logo."), 400
    data = f.read(MAX_LOGO_BYTES + 1)
    if len(data) > MAX_LOGO_BYTES:
        return jsonify(error="Logo tối đa 512 KB."), 400
    if not data.startswith(PNG_SIGNATURE):
        return jsonify(error="Logo phải là file PNG."), 400
    with db.connect() as conn:
        conn.execute("UPDATE shops SET logo = %s WHERE id = %s", (data, session["shop_id"]))
    log.info("shop=%s cap nhat logo (%d byte)", session["shop_id"], len(data))
    return jsonify(ok=True), 200


@app.delete("/api/logo")
@login_required
def delete_logo():
    """Xoá logo riêng, quay về logo mặc định."""
    with db.connect() as conn:
        conn.execute("UPDATE shops SET logo = NULL WHERE id = %s", (session["shop_id"],))
    return jsonify(ok=True)


_JOB_SELECT = """
SELECT j.id, j.shop_id, j.status, j.attempts, j.error, j.worker, j.created_at, j.started_at, j.finished_at,
       i.original_name, i.size_bytes, p.name AS product_name
FROM jobs j
JOIN images i ON i.id = j.image_id
LEFT JOIN products p ON p.id = i.product_id
"""


@app.get("/api/jobs")
@login_required
def list_jobs():
    limit = min(int(request.args.get("limit", 300)), 1000)
    with db.connect() as conn:
        rows = conn.execute(
            _JOB_SELECT + " WHERE j.shop_id = %s ORDER BY j.created_at DESC LIMIT %s",
            (session["shop_id"], limit),
        ).fetchall()
        counts = conn.execute(
            "SELECT status, count(*) AS n FROM jobs WHERE shop_id = %s GROUP BY status",
            (session["shop_id"],),
        ).fetchall()
    summary = {s: 0 for s in db.JOB_STATUSES}
    summary.update({r["status"]: r["n"] for r in counts})
    return jsonify(summary=summary, jobs=[_job_json(r) for r in rows])


@app.get("/api/stats")
@login_required
def stats():
    """Số liệu cho bảng theo dõi xử lý của shop: tốc độ, thời gian xử lý, các worker gần đây."""
    shop_id = session["shop_id"]
    with db.connect() as conn:
        per_minute = conn.execute(
            "SELECT count(*) AS n FROM jobs WHERE shop_id = %s AND status = 'DONE' "
            "AND finished_at > now() - interval '60 seconds'",
            (shop_id,),
        ).fetchone()["n"]
        avg = conn.execute(
            "SELECT avg(extract(epoch FROM finished_at - started_at)) AS s FROM ("
            "  SELECT started_at, finished_at FROM jobs WHERE shop_id = %s AND status = 'DONE' "
            "  AND started_at IS NOT NULL AND finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT 100"
            ") t",
            (shop_id,),
        ).fetchone()["s"]
        workers = conn.execute(
            "SELECT worker, count(*) FILTER (WHERE status = 'PROCESSING') AS active, "
            "       count(*) FILTER (WHERE status = 'DONE') AS done "
            "FROM jobs WHERE shop_id = %s AND worker IS NOT NULL "
            "AND (status = 'PROCESSING' OR started_at > now() - interval '5 minutes') "
            "GROUP BY worker ORDER BY worker",
            (shop_id,),
        ).fetchall()
    return jsonify(
        done_last_minute=per_minute,
        avg_seconds=round(float(avg), 1) if avg is not None else None,
        workers=[{"name": w["worker"], "active": w["active"], "done": w["done"]} for w in workers],
    )


@app.get("/api/jobs/<job_id>")
@login_required
def get_job(job_id):
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        abort(404)
    with db.connect() as conn:
        row = conn.execute(
            _JOB_SELECT + " WHERE j.id = %s AND j.shop_id = %s", (job_uuid, session["shop_id"])
        ).fetchone()
    if row is None:
        abort(404)
    return jsonify(_job_json(row))


@app.errorhandler(Exception)
def _unhandled(exc):
    from werkzeug.exceptions import HTTPException

    if isinstance(exc, HTTPException):
        return exc
    log.exception("loi khong mong doi")
    if request.path.startswith("/api/"):
        return jsonify(error="loi may chu"), 500
    return render_template("error.html"), 500
