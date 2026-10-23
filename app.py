"""Web server Flask cho bộ nén ảnh/PDF cục bộ."""

from __future__ import annotations

import atexit
import io
import logging
import math
import os
import re
import shutil
import sys
import tempfile
import threading
import traceback
import uuid
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory

import compress

BASE_DIR = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
HOST = "127.0.0.1"
PORT = 8765

app = Flask(__name__, static_folder=str(BASE_DIR / "static"), static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
app.json.ensure_ascii = False

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")

log = logging.getLogger("resizeassets")


def _cleanup_jobs() -> None:
    with JOBS_LOCK:
        jobs = list(JOBS.values())
        JOBS.clear()
    for job in jobs:
        shutil.rmtree(job["dir"], ignore_errors=True)


atexit.register(_cleanup_jobs)


def _safe_filename(name: str | None) -> str:
    name = (name or "upload").replace("\\", "/").split("/")[-1]
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name)
    name = name.strip().strip(".")
    return name or "upload"


def _kind_for(ext: str) -> str | None:
    if ext in compress.SUPPORTED_PDF_EXTS:
        return "pdf"
    if ext in compress.SUPPORTED_IMAGE_EXTS:
        return "image"
    return None


def _status_message(result: dict) -> str:
    status = result.get("status")
    if status == "already_small":
        return "File đã nhỏ hơn mục tiêu, giữ nguyên"
    if status == "target_not_met":
        return (
            "Không đạt mục tiêu mà vẫn giữ chất lượng chấp nhận được; "
            "đây là bản nhỏ nhất ở mức chất lượng tối thiểu"
        )
    return "Đã nén xong"


def _warnings(result: dict) -> list[str]:
    warnings: list[str] = []
    if result.get("kind") == "pdf" and not result.get("text_identical", True):
        warnings.append(
            "Không xác nhận được toàn bộ chữ trong PDF giữ nguyên. "
            "Hãy mở bản nén và kiểm tra lại nội dung."
        )
    return warnings


def _notes(result: dict) -> list[str]:
    notes: list[str] = []
    if result.get("editor_data_removed"):
        notes.append(compress.EDITOR_DATA_NOTE)
    return notes


def _public_result(result: dict, job_id: str, filename: str, target_mb: float) -> dict:
    original_bytes = int(result["original_bytes"])
    output_bytes = int(result["output_bytes"])
    reduction = (
        (1.0 - output_bytes / original_bytes) * 100.0 if original_bytes else 0.0
    )
    return {
        "job_id": job_id,
        "kind": result["kind"],
        "filename": filename,
        "output_filename": Path(result["output_path"]).name,
        "status": result["status"],
        "status_message": _status_message(result),
        "warnings": _warnings(result),
        "notes": _notes(result),
        "editor_data_removed": bool(result.get("editor_data_removed")),
        "images_recompressed": bool(result.get("images_recompressed")),
        "original_bytes": original_bytes,
        "output_bytes": output_bytes,
        "reduction_percent": round(reduction, 1),
        "original_width": result.get("original_width"),
        "original_height": result.get("original_height"),
        "output_width": result.get("output_width"),
        "output_height": result.get("output_height"),
        "format": result.get("format"),
        "quality": result.get("quality"),
        "subsampling": result.get("subsampling"),
        "dpi": result.get("dpi"),
        "page_count": result.get("page_count"),
        "text_identical": result.get("text_identical"),
        "ssim": result.get("ssim"),
        "downscaled": result.get("downscaled"),
        "target_mb": target_mb,
        "preview_mode": result["kind"],
    }


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.post("/api/compress")
def api_compress():
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "Không nhận được file. Hãy chọn lại."}), 400

    display_name = _safe_filename(uploaded.filename)
    ext = Path(display_name).suffix.lower()
    if ext not in compress.SUPPORTED_EXTS:
        supported = ", ".join(sorted(compress.SUPPORTED_EXTS))
        return (
            jsonify(
                {
                    "error": f"Định dạng không hỗ trợ ({ext or 'không có đuôi'}). "
                    f"Hỗ trợ: {supported}"
                }
            ),
            400,
        )

    try:
        target_mb = float(request.form.get("target_mb", "5"))
    except (TypeError, ValueError):
        return jsonify({"error": "Dung lượng mục tiêu không hợp lệ."}), 400
    if not math.isfinite(target_mb) or target_mb <= 0 or target_mb > 1000:
        return jsonify({"error": "Dung lượng mục tiêu phải lớn hơn 0 và không quá 1000 MB."}), 400

    kind = _kind_for(ext)
    job_id = uuid.uuid4().hex
    job_dir = Path(tempfile.mkdtemp(prefix="resizeassets_"))
    src_path = job_dir / display_name
    out_dir = job_dir / "out"

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        uploaded.save(src_path)
        target_bytes = int(target_mb * 1024 * 1024)
        if kind == "pdf":
            result = compress.compress_pdf(src_path, out_dir, target_bytes)
        else:
            result = compress.compress_image(src_path, out_dir, target_bytes)
    except ValueError as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        log.warning("Lỗi xử lý %s: %s", display_name, exc)
        return jsonify({"error": str(exc)}), 500
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        log.error("Lỗi xử lý %s:\n%s", display_name, traceback.format_exc())
        return (
            jsonify(
                {
                    "error": "Không xử lý được file này. "
                    "Hãy thử file khác hoặc kiểm tra định dạng."
                }
            ),
            500,
        )

    job = {
        "id": job_id,
        "dir": job_dir,
        "src": src_path,
        "out": Path(result["output_path"]),
        "kind": kind,
        "result": result,
        "previews": {},
    }
    with JOBS_LOCK:
        JOBS[job_id] = job

    return jsonify(_public_result(result, job_id, display_name, target_mb))


@app.get("/api/download/<job_id>")
def api_download(job_id: str):
    if not JOB_ID_RE.fullmatch(job_id):
        return jsonify({"error": "Mã job không hợp lệ."}), 400
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        return jsonify({"error": "Không tìm thấy kết quả. Hãy nén lại file."}), 404
    return send_file(
        job["out"],
        as_attachment=True,
        download_name=job["out"].name,
        mimetype="application/octet-stream",
    )


def _get_previews(job: dict, page: int) -> dict:
    with JOBS_LOCK:
        cached = job["previews"].get(page)
    if cached is not None:
        return cached
    previews = compress.make_previews(job["src"], job["out"], job["kind"], page)
    with JOBS_LOCK:
        job["previews"][page] = previews
    return previews


@app.get("/api/preview/<job_id>/<which>")
def api_preview(job_id: str, which: str):
    if not JOB_ID_RE.fullmatch(job_id):
        return jsonify({"error": "Mã job không hợp lệ."}), 400
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        return jsonify({"error": "Không tìm thấy kết quả. Hãy nén lại file."}), 404

    allowed = {
        "image": {"orig_full", "out_full", "orig_crop", "out_crop"},
        "pdf": {"orig_page", "out_page"},
    }
    if which not in allowed.get(job["kind"], set()):
        return jsonify({"error": "Loại ảnh xem trước không hợp lệ."}), 400

    if job["kind"] == "pdf":
        raw_page = request.args.get("page", "0")
        try:
            page = int(raw_page)
        except (TypeError, ValueError):
            return jsonify({"error": "Số trang không hợp lệ."}), 400
        page_count = int(job["result"].get("page_count") or 0)
        if page < 0 or page >= page_count:
            return jsonify({"error": "Số trang nằm ngoài phạm vi PDF."}), 400
    else:
        page = 0

    try:
        previews = _get_previews(job, page)
    except Exception:
        log.error("Lỗi tạo preview:\n%s", traceback.format_exc())
        return jsonify({"error": "Không tạo được ảnh so sánh."}), 500

    data = previews.get(which)
    if not isinstance(data, bytes):
        return jsonify({"error": "Không có ảnh xem trước này."}), 404
    response = send_file(io.BytesIO(data), mimetype="image/png")
    response.headers["Cache-Control"] = "private, max-age=3600"
    return response


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "File quá lớn. Giới hạn là 500 MB."}), 413


@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Không tìm thấy."}), 404
    return send_from_directory(app.static_folder, "index.html")


def _open_browser() -> None:
    webbrowser.open(f"http://{HOST}:{PORT}/")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if os.environ.get("COMPRESS_NO_BROWSER") != "1":
        threading.Timer(1.0, _open_browser).start()
    print(f"Đang chạy tại http://{HOST}:{PORT}/  (Ctrl+C để dừng)")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
