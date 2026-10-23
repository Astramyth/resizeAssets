"""Bộ nén ảnh và PDF cục bộ.

Phần lõi dùng Pillow cho ảnh, PyMuPDF cho PDF. Không ghi đè lên bất kỳ
file nào đã tồn tại; mọi kết quả đều được ghi thành file mới.
"""

from __future__ import annotations

import argparse
import io
import math
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageOps
from PIL import JpegImagePlugin
import pillow_heif

pillow_heif.register_heif_opener()

SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".heic", ".heif"}
SUPPORTED_PDF_EXTS = {".pdf"}
SUPPORTED_EXTS = SUPPORTED_IMAGE_EXTS | SUPPORTED_PDF_EXTS

IMAGE_QUALITY_MIN = 75
IMAGE_QUALITY_MAX = 95
IMAGE_LONG_EDGE_FLOOR = 2000
IMAGE_DOWNSCALE_FACTOR = 0.85

PDF_LADDER = [
    (300, 90),
    (250, 85),
    (200, 85),
    (200, 80),
    (150, 80),
    (150, 75),
]

EDITOR_DATA_NOTE = (
    "Đã bỏ dữ liệu chỉnh sửa ẩn của Photoshop/Illustrator (không hiển thị khi xem hoặc in). "
    "Bản nén không mở lại được dạng layer trong Photoshop/Illustrator; bản gốc vẫn giữ nguyên."
)


# ---------------------------------------------------------------------------
# Tên file / an toàn dữ liệu
# ---------------------------------------------------------------------------

def unique_output_path(out_dir: str | Path, stem: str, ext: str) -> Path:
    """Trả về đường dẫn chưa tồn tại: <stem>_compressed.<ext>, _2, _3, ..."""
    out_dir = Path(out_dir)
    ext = ext if ext.startswith(".") else "." + ext
    candidate = out_dir / f"{stem}_compressed{ext}"
    n = 2
    while candidate.exists():
        candidate = out_dir / f"{stem}_compressed_{n}{ext}"
        n += 1
    return candidate


def _write_new_file(path: Path, data: bytes) -> Path:
    """Ghi file mới, không bao giờ ghi đè (kể cả khi có race hiếm gặp)."""
    base = path.stem
    ext = path.suffix
    if base.endswith("_compressed"):
        prefix = base
    else:
        head, _, tail = base.rpartition("_")
        prefix = head if head.endswith("_compressed") and tail.isdigit() else base

    candidate = path
    n = 2
    while True:
        try:
            with open(candidate, "xb") as fh:
                fh.write(data)
            return candidate
        except FileExistsError:
            candidate = path.with_name(f"{prefix}_{n}{ext}")
            n += 1


def _copy_unchanged(src: Path, out_dir: Path) -> Path:
    out = unique_output_path(out_dir, src.stem, src.suffix.lower())
    shutil.copyfile(src, out)
    return out


def _display_dimensions(src_path: Path) -> tuple[int, int]:
    with Image.open(src_path) as im:
        fixed = ImageOps.exif_transpose(im)
        return fixed.size


# ---------------------------------------------------------------------------
# SSIM
# ---------------------------------------------------------------------------

def ssim(a: np.ndarray, b: np.ndarray) -> float:
    """SSIM chuẩn trên ảnh xám, cửa sổ đều 8x8, tính bằng integral image."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.ndim != 2 or b.ndim != 2:
        raise ValueError("ssim chỉ nhận ảnh xám 2 chiều")
    if a.shape != b.shape:
        raise ValueError("ssim cần hai ảnh cùng kích thước")
    h, w = a.shape
    if h == 0 or w == 0:
        return 0.0

    win_h = min(8, h)
    win_w = min(8, w)
    n = float(win_h * win_w)

    def box_sum(x: np.ndarray) -> np.ndarray:
        ii = np.zeros((h + 1, w + 1), dtype=np.float64)
        ii[1:, 1:] = np.cumsum(np.cumsum(x, axis=0), axis=1)
        return (
            ii[win_h:, win_w:]
            - ii[:-win_h, win_w:]
            - ii[win_h:, :-win_w]
            + ii[:-win_h, :-win_w]
        )

    mu_a = box_sum(a) / n
    mu_b = box_sum(b) / n
    var_a = box_sum(a * a) / n - mu_a * mu_a
    var_b = box_sum(b * b) / n - mu_b * mu_b
    cov_ab = box_sum(a * b) / n - mu_a * mu_b

    var_a = np.maximum(var_a, 0.0)
    var_b = np.maximum(var_b, 0.0)

    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2
    numerator = (2.0 * mu_a * mu_b + c1) * (2.0 * cov_ab + c2)
    denominator = (mu_a * mu_a + mu_b * mu_b + c1) * (var_a + var_b + c2)
    return float(np.mean(numerator / denominator))


# ---------------------------------------------------------------------------
# Xử lý màu / alpha
# ---------------------------------------------------------------------------

def _has_real_alpha(im: Image.Image) -> bool:
    if im.mode in ("RGBA", "LA"):
        alpha = im.getchannel("A")
        return alpha.getextrema()[0] < 255
    if im.mode == "P" and "transparency" in im.info:
        rgba = im.convert("RGBA")
        return rgba.getchannel("A").getextrema()[0] < 255
    return False


def _to_safe_mode(im: Image.Image, want_alpha: bool) -> Image.Image:
    """Đưa ảnh về RGB/RGBA hoặc L an toàn, xử lý CMYK và ảnh 16-bit."""
    mode = im.mode

    if want_alpha:
        if mode == "RGBA":
            return im
        if mode in ("LA", "P", "PA"):
            return im.convert("RGBA")
        if mode in ("L", "RGB"):
            return im.convert("RGBA")
        if mode == "CMYK":
            return im.convert("RGB").convert("RGBA")
        if mode.startswith("I") or mode == "F":
            return _high_depth_to_gray(im).convert("RGBA")
        return im.convert("RGBA")

    if mode == "L":
        return im
    if mode == "RGB":
        return im
    if mode == "P":
        return im.convert("RGB")
    if mode == "CMYK":
        return im.convert("RGB")
    if mode in ("LA", "RGBA"):
        return im.convert("RGB")
    if mode.startswith("I") or mode == "F":
        return _high_depth_to_gray(im)
    return im.convert("RGB")


def _high_depth_to_gray(im: Image.Image) -> Image.Image:
    arr = np.asarray(im, dtype=np.float32)
    if im.mode.startswith("I;16"):
        arr = arr / 257.0
    else:
        lo = float(np.min(arr))
        hi = float(np.max(arr))
        if hi > lo:
            arr = (arr - lo) * (255.0 / (hi - lo))
        else:
            arr = np.zeros_like(arr)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "L")


def _flatten_on_white(im: Image.Image) -> Image.Image:
    """Bản xem trước: nền trong suốt được đặt trên nền trắng."""
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
    return im.convert("RGB")


def _grayscale_from_image(im: Image.Image) -> np.ndarray:
    return np.asarray(_flatten_on_white(im).convert("L"), dtype=np.float32)


def _center_crop_box(size: tuple[int, int], max_w: int, max_h: int) -> tuple[int, int, int, int]:
    w, h = size
    cw = min(max_w, w)
    ch = min(max_h, h)
    left = max(0, (w - cw) // 2)
    top = max(0, (h - ch) // 2)
    return left, top, left + cw, top + ch


# ---------------------------------------------------------------------------
# Nén ảnh
# ---------------------------------------------------------------------------

def _encode_image(
    im: Image.Image,
    fmt: str,
    quality: int,
    subsampling: int,
    exif_bytes: bytes | None,
    icc_profile: bytes | None,
) -> bytes:
    buf = io.BytesIO()
    kwargs: dict = {"quality": int(quality)}
    if fmt == "JPEG":
        kwargs.update(optimize=True, progressive=True, subsampling=int(subsampling))
    else:
        kwargs.update(method=4)
    if exif_bytes:
        kwargs["exif"] = exif_bytes
    if icc_profile:
        kwargs["icc_profile"] = icc_profile
    try:
        im.save(buf, format=fmt, **kwargs)
    except OSError:
        if fmt != "JPEG":
            raise
        # Với ảnh rất chi tiết/nhiễu, buffer của encoder JPEG (ImageFile.MAXBLOCK)
        # không đủ cho optimize/progressive. Thử lại một lần ở chế độ tuần tự,
        # giữ nguyên quality/subsampling/exif/icc. Không nâng MAXBLOCK toàn cục
        # vì sẽ tốn rất nhiều RAM với ảnh lớn.
        buf = io.BytesIO()
        kwargs.update(optimize=False, progressive=False)
        im.save(buf, format=fmt, **kwargs)
    return buf.getvalue()


def _search_quality(
    im: Image.Image,
    fmt: str,
    target_bytes: int,
    subsampling: int,
    exif_bytes: bytes | None,
    icc_profile: bytes | None,
) -> tuple[int, bytes] | None:
    """Tìm quality cao nhất trong [75, 95] mà dung lượng <= target."""
    cache: dict[int, bytes] = {}

    def encode(q: int) -> bytes:
        if q not in cache:
            cache[q] = _encode_image(im, fmt, q, subsampling, exif_bytes, icc_profile)
        return cache[q]

    at_min = encode(IMAGE_QUALITY_MIN)
    if len(at_min) > target_bytes:
        return None

    best_q, best_data = IMAGE_QUALITY_MIN, at_min
    lo, hi = IMAGE_QUALITY_MIN + 1, IMAGE_QUALITY_MAX
    while lo <= hi:
        mid = (lo + hi) // 2
        data = encode(mid)
        if len(data) <= target_bytes:
            best_q, best_data = mid, data
            lo = mid + 1
        else:
            hi = mid - 1
    return best_q, best_data


def _dims_for_long_edge(w: int, h: int, long_edge: int) -> tuple[int, int]:
    if w >= h:
        return max(1, int(long_edge)), max(1, int(round(h * long_edge / w)))
    return max(1, int(round(w * long_edge / h))), max(1, int(long_edge))


def _image_ssim(original: Image.Image, out_path: Path) -> tuple[float, bool]:
    """SSIM trên vùng giữa tối đa 2048x2048 ở độ phân giải đầu ra."""
    with Image.open(out_path) as out_im0:
        out_im = ImageOps.exif_transpose(out_im0)
        out_w, out_h = out_im.size
        downscaled = out_im.size != original.size
        if downscaled:
            base = original.resize(out_im.size, Image.Resampling.LANCZOS)
        else:
            base = original
        box = _center_crop_box(out_im.size, 2048, 2048)
        a = _grayscale_from_image(base.crop(box))
        b = _grayscale_from_image(out_im.crop(box))
    return ssim(a, b), downscaled


def compress_image(
    src_path: str | Path,
    out_dir: str | Path,
    target_bytes: int,
) -> dict:
    src = Path(src_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    original_bytes = src.stat().st_size
    if target_bytes <= 0:
        raise ValueError("Dung lượng mục tiêu phải lớn hơn 0.")

    if original_bytes <= target_bytes:
        try:
            w, h = _display_dimensions(src)
        except Exception as exc:
            print(f"  ! Không mở được ảnh {src}: {exc}", file=sys.stderr)
            raise ValueError(
                "Không mở được ảnh. File có thể bị hỏng hoặc không đúng định dạng."
            ) from exc
        out_path = _copy_unchanged(src, out_dir)
        return {
            "kind": "image",
            "status": "already_small",
            "output_path": str(out_path),
            "original_bytes": original_bytes,
            "output_bytes": out_path.stat().st_size,
            "original_width": w,
            "original_height": h,
            "output_width": w,
            "output_height": h,
            "format": (
                "JPEG"
                if src.suffix.lower() in (".jpg", ".jpeg")
                else src.suffix.lstrip(".").upper()
            ),
            "quality": None,
            "ssim": 1.0,
            "downscaled": False,
            "target_bytes": target_bytes,
        }

    try:
        with Image.open(src) as im0:
            src_format = (im0.format or "").upper()
            source_mode = im0.mode
            icc = im0.info.get("icc_profile")
            subsampling = 0
            if src_format in ("JPEG", "MPO"):
                try:
                    sampling = JpegImagePlugin.get_sampling(im0)
                    if isinstance(sampling, int) and sampling >= 0:
                        subsampling = sampling
                except Exception:
                    subsampling = 0

            im = ImageOps.exif_transpose(im0)
            orig_w, orig_h = im.size

            # ICC chỉ giữ khi không gian màu đầu ra còn tương thích.
            if source_mode in ("RGB", "RGBA", "L", "LA", "P"):
                icc_profile = icc
            else:
                icc_profile = None

            exif_bytes = None
            try:
                exif = im.getexif()
                exif[0x0112] = 1  # Orientation = 1
                exif_bytes = exif.tobytes() if len(exif) else None
            except Exception:
                exif_bytes = None

            has_alpha = _has_real_alpha(im)
            if has_alpha:
                work = _to_safe_mode(im, True)
                fmt, ext = "WEBP", ".webp"
            else:
                work = _to_safe_mode(im, False)
                fmt, ext = "JPEG", ".jpg"
    except Exception as exc:
        print(f"  ! Không mở được ảnh {src}: {exc}", file=sys.stderr)
        raise ValueError(
            "Không mở được ảnh. File có thể bị hỏng hoặc không đúng định dạng."
        ) from exc

    long_edge = max(orig_w, orig_h)
    scale = 1.0
    chosen: tuple[int, bytes, Image.Image] | None = None
    status = "ok"

    while True:
        if scale == 1.0:
            current = work
        else:
            target_long = max(IMAGE_LONG_EDGE_FLOOR, int(round(long_edge * scale)))
            current = work.resize(
                _dims_for_long_edge(orig_w, orig_h, target_long),
                Image.Resampling.LANCZOS,
            )

        found = _search_quality(
            current, fmt, target_bytes, subsampling, exif_bytes, icc_profile
        )
        if found is not None:
            q, data = found
            chosen = (q, data, current)
            break

        cur_long = max(current.size)
        if cur_long <= IMAGE_LONG_EDGE_FLOOR:
            # Đã chạm sàn: lấy bản quality 75 của độ phân giải sàn.
            q = IMAGE_QUALITY_MIN
            data = _encode_image(
                current, fmt, q, subsampling, exif_bytes, icc_profile
            )
            chosen = (q, data, current)
            status = "target_not_met"
            break

        next_scale = scale * IMAGE_DOWNSCALE_FACTOR
        next_long = max(IMAGE_LONG_EDGE_FLOOR, int(round(long_edge * next_scale)))
        if next_long >= cur_long:
            next_long = IMAGE_LONG_EDGE_FLOOR
        scale = next_long / long_edge
        if scale >= 1.0:
            scale = IMAGE_DOWNSCALE_FACTOR

    quality, data, final_im = chosen
    out_path = unique_output_path(out_dir, src.stem, ext)
    out_path = _write_new_file(out_path, data)

    quality_ssim, downscaled = _image_ssim(work, out_path)
    out_w, out_h = final_im.size

    return {
        "kind": "image",
        "status": status,
        "output_path": str(out_path),
        "original_bytes": original_bytes,
        "output_bytes": len(data),
        "original_width": orig_w,
        "original_height": orig_h,
        "output_width": out_w,
        "output_height": out_h,
        "format": fmt,
        "quality": int(quality),
        "ssim": round(quality_ssim, 4),
        "downscaled": bool(downscaled),
        "target_bytes": target_bytes,
        "subsampling": int(subsampling),
    }


# ---------------------------------------------------------------------------
# Nén PDF
# ---------------------------------------------------------------------------

def _pdf_text(doc) -> str:
    return "".join(page.get_text() for page in doc)


def _pdf_ssim(original_path: Path, out_bytes: bytes, page_count: int) -> float:
    idxs = [0]
    if page_count > 1:
        middle = int(math.ceil(page_count / 2.0)) - 1
        idxs.append(middle)
        idxs.append(page_count - 1)
    seen: list[int] = []
    for i in idxs:
        if 0 <= i < page_count and i not in seen:
            seen.append(i)

    orig_doc = pymupdf.open(original_path)
    out_doc = pymupdf.open(stream=out_bytes, filetype="pdf")
    values: list[float] = []
    try:
        for i in seen:
            a = _render_gray(orig_doc[i], 100)
            b = _render_gray(out_doc[i], 100)
            if a.shape != b.shape:
                b_img = Image.fromarray(b.astype(np.uint8)).resize(
                    (a.shape[1], a.shape[0]), Image.Resampling.LANCZOS
                )
                b = np.asarray(b_img, dtype=np.float32)
            values.append(ssim(a, b))
    finally:
        orig_doc.close()
        out_doc.close()
    return float(np.mean(values)) if values else 0.0


def _render_gray(page, dpi: int) -> np.ndarray:
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)
    return arr[:, : pix.width].astype(np.float32)


def _open_pdf_checked(src: Path):
    try:
        doc = pymupdf.open(src)
    except Exception as exc:
        print(f"  ! Không mở được PDF {src}: {exc}", file=sys.stderr)
        raise ValueError(
            "Không mở được PDF. File có thể bị hỏng hoặc không đúng định dạng."
        ) from exc
    if doc.needs_pass:
        doc.close()
        raise ValueError(
            "PDF này được bảo vệ bằng mật khẩu. Hãy mở khóa PDF trước rồi thử lại."
        )
    return doc


def _strip_editor_data(doc) -> bool:
    """Bỏ dữ liệu chỉnh sửa ẩn (Photoshop/Illustrator) không dùng để hiển thị."""
    catalog = doc.pdf_catalog()
    page_xrefs = [page.xref for page in doc]
    removed = False
    for xref in page_xrefs + [catalog]:
        if doc.xref_get_key(xref, "PieceInfo")[0] != "null":
            doc.xref_set_key(xref, "PieceInfo", "null")
            removed = True
        if xref != catalog and doc.xref_get_key(xref, "Thumb")[0] != "null":
            doc.xref_set_key(xref, "Thumb", "null")
            removed = True
    return removed


def compress_pdf(
    src_path: str | Path,
    out_dir: str | Path,
    target_bytes: int,
) -> dict:
    src = Path(src_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    original_bytes = src.stat().st_size
    if target_bytes <= 0:
        raise ValueError("Dung lượng mục tiêu phải lớn hơn 0.")

    # Kiểm tra PDF (kể cả mật khẩu) trước khi ghi bất cứ thứ gì.
    doc = _open_pdf_checked(src)
    try:
        page_count = doc.page_count
    finally:
        doc.close()

    if original_bytes <= target_bytes:
        out_path = _copy_unchanged(src, out_dir)
        return {
            "kind": "pdf",
            "status": "already_small",
            "output_path": str(out_path),
            "original_bytes": original_bytes,
            "output_bytes": out_path.stat().st_size,
            "original_width": None,
            "original_height": None,
            "output_width": None,
            "output_height": None,
            "format": "PDF",
            "quality": None,
            "dpi": None,
            "page_count": page_count,
            "text_identical": True,
            "editor_data_removed": False,
            "images_recompressed": False,
            "ssim": 1.0,
            "downscaled": False,
            "target_bytes": target_bytes,
        }

    doc = _open_pdf_checked(src)
    try:
        original_text = _pdf_text(doc)
    finally:
        doc.close()

    best: tuple[bytes, int | None, int | None, bool, bool] | None = None
    last_error: Exception | None = None
    step0_met_target = False

    # Bước 0: chỉ bỏ dữ liệu chỉnh sửa ẩn, không đụng tới ảnh.
    try:
        work = _open_pdf_checked(src)
        try:
            editor_data_removed = _strip_editor_data(work)
            try:
                work.subset_fonts()
            except Exception as exc:  # subset_fonts không bắt buộc phải thành công
                print(f"  ! subset_fonts bỏ qua: {exc}", file=sys.stderr)
            buf = io.BytesIO()
            work.save(buf, garbage=4, deflate=True, use_objstms=1)
            data = buf.getvalue()
        finally:
            work.close()

        check = pymupdf.open(stream=data, filetype="pdf")
        try:
            same_pages = check.page_count == page_count
        finally:
            check.close()
        if not same_pages:
            print("  ! Bỏ qua bước 0: số trang thay đổi", file=sys.stderr)
        else:
            best = (data, None, None, False, editor_data_removed)
            step0_met_target = len(data) <= target_bytes
    except Exception as exc:
        last_error = exc
        print(f"  ! Lỗi ở bước 0: {exc}", file=sys.stderr)

    if not step0_met_target:
        for dpi, quality in PDF_LADDER:
            try:
                work = _open_pdf_checked(src)
                try:
                    editor_data_removed = _strip_editor_data(work)
                    work.rewrite_images(
                        dpi_threshold=dpi + 10,
                        dpi_target=dpi,
                        quality=quality,
                    )
                    try:
                        work.subset_fonts()
                    except Exception as exc:  # subset_fonts không bắt buộc phải thành công
                        print(f"  ! subset_fonts bỏ qua: {exc}", file=sys.stderr)
                    buf = io.BytesIO()
                    work.save(buf, garbage=4, deflate=True, use_objstms=1)
                    data = buf.getvalue()
                finally:
                    work.close()

                check = pymupdf.open(stream=data, filetype="pdf")
                try:
                    same_pages = check.page_count == page_count
                finally:
                    check.close()
                if not same_pages:
                    print(
                        f"  ! Bỏ qua bậc {dpi} DPI/q{quality}: số trang thay đổi",
                        file=sys.stderr,
                    )
                    continue

                if len(data) <= target_bytes:
                    best = (data, dpi, quality, True, editor_data_removed)
                    break
                if best is None or len(data) < len(best[0]):
                    best = (data, dpi, quality, True, editor_data_removed)
            except Exception as exc:
                last_error = exc
                print(
                    f"  ! Lỗi ở bậc {dpi} DPI/q{quality}: {exc}",
                    file=sys.stderr,
                )

    if best is None:
        raise RuntimeError(
            f"Không thể nén PDF: {last_error}" if last_error else "Không thể nén PDF."
        )

    data, dpi, quality, images_recompressed, editor_data_removed = best
    status = "ok" if len(data) <= target_bytes else "target_not_met"

    # Nếu bản "nén" lại lớn hơn bản gốc thì giữ nguyên bản gốc (an toàn hơn).
    if len(data) >= original_bytes:
        data = src.read_bytes()
        dpi = None
        quality = None
        images_recompressed = False
        editor_data_removed = False
        status = "target_not_met"

    out_doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        if out_doc.page_count != page_count:
            raise RuntimeError("Số trang PDF sau khi nén không khớp với bản gốc.")
        output_text = _pdf_text(out_doc)
    finally:
        out_doc.close()

    text_identical = output_text == original_text
    quality_ssim = _pdf_ssim(src, data, page_count)

    ext = ".pdf"
    out_path = unique_output_path(out_dir, src.stem, ext)
    out_path = _write_new_file(out_path, data)

    return {
        "kind": "pdf",
        "status": status,
        "output_path": str(out_path),
        "original_bytes": original_bytes,
        "output_bytes": len(data),
        "original_width": None,
        "original_height": None,
        "output_width": None,
        "output_height": None,
        "format": "PDF",
        "quality": quality,
        "dpi": dpi,
        "page_count": page_count,
        "text_identical": bool(text_identical),
        "editor_data_removed": bool(editor_data_removed),
        "images_recompressed": bool(images_recompressed),
        "ssim": round(quality_ssim, 4),
        "downscaled": False,
        "target_bytes": target_bytes,
    }


# ---------------------------------------------------------------------------
# Preview cho UI
# ---------------------------------------------------------------------------

def _fit_png(im: Image.Image, long_edge: int) -> bytes:
    preview = _flatten_on_white(im)
    preview.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    preview.save(buf, format="PNG")
    return buf.getvalue()


def make_previews(
    src_path: str | Path,
    out_path: str | Path,
    kind: str,
    page: int = 0,
) -> dict:
    """Trả về dict PNG bytes cho ảnh so sánh.

    Ảnh: orig_full, out_full, orig_crop, out_crop.
    PDF: orig_page, out_page (kèm page, page_count).
    """
    src = Path(src_path)
    out = Path(out_path)

    if kind == "image":
        with Image.open(src) as src0, Image.open(out) as out0:
            orig = ImageOps.exif_transpose(src0)
            out_im = ImageOps.exif_transpose(out0)
            out_size = out_im.size

            if orig.size != out_size:
                base = orig.resize(out_size, Image.Resampling.LANCZOS)
            else:
                base = orig

            box = _center_crop_box(out_size, 800, 800)
            orig_crop = _flatten_on_white(base.crop(box))
            out_crop = _flatten_on_white(out_im.crop(box))

            orig_full = _fit_png(orig, 1200)
            out_full = _fit_png(out_im, 1200)

        def crop_png(im: Image.Image) -> bytes:
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            return buf.getvalue()

        return {
            "kind": "image",
            "orig_full": orig_full,
            "out_full": out_full,
            "orig_crop": crop_png(orig_crop),
            "out_crop": crop_png(out_crop),
        }

    if kind == "pdf":
        orig_doc = pymupdf.open(src)
        out_doc = pymupdf.open(out)
        try:
            count = min(orig_doc.page_count, out_doc.page_count)
            if count <= 0:
                raise ValueError("PDF không có trang nào.")
            page = max(0, min(int(page), count - 1))
            orig_png = orig_doc[page].get_pixmap(dpi=150, alpha=False).tobytes("png")
            out_png = out_doc[page].get_pixmap(dpi=150, alpha=False).tobytes("png")
        finally:
            orig_doc.close()
            out_doc.close()
        return {
            "kind": "pdf",
            "orig_page": orig_png,
            "out_page": out_png,
            "page": page,
            "page_count": count,
        }

    raise ValueError("Loại file không hỗ trợ để tạo ảnh so sánh.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _fmt_mb(n: int | None) -> str:
    if n is None:
        return "-"
    return f"{n / (1024 * 1024):.2f}"


def _short(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return "..." + text[-(width - 3):]


def _print_table(results: list[dict], out_paths: list[Path]) -> None:
    headers = [
        "File",
        "Before MB",
        "After MB",
        "Ratio",
        "Resolution/DPI",
        "Quality",
        "SSIM",
        "Status",
    ]
    rows: list[list[str]] = []
    for res, out_path in zip(results, out_paths):
        if res["kind"] == "image":
            resolution = (
                f'{res["original_width"]}x{res["original_height"]} -> '
                f'{res["output_width"]}x{res["output_height"]}'
            )
        else:
            dpi = res.get("dpi")
            resolution = (
                f'{res.get("page_count", 0)} pages, {dpi} dpi'
                if dpi
                else f'{res.get("page_count", 0)} pages, original images'
            )
        q = res.get("quality")
        if res["kind"] == "image":
            quality_text = f'{res.get("format")} q{q}' if q else "-"
        else:
            quality_text = f'q{q}' if q else "-"
        ratio = (
            f'{res["output_bytes"] / res["original_bytes"] * 100:.1f}%'
            if res["original_bytes"]
            else "-"
        )
        rows.append(
            [
                _short(out_path.name, 42),
                _fmt_mb(res["original_bytes"]),
                _fmt_mb(res["output_bytes"]),
                ratio,
                resolution,
                quality_text,
                f'{res["ssim"]:.4f}',
                res["status"],
            ]
        )

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(line)
    print("-" * len(line))
    for row in rows:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="Nén ảnh/PDF về gần dung lượng mục tiêu, không ghi đè bản gốc."
    )
    parser.add_argument("files", nargs="+", help="Các file ảnh hoặc PDF cần nén")
    parser.add_argument(
        "--target",
        type=float,
        default=5.0,
        metavar="MB",
        help="Dung lượng mục tiêu tính bằng MB (mặc định 5)",
    )
    parser.add_argument(
        "--out",
        default=None,
        metavar="DIR",
        help="Thư mục đầu ra (mặc định: cùng thư mục với file gốc)",
    )
    args = parser.parse_args(argv)

    if args.target <= 0:
        parser.error("--target phải lớn hơn 0")
    target_bytes = int(args.target * 1024 * 1024)

    results: list[dict] = []
    out_paths: list[Path] = []
    for file_name in args.files:
        src = Path(file_name)
        if not src.is_file():
            print(f"LỖI: không tìm thấy file {src}", file=sys.stderr)
            return 2
        ext = src.suffix.lower()
        if ext not in SUPPORTED_EXTS:
            print(f"LỖI: định dạng không hỗ trợ: {ext or '(không có đuôi)'}", file=sys.stderr)
            return 2
        out_dir = Path(args.out) if args.out else src.parent
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"Đang xử lý: {src.name} ...", file=sys.stderr)
        started = time.time()
        if ext in SUPPORTED_PDF_EXTS:
            res = compress_pdf(src, out_dir, target_bytes)
        else:
            res = compress_image(src, out_dir, target_bytes)
        elapsed = time.time() - started

        results.append(res)
        out_paths.append(Path(res["output_path"]))
        print(
            f"  -> {res['status']} trong {elapsed:.1f}s: {res['output_path']}",
            file=sys.stderr,
        )

    print()
    _print_table(results, out_paths)

    warnings = []
    notes = []
    for res, out_path in zip(results, out_paths):
        if res["status"] == "target_not_met":
            warnings.append(
                f"{out_path.name}: không đạt mục tiêu; đây là bản nhỏ nhất ở mức "
                "chất lượng tối thiểu."
            )
        if res["kind"] == "pdf" and not res.get("text_identical", True):
            warnings.append(
                f"{out_path.name}: không xác nhận được toàn bộ chữ giữ nguyên; "
                "hãy kiểm tra lại bản nén."
            )
        if res.get("editor_data_removed"):
            notes.append(f"{out_path.name}: {EDITOR_DATA_NOTE}")
    if warnings:
        print()
        for warning in warnings:
            print(f"CẢNH BÁO: {warning}")
    if notes:
        print()
        for note in notes:
            print(f"LƯU Ý: {note}")

    print()
    print("SSIM gần 1.0 = gần giống bản gốc; chỉ là chỉ số tham khảo, hãy tự xem ảnh so sánh.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
