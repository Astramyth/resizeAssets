# Tài liệu kỹ thuật

Phần chi tiết tách ra từ [README](../README.md): cách dùng đầy đủ, thuật toán, kết quả kiểm thử và toàn bộ giới hạn đã biết.

## Dùng giao diện web

- Ô **Dung lượng mục tiêu (MB)** mặc định là `5`.
- Kéo thả hoặc chọn **nhiều file cùng lúc**; mỗi lần thả/chọn là một lượt nén. Toàn bộ trang đều là vùng thả.
- Trong mỗi lượt, các file được xử lý lần lượt; một file lỗi không dừng các file còn lại. File không hỗ trợ bị bỏ qua và được liệt kê ngay trên đầu lượt nén.
- Mỗi file là một dòng gọn: tên, dung lượng trước → sau, % giảm và trạng thái bằng chữ kèm biểu tượng. Nút **Chi tiết** mở độ phân giải, định dạng/chất lượng, SSIM, cảnh báo, **Tải về** và **So sánh**.
- Khi lượt nén xong:
  - từ **2 file thành công** trở lên: tự động đóng gói một file ZIP và tải về; nút **Tải lại file ZIP (N file)** tải lại.
  - đúng **1 file**: tự động tải file đó; nút **Tải về** tải lại.
- Lượt nén mới luôn nằm trên cùng. Các lượt trước được thu gọn vào mục **Các lần nén trước (K)** và chỉ hiện khi bấm mở.
- **So sánh** mở ảnh cạnh nhau:
  - Ảnh: toàn bộ ảnh (vừa 1200 px) và vùng cắt 100% ở giữa (800×800).
  - PDF: cặp trang gốc/bản nén ở 150 DPI, có nút chuyển trang.

Giới hạn upload: 500 MB mỗi request. Trong ứng dụng, `1 MB = 1024 × 1024 byte`.

## Định dạng

- Ảnh có alpha nhìn thấy được (alpha không phải toàn 255) mới chuyển sang WebP. Alpha toàn 255 được coi là không trong suốt và xuất JPEG.
- Ảnh nhiều khung (TIFF nhiều trang, WebP động) chỉ xử lý khung đầu tiên.
- PDF có mật khẩu bị từ chối với thông báo tiếng Việt; hãy mở khóa PDF trước.

## Kết quả kiểm thử

Kiểm tra ngày 2026-10-31 trên Windows 11, với Python 3.12.10 và 3.14.8, Pillow 13.0.0, NumPy 2.5.4, PyMuPDF 2.0, Flask 3.1.3, pillow-heif 1.8.1.

### Tự kiểm tra

```powershell
.venv\Scripts\python test_compress.py
```

Kết quả: **53/53 kiểm tra đạt** trên cả hai phiên bản Python.

| Hạng mục | Kết quả thực tế |
|---|---|
| PNG nhiễu 3000×2000 (12.78 MB) → mục tiêu 0.5 MB | 0.50 MB, `ok`, 2167×1445, SSIM 0.8611 |
| PNG nhiễu thuần 3000×2000 (12.78 MB) → mục tiêu 0.5 MB | 2.09 MB, `target_not_met`, vẫn ghi JPEG mở lại được |
| Chạy lại cùng thư mục | Tạo `_compressed_2`, không ghi đè file cũ |
| PNG RGBA 1800×1200 (1.61 MB) → mục tiêu 1 MB | WebP 0.87 MB, `ok`, còn kênh alpha |
| Cùng ảnh RGBA → mục tiêu 0.02 MB | `target_not_met`, vẫn tạo bản nhỏ nhất |
| File 3.6 KB → mục tiêu 5 MB | `already_small`, bản sao byte-for-byte |
| PDF 3 trang có ảnh lớn + chữ (1.21 MB) → mục tiêu 0.5 MB | 0.10 MB, 150 DPI/q80, đủ 3 trang, `text_identical: true`, SSIM 0.9907 |
| PDF 1 trang có ảnh nhỏ + 3 MB `/PieceInfo` ẩn (3.01 MB) → mục tiêu 1 MB | 0.01 MB, `ok`, bỏ dữ liệu ẩn, không nén lại ảnh, render 72 DPI giống hệt |
| PDF có mật khẩu | Báo `ValueError` tiếng Việt, không tạo file rác |
| SHA-256 của 5 file gốc trước/sau | Không đổi |
| Preview ảnh/PDF | Trả đủ PNG, chọn đúng trang |
| `POST /api/zip` với 2 file cùng tên | ZIP có 2 mục tên duy nhất, nội dung trùng bản tải riêng; job id sai trả 400, id không tồn tại trả 404 |

Dòng `Suspension not allowed here` do thư viện native của PyMuPDF in ra khi tạo PDF kiểm tra; đây không phải lỗi của ứng dụng và không ảnh hưởng kết quả.

### Lượt nén mẫu qua trình duyệt

Bốn file mẫu, mục tiêu 5 MB, chạy trên Edge 156 ở 1440×900 qua ô chọn file. Xong trong 13 giây, tự tải ZIP đủ 4 file, không có lỗi console. Ở 375 px không tràn ngang.

```text
File                              Before MB  After MB  Ratio   Resolution/DPI          Quality   SSIM    Status
----------------------------------------------------------------------------------------------------------------------
nha-mau-toan-canh_compressed.jpg  30.49      4.85      15.9%   6240x4160 -> 6240x4160  JPEG q81  0.9793  ok
noi-that-go_compressed.jpg        19.89      4.67      23.5%   6144x4098 -> 6144x4098  JPEG q92  0.9927  ok
ho-so-nha-mau_compressed.pdf      37.69      2.38      6.3%    2 pages, 300 dpi        q90       0.9988  ok
anh-dang-web_compressed.jpg       0.57       0.57      100.0%  2400x1600 -> 2400x1600  -         1.0000  already_small
```

Bảng trên là output CLI của cùng bốn file. Đầu ra CLI và giao diện web cho cùng số liệu.

## Quyết định kỹ thuật

### Ảnh

- Nếu file gốc đã ≤ mục tiêu: sao chép nguyên byte sang tên mới, trạng thái `already_small`.
- Gọi `ImageOps.exif_transpose` để ảnh đúng chiều; ghi EXIF với thẻ `0x0112` (Orientation) = 1 và giữ ICC khi không gian màu còn tương thích.
- Không alpha → JPEG; alpha thật → WebP. CMYK và ảnh 16-bit được chuyển đổi an toàn sang RGB/L.
- JPEG giữ subsampling của file gốc khi đọc được bằng `JpegImagePlugin.get_sampling`; nếu không, dùng 4:4:4. Luôn bật `optimize=True`, `progressive=True`.
- Encode vào bộ nhớ, tìm quality cao nhất trong khoảng 75–95 bằng tìm kiếm nhị phân sao cho dung lượng ≤ mục tiêu.
- Nếu quality 75 vẫn quá lớn: giảm cạnh dài còn 85% bằng LANCZOS rồi lặp lại. Không giảm dưới cạnh dài 2000 px. Nếu vẫn quá lớn, ghi bản quality 75 ở mức sàn và trả `target_not_met`.
- SSIM: ảnh xám float32, cửa sổ đều 8×8, C1 = (0,01×255)², C2 = (0,03×255)², tính bằng integral image (không dùng scipy/skimage). Với ảnh, so vùng giữa tối đa 2048×2048 ở độ phân giải đầu ra; nếu đã thu nhỏ thì resize bản gốc về cùng kích thước trước khi so.

### PDF

- Nếu file gốc đã ≤ mục tiêu: sao chép nguyên byte, trạng thái `already_small`.
- PDF có mật khẩu (`needs_pass`) bị từ chối ngay bằng `ValueError` tiếng Việt.
- **Bước 0 (bỏ dữ liệu chỉnh sửa ẩn):** mở bản gốc, đặt `/PieceInfo` = null ở từng trang và ở catalog, bỏ `/Thumb` ở trang, thử `subset_fonts()`, rồi lưu bằng `garbage=4, deflate=True, use_objstms=1` nhưng **không** gọi `rewrite_images`. Nếu kết quả đã ≤ mục tiêu thì dùng luôn với `dpi=None`, `quality=None`, `images_recompressed=False`. Không đụng tới file nhúng, annotation, form hay XMP.
- Thang nén: `(300,90) → (250,85) → (200,85) → (200,80) → (150,80) → (150,75)` (DPI, quality JPEG).
- Mỗi bậc mở lại **file gốc**, bỏ dữ liệu chỉnh sửa ẩn, gọi `rewrite_images(dpi_threshold=dpi+10, dpi_target=dpi, quality=quality)`, thử `subset_fonts()`, rồi lưu bằng `garbage=4, deflate=True, use_objstms=1`.
- Dừng ở bậc đầu tiên ≤ mục tiêu. Nếu không bậc nào đạt, giữ bản nhỏ nhất và trả `target_not_met`; nếu bản đó còn lớn hơn file gốc thì giữ nguyên file gốc (an toàn hơn).
- Kiểm tra lại số trang phải bằng bản gốc. So sánh toàn bộ chữ bằng `page.get_text()`; kết quả là `text_identical`.
- Kết quả PDF có thêm `editor_data_removed` (đã bỏ dữ liệu ẩn hay chưa) và `images_recompressed` (ảnh có bị encode lại hay không).
- SSIM PDF: render trang 1, trang giữa và trang cuối (tối đa 3 trang) ở 100 DPI, ảnh xám, rồi lấy trung bình.

### An toàn dữ liệu và tên file

- Tên ra: `<stem>_compressed.<ext>`; nếu đã tồn tại thì `_2`, `_3`, ...
- Ghi file bằng chế độ `xb` (tạo mới) để không bao giờ ghi đè.
- Web: mỗi job có thư mục tạm riêng (`tempfile.mkdtemp`); thư mục được xóa khi tiến trình kết thúc (`atexit`).
- Web: `MAX_CONTENT_LENGTH = 500 MB`; job id là uuid4 hex và được kiểm tra bằng regex; tham số `which`/`page` được whitelist.
- Lỗi xử lý trả JSON tiếng Việt, không đưa stack trace ra giao diện; chi tiết được ghi ra console.

## Giới hạn đã biết

- **Không phải lúc nào cũng đạt mục tiêu.** Ảnh/PDF đã nén sẵn, ảnh có alpha nhiễu, hoặc file có cấu trúc đặc biệt có thể không xuống được mục tiêu mà vẫn giữ chất lượng. Khi đó trạng thái là `target_not_met` và ứng dụng nói rõ.
- Chất lượng `q` là thông số của encoder (JPEG/WebP), **không phải phần trăm chất lượng**. SSIM cũng chỉ là chỉ số tham khảo, không phải lời hứa về chất lượng cảm nhận.
- Ảnh JPEG/WebP bị encode lại nên có thể mất một ít chi tiết. Với ảnh đã nén mạnh từ trước, file ra có thể không nhỏ hơn nhiều.
- Ảnh có cạnh dài dưới 2000 px sẽ không bị thu nhỏ thêm; nếu mục tiêu quá nhỏ, kết quả có thể là `target_not_met`.
- PDF chỉ nén lại ảnh raster bên trong. Chữ, vector, form, annotation, liên kết được giữ nguyên; không OCR, không làm phẳng trang.
- PDF chỉ có chữ/vector, hoặc ảnh bên trong đã nhỏ/sắc nét, thường **không thể giảm 50%**. Bước bỏ dữ liệu chỉnh sửa ẩn chỉ giúp khi file thực sự chứa dữ liệu đó.
- Bỏ dữ liệu chỉnh sửa ẩn (Photoshop/Illustrator) là **không mất mát về mặt hiển thị/in**, nhưng bản nén sẽ không mở lại được dạng layer trong các ứng dụng đó; bản gốc vẫn giữ nguyên.
- `subset_fonts()` có thể thất bại với một số font lạ; khi đó bỏ qua bước này và vẫn tiếp tục.
- `text_identical` chỉ so sánh phần chữ trích xuất được. Chữ trong ảnh scan không được kiểm tra bằng so sánh text.
- ICC được giữ cho ảnh RGB/RGBA/L/P. Ảnh CMYK hoặc 16-bit được chuyển sang RGB/L; profile ICC CMYK gốc không được gắn vào file RGB vì sai không gian màu.
- TIFF nhiều trang và WebP động chỉ lấy khung đầu tiên.
- HEIC/HEIF đọc được nhờ `pillow-heif`; đầu ra vẫn là JPEG/WebP, không ghi lại HEIC.
- PDF mã hóa/mật khẩu không được hỗ trợ.
- File rất lớn có thể dùng nhiều RAM và mất vài chục giây. Server tích hợp Flask (`python app.py`) chỉ dành cho sử dụng cục bộ. Bản Docker dùng Gunicorn; xem [hướng dẫn Dokploy](DEPLOY_DOKPLOY.md) về một worker/replica, xác thực, HTTPS và giới hạn lưu file tạm.
- Giao diện dùng tiếng Việt; tên file có dấu được giữ nguyên.

## Cấu trúc file

```text
compress.py        lõi nén ảnh/PDF + CLI
app.py             Flask server (127.0.0.1:8765)
static/index.html  markup giao diện web (tiếng Việt)
static/style.css   toàn bộ CSS của giao diện
static/app.js      toàn bộ JavaScript của giao diện
static/vendor/motion.js          Motion 12.23.24 (UMD, vendor cục bộ, không dùng CDN)
static/vendor/motion.LICENSE.txt giấy phép MIT của Motion
requirements.txt   flask, pillow, numpy, pymupdf, pillow-heif
requirements-docker.lock phiên bản thư viện cố định cho Docker Linux
Dockerfile         Gunicorn, cổng 8765, một worker/thread, user không có quyền root
.dockerignore      chỉ đưa mã ứng dụng và static vào build context
run.bat            tạo .venv/cài thư viện lần đầu rồi chạy app
test_compress.py   tự kiểm tra bằng assert, không cần pytest
test_deployment.py kiểm tra HTTP trên ứng dụng đang chạy
README.md          giới thiệu ngắn
docs/              tài liệu này, banner và ảnh minh họa README
.nomi/             trailer, flow và bằng chứng kiểm tra giao diện
_testdata/         dữ liệu và kết quả kiểm tra (có thể xóa)
```

## Ghi chú về SSIM

SSIM gần 1.0 nghĩa là bản nén gần giống bản gốc về cấu trúc sáng/tối; chỉ số này không đo được "độ đẹp" hay độ dễ đọc của chữ. Hãy dùng nút **So sánh** để xem toàn ảnh và vùng cắt 100%, đặc biệt với ảnh có chữ nhỏ hoặc PDF scan. Ứng dụng cố tình không quy đổi SSIM thành "X% chất lượng".
