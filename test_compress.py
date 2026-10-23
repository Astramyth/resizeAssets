"""Tự kiểm tra bộ nén bằng assert thuần, không cần pytest.

Chạy: .venv\\Scripts\\python test_compress.py
"""

from __future__ import annotations

import hashlib
import io
import sys
import time
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image

import compress

ROOT = Path(__file__).resolve().parent
TESTDATA = ROOT / "_testdata"
INPUTS = TESTDATA / "inputs"
RUN_DIR = TESTDATA / f"out_{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000) % 1000}"
TARGET_SMALL = int(0.5 * 1024 * 1024)

CHECKS = 0


def check(condition: bool, message: str) -> None:
    global CHECKS
    if not condition:
        raise AssertionError(message)
    CHECKS += 1
    print(f"PASS: {message}")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def make_noise_png(path: Path, w: int = 3000, h: int = 2000) -> None:
    rng = np.random.default_rng(12345)
    yy, xx = np.mgrid[0:h, 0:w]
    base = np.empty((h, w, 3), dtype=np.int16)
    base[..., 0] = (xx * 255 // max(1, w - 1)).astype(np.int16)
    base[..., 1] = (yy * 255 // max(1, h - 1)).astype(np.int16)
    base[..., 2] = ((xx + yy) * 255 // max(1, w + h - 2)).astype(np.int16)
    base += rng.integers(-18, 19, (h, w, 3), dtype=np.int16)
    arr = np.clip(base, 0, 255).astype(np.uint8)
    Image.fromarray(arr, "RGB").save(path)


def make_alpha_png(path: Path, w: int = 1800, h: int = 1200) -> None:
    rng = np.random.default_rng(777)
    yy, xx = np.mgrid[0:h, 0:w]
    arr = np.empty((h, w, 4), dtype=np.uint8)
    arr[..., 0] = (xx * 255 // max(1, w - 1)).astype(np.uint8)
    arr[..., 1] = (yy * 255 // max(1, h - 1)).astype(np.uint8)
    arr[..., 2] = 150
    alpha = np.full((h, w), 255, dtype=np.int16)
    alpha[150:900, 250:1300] = 70
    alpha = np.clip(alpha + rng.integers(-8, 9, (h, w), dtype=np.int16), 0, 255)
    arr[..., 3] = alpha.astype(np.uint8)
    Image.fromarray(arr, "RGBA").save(path)


def make_small_jpeg(path: Path) -> None:
    yy, xx = np.mgrid[0:200, 0:300]
    arr = np.stack(
        [
            (xx * 255 // 299).astype(np.uint8),
            (yy * 255 // 199).astype(np.uint8),
            np.full((200, 300), 120, dtype=np.uint8),
        ],
        axis=-1,
    )
    Image.fromarray(arr, "RGB").save(path, format="JPEG", quality=80)


def make_pdf(path: Path, image_bytes: bytes) -> None:
    doc = pymupdf.open()
    try:
        for i in range(3):
            page = doc.new_page(width=595, height=842)
            page.insert_text((60, 70), f"Invoice 00{i + 1} - Resize Assets test", fontsize=16)
            page.insert_text((60, 96), "Customer: Nguyen Van A", fontsize=11)
            page.insert_text((60, 114), "Total: 1,250,000 VND", fontsize=11)
            page.insert_image(pymupdf.Rect(50, 140, 545, 640), stream=image_bytes)
        doc.save(path, garbage=4, deflate=True)
    finally:
        doc.close()


def main() -> int:
    global CHECKS
    TESTDATA.mkdir(parents=True, exist_ok=True)
    INPUTS.mkdir(parents=True, exist_ok=True)
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    print("Đang tạo dữ liệu kiểm tra...")
    noise_png = INPUTS / "noise_3000x2000.png"
    alpha_png = INPUTS / "alpha_1800x1200.png"
    small_jpg = INPUTS / "small_300x200.jpg"
    pdf_path = INPUTS / "invoice_3_pages.pdf"
    encrypted_pdf = INPUTS / "encrypted.pdf"

    make_noise_png(noise_png)
    make_alpha_png(alpha_png)
    make_small_jpeg(small_jpg)

    rng = np.random.default_rng(99)
    arr = np.clip(
        np.stack(
            [
                np.linspace(0, 255, 2400, dtype=np.float32)[None, :].repeat(1600, 0),
                np.linspace(0, 255, 1600, dtype=np.float32)[:, None].repeat(2400, 1),
                np.full((1600, 2400), 130, dtype=np.float32),
            ],
            axis=-1,
        )
        + rng.normal(0, 9, (1600, 2400, 3)),
        0,
        255,
    ).astype(np.uint8)
    jpg_buf = io.BytesIO()
    Image.fromarray(arr, "RGB").save(jpg_buf, format="JPEG", quality=92)
    make_pdf(pdf_path, jpg_buf.getvalue())

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Encrypted test")
    doc.save(
        encrypted_pdf,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner-secret",
        user_pw="user-secret",
    )
    doc.close()

    sources = [noise_png, alpha_png, small_jpg, pdf_path]
    before = {p: sha256(p) for p in sources}

    # 1. SSIM cơ bản
    a = np.tile(np.linspace(0, 255, 256, dtype=np.float32), (128, 1))
    check(abs(compress.ssim(a, a) - 1.0) < 1e-9, "SSIM ảnh giống hệt bằng 1.0")
    noisy = np.clip(a + np.random.default_rng(5).normal(0, 12, a.shape), 0, 255).astype(np.float32)
    check(compress.ssim(a, noisy) < compress.ssim(a, a), "SSIM giảm khi ảnh bị nhiễu")

    # 2. Nén PNG nhiễu về 0.5 MB
    img_result = compress.compress_image(noise_png, RUN_DIR, TARGET_SMALL)
    print(
        f"  noise.png -> {Path(img_result['output_path']).name}, "
        f"{img_result['output_bytes'] / 1024 / 1024:.2f} MB, {img_result['status']}, "
        f"SSIM {img_result['ssim']}"
    )
    check(
        img_result["status"] != "target_not_met"
        and img_result["output_bytes"] <= TARGET_SMALL,
        "Ảnh nén không vượt mục tiêu khi trạng thái không phải target_not_met",
    )
    check(
        Path(img_result["output_path"]).suffix.lower() == ".jpg",
        "Ảnh không có alpha được lưu thành JPEG",
    )
    check(
        img_result["output_width"] != img_result["original_width"]
        or img_result["quality"] is not None,
        "Ảnh có thông tin độ phân giải/chất lượng đầu ra",
    )
    first_output = Path(img_result["output_path"])

    # 3. Chạy lần hai không ghi đè
    img_result_2 = compress.compress_image(noise_png, RUN_DIR, TARGET_SMALL)
    second_output = Path(img_result_2["output_path"])
    check(first_output.exists(), "File kết quả lần một vẫn còn sau lần chạy thứ hai")
    check(second_output != first_output, "Lần chạy thứ hai tạo file mới, không ghi đè")
    check(
        second_output.stem.endswith("_2"),
        "Tên file lần hai có hậu tố _2",
    )

    # 4. RGBA -> WebP
    alpha_target = int(1.0 * 1024 * 1024)
    alpha_result = compress.compress_image(alpha_png, RUN_DIR, alpha_target)
    print(
        f"  alpha.png -> {Path(alpha_result['output_path']).name}, "
        f"{alpha_result['output_bytes'] / 1024 / 1024:.2f} MB, {alpha_result['status']}"
    )
    check(
        Path(alpha_result["output_path"]).suffix.lower() == ".webp",
        "Ảnh RGBA có alpha thật được lưu thành WebP",
    )
    check(
        alpha_result["status"] != "target_not_met"
        and alpha_result["output_bytes"] <= alpha_target,
        "WebP không vượt mục tiêu khi trạng thái không phải target_not_met",
    )
    with Image.open(alpha_result["output_path"]) as alpha_out:
        check("A" in alpha_out.getbands(), "WebP đầu ra còn kênh alpha")

    # 4b. Mục tiêu quá nhỏ: phải báo target_not_met thay vì hứa hẹn sai
    hard_result = compress.compress_image(alpha_png, RUN_DIR, int(0.02 * 1024 * 1024))
    check(
        hard_result["status"] == "target_not_met",
        "Mục tiêu bất khả thi trả trạng thái target_not_met",
    )
    check(
        Path(hard_result["output_path"]).exists(),
        "Vẫn tạo được bản nhỏ nhất khi không đạt mục tiêu",
    )

    # 5. File đã nhỏ hơn mục tiêu được giữ nguyên
    small_result = compress.compress_image(small_jpg, RUN_DIR, 5 * 1024 * 1024)
    check(small_result["status"] == "already_small", "File nhỏ hơn mục tiêu có trạng thái already_small")
    check(
        Path(small_result["output_path"]).read_bytes() == small_jpg.read_bytes(),
        "File already_small là bản sao byte-for-byte",
    )

    # 6. PDF: số trang, chữ, dung lượng
    pdf_result = compress.compress_pdf(pdf_path, RUN_DIR, TARGET_SMALL)
    print(
        f"  invoice.pdf -> {Path(pdf_result['output_path']).name}, "
        f"{pdf_result['output_bytes'] / 1024 / 1024:.2f} MB, {pdf_result['status']}, "
        f"{pdf_result['dpi']} DPI/q{pdf_result['quality']}, SSIM {pdf_result['ssim']}"
    )
    check(pdf_result["page_count"] == 3, "PDF đầu ra giữ đủ 3 trang")
    check(pdf_result["text_identical"] is True, "Chữ trong PDF đầu ra giống bản gốc")
    check(
        pdf_result["status"] == "target_not_met"
        or pdf_result["output_bytes"] <= TARGET_SMALL,
        "PDF không vượt mục tiêu khi trạng thái không phải target_not_met",
    )
    with pymupdf.open(pdf_result["output_path"]) as out_doc:
        check(out_doc.page_count == 3, "Mở lại PDF đầu ra thấy đúng 3 trang")

    # 7. PDF có mật khẩu báo lỗi rõ ràng
    try:
        compress.compress_pdf(encrypted_pdf, RUN_DIR, TARGET_SMALL)
        check(False, "PDF có mật khẩu phải báo lỗi")
    except ValueError as exc:
        check("mật khẩu" in str(exc).lower(), "PDF có mật khẩu báo lỗi tiếng Việt rõ ràng")

    # 8. Preview PNG
    previews = compress.make_previews(noise_png, first_output, "image")
    check(
        all(k in previews for k in ("orig_full", "out_full", "orig_crop", "out_crop")),
        "Preview ảnh trả đủ 4 ảnh PNG",
    )
    check(previews["orig_full"][:8] == b"\x89PNG\r\n\x1a\n", "Preview ảnh là dữ liệu PNG")
    pdf_previews = compress.make_previews(pdf_path, pdf_result["output_path"], "pdf", page=1)
    check(
        all(k in pdf_previews for k in ("orig_page", "out_page")),
        "Preview PDF trả đủ cặp trang",
    )
    check(pdf_previews["page"] == 1, "Preview PDF chọn đúng số trang")

    # 9. Bản gốc không thay đổi
    for path in sources:
        check(sha256(path) == before[path], f"Bản gốc không đổi: {path.name}")

    print()
    print(f"TẤT CẢ {CHECKS} KIỂM TRA ĐỀU ĐẠT")
    print(f"Thư mục kết quả kiểm tra: {RUN_DIR}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
