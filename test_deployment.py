"""Smoke test a running server: python test_deployment.py http://127.0.0.1:18765.

Only use against a deployment you control; this uploads generated test files.
"""

import io
import json
import sys
import urllib.error
import urllib.request
import uuid
import zipfile

import pymupdf
from PIL import Image


def main(base_url: str) -> None:
    base_url = base_url.rstrip("/")

    def request(path, data=None, headers=None):
        req = urllib.request.Request(base_url + path, data=data, headers=headers or {})
        with urllib.request.urlopen(req, timeout=600) as response:
            assert response.status == 200, path
            return response.read()

    page = request("/").decode("utf-8")
    assert "máy chủ" in page and "không tải lên internet" not in page
    for path in ("/static/app.js", "/static/style.css", "/static/vendor/motion.js"):
        assert len(request(path)) > 100, path

    def upload(name, content):
        boundary = uuid.uuid4().hex
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"target_mb\"\r\n\r\n5\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"{name}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        result = json.loads(request("/api/compress", body, {
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        }))
        assert result["job_id"] and result["output_bytes"] > 0, result
        return result

    image = io.BytesIO()
    Image.new("RGB", (120, 80), "green").save(image, format="JPEG")
    jpg = upload("smoke.jpg", image.getvalue())
    assert jpg["kind"] == "image"
    assert request("/api/download/" + jpg["job_id"]) == image.getvalue()
    preview = request(f"/api/preview/{jpg['job_id']}/out_full")
    assert preview.startswith(b"\x89PNG\r\n\x1a\n")

    with pymupdf.open() as doc:
        doc.new_page().insert_text((72, 72), "Deployment smoke test")
        pdf = upload("smoke.pdf", doc.tobytes())
    assert pdf["kind"] == "pdf" and pdf["page_count"] == 1
    with pymupdf.open(stream=request("/api/download/" + pdf["job_id"]), filetype="pdf") as doc:
        assert "Deployment smoke test" in doc[0].get_text()
    assert request(f"/api/preview/{pdf['job_id']}/out_page").startswith(b"\x89PNG\r\n\x1a\n")

    archive = request("/api/zip", json.dumps({
        "job_ids": [jpg["job_id"], pdf["job_id"]]
    }).encode(), {"Content-Type": "application/json"})
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        assert len(zf.namelist()) == 2
        assert zf.testzip() is None

    try:
        request("/api/download/invalid")
    except urllib.error.HTTPError as exc:
        assert exc.code == 400
    else:
        raise AssertionError("Invalid job ID must be rejected")
    print("PASS: HTML, static assets, image/PDF uploads, downloads, previews, ZIP, validation")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python test_deployment.py http://127.0.0.1:18765")
    main(sys.argv[1])
