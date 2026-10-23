# Nén ảnh & PDF trên máy tính (Windows + Python)

Ứng dụng cục bộ giúp kéo thả ảnh hoặc PDF 20–30 MB và nhận về bản nhẹ hơn (mặc định khoảng 5 MB) mà vẫn giữ độ nét, màu sắc và nội dung ở mức chấp nhận được.

- Giao diện web chạy tại `http://127.0.0.1:8765`, chỉ mở trên máy bạn.
- Không upload file lên internet.
- **Không bao giờ ghi đè file gốc.** Mọi kết quả là một file mới.
- Khi không thể đạt mục tiêu mà vẫn giữ chất lượng, ứng dụng nói rõ bằng trạng thái `target_not_met` thay vì hứa hẹn sai.

## Chạy nhanh

1. Nhấp đúp `run.bat`.
   - Lần đầu, file này tạo `.venv`, cài thư viện trong `requirements.txt`, rồi mở ứng dụng.
   - Các lần sau, nó dùng luôn `.venv` đã có.
2. Trình duyệt tự mở trang `http://127.0.0.1:8765/`.
3. Kéo thả file, nhập dung lượng mục tiêu (MB), chờ nén, rồi bấm **Tải về** hoặc **So sánh**.
4. Nhấn `Ctrl+C` trong cửa sổ dòng lệnh để dừng ứng dụng.

Nếu muốn chạy bằng tay:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

Yêu cầu: Windows, Python 3.12 đã có trên `PATH`.

## Định dạng hỗ trợ

| Loại | Định dạng đầu vào | Đầu ra |
|---|---|---|
| Ảnh không có alpha | `.jpg`, `.jpeg`, `.png`, `.webp`, `.tif`, `.tiff`, `.bmp`, `.heic`, `.heif` | `.jpg` |
| Ảnh có alpha thật | `.png`, `.webp`, `.tif`, `.heic`, `.heif`... | `.webp` |
| Tài liệu | `.pdf` | `.pdf` |

- Ảnh có alpha nhìn thấy được (alpha không phải toàn 255) mới chuyển sang WebP. Alpha toàn 255 được coi là không trong suốt và xuất JPEG.
- Ảnh nhiều khung (TIFF nhiều trang, WebP động) chỉ xử lý khung đầu tiên.
- PDF có mật khẩu bị từ chối với thông báo tiếng Việt; hãy mở khóa PDF trước.

## Dùng giao diện web

- Ô **Dung lượng mục tiêu (MB)** mặc định là `5`.
- Có thể chọn nhiều file; các file được xử lý lần lượt.
- Mỗi file có một thẻ hiển thị:
  - dung lượng trước → sau và % giảm;
  - độ phân giải trước/sau (ảnh) hoặc số trang + DPI ảnh trong PDF;
  - định dạng và chất lượng encoder đã dùng;
  - SSIM kèm giải thích;
  - trạng thái `already_small` / `target_not_met` / cảnh báo chữ PDF.
- **So sánh** mở ảnh cạnh nhau:
  - Ảnh: toàn bộ ảnh (vừa 1200 px) và vùng cắt 100% ở giữa (800×800).
  - PDF: cặp trang gốc/bản nén ở 150 DPI, có nút chuyển trang.
- **Tải về** tải đúng file kết quả, tên dạng `<tên>_compressed.<đuôi>`.

Giới hạn upload: 500 MB mỗi request.

## Dùng dòng lệnh

```powershell
.venv\Scripts\python compress.py FILE [FILE ...] [--target MB] [--out DIR]
```

- `--target` mặc định `5` MB.
- `--out` mặc định là thư mục chứa file gốc.
- Ví dụ:

```powershell
.venv\Scripts\python compress.py "E:\project-Annhome\Sample-jpg-image-30mb-16.jpg" --target 5 --out _testdata
```

Kết quả CLI in bảng: file, trước MB, sau MB, tỉ lệ, độ phân giải/DPI, chất lượng, SSIM, trạng thái.

## Kết quả kiểm thử

Môi trường đã kiểm tra: Python 3.12.10, Pillow 13.0.0, NumPy 2.5.4, PyMuPDF 2.0, Flask 3.1.3, pillow-heif 1.8.1.

### Tự kiểm tra

Lệnh:

```powershell
.venv\Scripts\python test_compress.py
```

Kết quả: **28/28 kiểm tra đạt**.

| Hạng mục | Kết quả thực tế |
|---|---|
| PNG nhiễu 3000×2000 (12.78 MB) → mục tiêu 0.5 MB | 0.50 MB, `ok`, 2167×1445, SSIM 0.8611 |
| Chạy lại cùng thư mục | Tạo `_compressed_2`, không ghi đè file cũ |
| PNG RGBA 1800×1200 (1.61 MB) → mục tiêu 1 MB | WebP 0.87 MB, `ok`, còn kênh alpha |
| Cùng ảnh RGBA → mục tiêu 0.02 MB | `target_not_met`, vẫn tạo bản nhỏ nhất |
| File 3.6 KB → mục tiêu 5 MB | `already_small`, bản sao byte-for-byte |
| PDF 3 trang có ảnh lớn + chữ (1.21 MB) → mục tiêu 0.5 MB | 0.10 MB, 150 DPI/q80, đủ 3 trang, `text_identical: true`, SSIM 0.9907 |
| PDF có mật khẩu | Báo `ValueError` tiếng Việt, không tạo file rác |
| SHA-256 của 4 file gốc trước/sau | Không đổi |
| Preview ảnh/PDF | Trả đủ PNG, chọn đúng trang |

<details>
<summary>Xem toàn bộ output kiểm tra</summary>

```text
Đang tạo dữ liệu kiểm tra...
PASS: SSIM ảnh giống hệt bằng 1.0
PASS: SSIM giảm khi ảnh bị nhiễu
  noise.png -> noise_3000x2000_compressed.jpg, 0.50 MB, ok, SSIM 0.8611
PASS: Ảnh nén không vượt mục tiêu khi trạng thái không phải target_not_met
PASS: Ảnh không có alpha được lưu thành JPEG
PASS: Ảnh có thông tin độ phân giải/chất lượng đầu ra
PASS: File kết quả lần một vẫn còn sau lần chạy thứ hai
PASS: Lần chạy thứ hai tạo file mới, không ghi đè
PASS: Tên file lần hai có hậu tố _2
  alpha.png -> alpha_1800x1200_compressed.webp, 0.87 MB, ok
PASS: Ảnh RGBA có alpha thật được lưu thành WebP
PASS: WebP không vượt mục tiêu khi trạng thái không phải target_not_met
PASS: WebP đầu ra còn kênh alpha
PASS: Mục tiêu bất khả thi trả trạng thái target_not_met
PASS: Vẫn tạo được bản nhỏ nhất khi không đạt mục tiêu
PASS: File nhỏ hơn mục tiêu có trạng thái already_small
PASS: File already_small là bản sao byte-for-byte
  invoice.pdf -> invoice_3_pages_compressed.pdf, 0.10 MB, ok, 150 DPI/q80, SSIM 0.9907
PASS: PDF đầu ra giữ đủ 3 trang
PASS: Chữ trong PDF đầu ra giống bản gốc
PASS: PDF không vượt mục tiêu khi trạng thái không phải target_not_met
PASS: Mở lại PDF đầu ra thấy đúng 3 trang
PASS: PDF có mật khẩu báo lỗi tiếng Việt rõ ràng
PASS: Preview ảnh trả đủ 4 ảnh PNG
PASS: Preview ảnh là dữ liệu PNG
PASS: Preview PDF trả đủ cặp trang
PASS: Preview PDF chọn đúng số trang
PASS: Bản gốc không đổi: noise_3000x2000.png
PASS: Bản gốc không đổi: alpha_1800x1200.png
PASS: Bản gốc không đổi: small_300x200.jpg
PASS: Bản gốc không đổi: invoice_3_pages.pdf

TẤT CẢ 28 KIỂM TRA ĐỀU ĐẠT
```

</details>

### Ảnh mẫu 14 MB

Lệnh đã chạy:

```powershell
.venv\Scripts\python compress.py "E:\project-Annhome\Sample-jpg-image-30mb-16.jpg" --target 5 --out _testdata
```

Bảng CLI thực tế:

```text
File                                     Before MB  After MB  Ratio  Resolution/DPI           Quality   SSIM    Status
----------------------------------------------------------------------------------------------------------------------
Sample-jpg-image-30mb-16_compressed.jpg  13.45      4.89      36.4%  13583x5417 -> 6027x2404  JPEG q84  0.9799  ok    
```

- File gốc: 13.45 MiB (14.102.352 byte), 13583×5417, JPEG, có EXIF + ICC.
- File ra: 4.89 MiB (5.130.996 byte), 6027×2404, JPEG q84, progressive, giữ EXIF (orientation = 1) và ICC.
- Thời gian chạy trên máy kiểm tra: khoảng 12,6 giây.
- Kết quả nằm tại `_testdata\Sample-jpg-image-30mb-16_compressed.jpg`.

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
- Thang nén: `(300,90) → (250,85) → (200,85) → (200,80) → (150,80) → (150,75)` (DPI, quality JPEG).
- Mỗi bậc mở lại **file gốc**, gọi `rewrite_images(dpi_threshold=dpi+10, dpi_target=dpi, quality=quality)`, thử `subset_fonts()`, rồi lưu bằng `garbage=4, deflate=True, use_objstms=1`.
- Dừng ở bậc đầu tiên ≤ mục tiêu. Nếu không bậc nào đạt, giữ bản nhỏ nhất và trả `target_not_met`; nếu bản đó còn lớn hơn file gốc thì giữ nguyên file gốc (an toàn hơn).
- Kiểm tra lại số trang phải bằng bản gốc. So sánh toàn bộ chữ bằng `page.get_text()`; kết quả là `text_identical`.
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
- `subset_fonts()` có thể thất bại với một số font lạ; khi đó bỏ qua bước này và vẫn tiếp tục.
- `text_identical` chỉ so sánh phần chữ trích xuất được. Chữ trong ảnh scan không được kiểm tra bằng so sánh text.
- ICC được giữ cho ảnh RGB/RGBA/L/P. Ảnh CMYK hoặc 16-bit được chuyển sang RGB/L; profile ICC CMYK gốc không được gắn vào file RGB vì sai không gian màu.
- TIFF nhiều trang và WebP động chỉ lấy khung đầu tiên.
- HEIC/HEIF đọc được nhờ `pillow-heif`; đầu ra vẫn là JPEG/WebP, không ghi lại HEIC.
- PDF mã hóa/mật khẩu không được hỗ trợ.
- File rất lớn có thể dùng nhiều RAM và mất vài chục giây. Server Flask chỉ dành cho sử dụng cục bộ một người, không phải server production.
- Giao diện dùng tiếng Việt; tên file có dấu được giữ nguyên.

## Cấu trúc file

```text
compress.py        lõi nén ảnh/PDF + CLI
app.py             Flask server (127.0.0.1:8765)
static/index.html  giao diện web (HTML/CSS/JS thuần, tiếng Việt)
requirements.txt   flask, pillow, numpy, pymupdf, pillow-heif
run.bat            tạo .venv/cài thư viện lần đầu rồi chạy app
test_compress.py   tự kiểm tra bằng assert, không cần pytest
README.md          tài liệu này
_testdata/         dữ liệu và kết quả kiểm tra (có thể xóa)
```

## Ghi chú về SSIM

SSIM gần 1.0 nghĩa là bản nén gần giống bản gốc về cấu trúc sáng/tối; chỉ số này không đo được "độ đẹp" hay độ dễ đọc của chữ. Hãy dùng nút **So sánh** để xem toàn ảnh và vùng cắt 100%, đặc biệt với ảnh có chữ nhỏ hoặc PDF scan. Ứng dụng cố tình không quy đổi SSIM thành "X% chất lượng".
