"""Upload ảnh song song qua API ImgFlow và chờ trạng thái job."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from getpass import getpass
import os
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

import requests


MAX_UPLOADS_PER_REQUEST = 500
MAX_IMAGE_BYTES = 25 * 1024 * 1024
CORRUPT_IMAGE = b"ImgFlow load test: invalid JPEG"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--image", required=True, type=Path, help="Tệp JPEG hợp lệ")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--include-corrupt", action="store_true")
    parser.add_argument("--wait-seconds", type=float, default=600)
    args = parser.parse_args()
    if not 1 <= args.count <= MAX_UPLOADS_PER_REQUEST - int(args.include_corrupt):
        parser.error("Cần ít nhất 1 ảnh tốt và tổng số ảnh không quá 500.")
    if args.workers < 1 or args.wait_seconds <= 0:
        parser.error("--workers và --wait-seconds phải lớn hơn 0.")
    return args


def checked_json(response, expected_status, operation):
    if response.status_code != expected_status:
        raise RuntimeError(f"{operation}: HTTP {response.status_code}")
    return response.json()


def put_image(upload, content):
    try:
        with requests.put(
            upload["url"],
            headers=upload["headers"],
            data=content,
            timeout=(10, 60),
            allow_redirects=False,
        ) as response:
            return response.status_code, None
    except requests.RequestException as exc:
        # Không in exc vì thông báo lỗi có thể chứa presigned URL.
        return None, type(exc).__name__


def wait_for_jobs(session, base_url, pending_ids, deadline):
    observed = {}
    pending = set(pending_ids)
    while pending:
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        response = session.get(
            f"{base_url}/api/jobs",
            params={"limit": 1000},
            timeout=min(15, remaining),
            allow_redirects=False,
        )
        result = checked_json(response, 200, "Tra trạng thái")
        for job in result["jobs"]:
            job_id = job["job_id"]
            if job_id in pending and job["status"] in {"DONE", "FAILED"}:
                observed[job_id] = job["status"]
                pending.remove(job_id)
        if pending:
            sleep(max(0, min(3, deadline - monotonic())))
    return observed


def run(args, session):
    base_url = args.base_url.rstrip("/")
    with args.image.open("rb") as image:
        sample = image.read(MAX_IMAGE_BYTES + 1)
    if len(sample) > MAX_IMAGE_BYTES or not sample.startswith(b"\xff\xd8\xff"):
        raise RuntimeError("Ảnh mẫu phải là JPEG hợp lệ, tối đa 25 MiB.")

    run_id = uuid4().hex[:8]
    contents = {f"{run_id}-{i:04d}.jpg": sample for i in range(1, args.count + 1)}
    corrupt_name = f"{run_id}-corrupt.jpg"
    if args.include_corrupt:
        contents[corrupt_name] = CORRUPT_IMAGE

    password = os.environ.get("IMGFLOW_PASSWORD") or getpass("Mật khẩu shop: ")
    checked_json(
        session.post(
            f"{base_url}/login",
            json={"username": args.username, "password": password},
            timeout=20,
            allow_redirects=False,
        ),
        200,
        "Đăng nhập",
    )

    print(f"run={run_id} bắt đầu UTC={datetime.now(timezone.utc).isoformat()}", flush=True)
    started_at = monotonic()
    payload = {
        "product": f"Load test {run_id}",
        "files": [
            {"name": name, "type": "image/jpeg", "size": len(data)}
            for name, data in contents.items()
        ],
    }
    response = session.post(
        f"{base_url}/api/uploads", json=payload, timeout=60, allow_redirects=False
    )
    uploads = checked_json(response, 201, "Cấp presigned URL")["uploads"]
    if len(uploads) != len(contents) or {item["name"] for item in uploads} != set(contents):
        raise RuntimeError("Danh sách presigned URL không khớp các file đã gửi.")
    upload_start = monotonic()
    expected = {}
    upload_bytes = 0
    corrupt_id = None
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(put_image, item, contents[item["name"]]): item for item in uploads}
        for future in as_completed(futures):
            item = futures[future]
            name, job_id = item["name"], item["job_id"]
            status, error = future.result()
            if status is None or not 200 <= status < 300:
                print(f"PUT lỗi: {name} job={job_id} HTTP={status} lỗi={error}", flush=True)
                continue
            if name == corrupt_name:
                corrupt_id = job_id
            expected[job_id] = "FAILED" if name == corrupt_name else "DONE"
            upload_bytes += len(contents[name])

    upload_end = monotonic()
    elapsed = upload_end - upload_start
    print(f"Cấp URL: {upload_start - started_at:.2f} s")
    print(f"PUT: {len(expected)}/{len(uploads)} thành công trong {elapsed:.2f} s"
          f" | {upload_bytes / (1024 ** 2) / max(elapsed, 0.001):.2f} MiB/s", flush=True)
    if corrupt_id:
        print(f"Job ảnh hỏng: {corrupt_id}", flush=True)

    observed = wait_for_jobs(session, base_url, expected, upload_end + args.wait_seconds)
    counts = Counter(observed.values())
    print(f"DONE={counts['DONE']} FAILED={counts['FAILED']} chưa kết thúc={len(expected) - len(observed)}")
    for job_id, status in expected.items():
        actual = observed.get(job_id, "TIMEOUT")
        if actual != status:
            print(f"Job {job_id}: chờ {status}, nhận {actual}")
    print(f"kết thúc UTC={datetime.now(timezone.utc).isoformat()}"
          f" | tổng cấp URL + PUT + chờ: {monotonic() - started_at:.2f} s")
    return 0 if len(expected) == len(uploads) and observed == expected else 1


def main():
    args = parse_args()
    try:
        with requests.Session() as session:
            return run(args, session)
    except requests.RequestException as exc:
        print(f"Lỗi HTTP hoặc dữ liệu API: {type(exc).__name__}")
    except (OSError, RuntimeError, KeyError, ValueError) as exc:
        print(f"Lỗi: {exc}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
