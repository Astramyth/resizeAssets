# Triển khai resizeAssets lên Dokploy

Hướng dẫn cho repo `https://github.com/Astramyth/resizeAssets`, nhánh `main`, và trang quản trị `http://113.166.120.18:3000/`.

Bản Docker dùng Linux + Python 3.12 + Gunicorn, phục vụ cả giao diện và API tại cổng `8765`. Không cần Node.js, database, Redis, file `.env` hoặc volume. Bản Windows vẫn chạy bằng `run.bat` như trước.

Đã kiểm tra ngày 2026-11-01: build Docker thành công; container chạy UID 1000; 53/53 kiểm tra thuật toán/API hiện có đạt trên Windows và Docker Linux; smoke test HTTP trên bản Docker cuối đạt cho JPG/PDF, preview, download, ZIP và kiểm tra mã job. Chưa deploy lên Dokploy thật hoặc kiểm chứng DNS/HTTPS/Basic Auth của server. Địa chỉ quản trị hiện yêu cầu đăng nhập.

## 1. Đưa các file đã chuẩn bị lên GitHub

Dokploy tải mã từ GitHub, không đọc thư mục trên máy bạn. Phải push các thay đổi trước khi bấm Deploy.

**Nếu đã nhận link pull request chứa cấu hình này:** mở pull request, nếu đang Draft thì bấm **Ready for review**, kiểm tra tab **Files changed**, sau đó bấm **Merge pull request → Confirm merge** (hoặc làm theo quy trình bảo vệ nhánh của repo). Khi `main` đã có Dockerfile và lock file, chuyển thẳng sang bước 2; không cần chạy các lệnh commit bên dưới. Cũng có thể triển khai trực tiếp nhánh `codex/dokploy-deploy` để thử trước khi merge.

Mở PowerShell tại thư mục dự án:

```powershell
cd D:\project-annhome\resizeAssets
git status --short
git add Dockerfile .dockerignore requirements-docker.lock test_deployment.py static/index.html README.md docs/DEPLOY_DOKPLOY.md docs/ky-thuat.md
git commit -m "build: prepare Docker deployment for Dokploy"
git push origin main
```

Nếu GitHub yêu cầu đăng nhập, hoàn tất trong cửa sổ trình duyệt được mở. Nếu dùng GitHub CLI và gặp lỗi token:

```powershell
gh auth login --hostname github.com --web --git-protocol https
gh auth setup-git
git push origin main
```

Dùng tài khoản có quyền ghi repo `Astramyth/resizeAssets`. Không gửi mật khẩu hoặc token vào chat. Nếu `main` được bảo vệ, đẩy lên nhánh riêng và tạo pull request thay vì ép push:

```powershell
git switch -c codex/dokploy-deploy
git push -u origin codex/dokploy-deploy
```

Mở repo trên GitHub, xác nhận nhánh sẽ deploy đã có `Dockerfile` và `requirements-docker.lock`.

## 2. Tạo project và ứng dụng

1. Mở `http://113.166.120.18:3000/` và đăng nhập bằng tài khoản Dokploy của bạn.
2. Chọn **Projects → Create Project**, đặt tên `resizeAssets` rồi tạo.
3. Mở project và environment (thường là `production`).
4. Chọn **Create Service → Application**, đặt tên `resizeassets`.
5. Mở ứng dụng vừa tạo, vào **General** để cấu hình nguồn mã.

Tên nút có thể khác đôi chút giữa các phiên bản Dokploy; cần tạo **Application**, không phải Static Site hay database.

## 3. Kết nối repo

### Repo công khai: dùng Git cho nhanh

Chọn provider **Git**, điền và lưu:

| Trường | Giá trị |
|---|---|
| Repository / Git URL | `https://github.com/Astramyth/resizeAssets.git` |
| Branch | `main` |
| Build Path | `/` |
| SSH Key | Để trống khi clone HTTPS repo công khai |

### Repo riêng tư hoặc muốn liên kết GitHub

1. Vào **Git Sources → GitHub** trong Dokploy và kết nối GitHub theo hướng dẫn trên màn hình.
2. Cấp quyền cho GitHub App truy cập repo `Astramyth/resizeAssets`; có thể chỉ chọn repo này.
3. Nếu repo thuộc tổ chức, tài khoản quản trị tổ chức có thể cần phê duyệt cài GitHub App.
4. Quay lại ứng dụng, chọn provider **GitHub** rồi điền:

| Trường | Giá trị |
|---|---|
| GitHub Account / Source | Kết nối GitHub vừa tạo |
| Owner | `Astramyth` |
| Repository | `resizeAssets` |
| Branch | `main` |
| Build Path | `/` |

Nếu chưa merge pull request, dùng đúng tên nhánh có Dockerfile. Không nhập token vào Git URL. Nếu không thấy repo, kiểm tra quyền của GitHub App và quyền truy cập tổ chức.

## 4. Chọn cách build và cấu hình chạy

Ở **General → Build Type**, chọn:

| Trường | Giá trị |
|---|---|
| Build Type | `Dockerfile` |
| Dockerfile Path | `Dockerfile` |
| Docker Context Path | `.` |
| Docker Build Stage | Để trống |

Nhấn **Save**. Ở phần Environment, không cần thêm biến nào.

Ở **Advanced**:

- Giữ **Replicas = 1** nếu có trường này.
- Để trống **Command / Arguments** để dùng lệnh có sẵn trong Dockerfile.
- Không thêm published port trong **Ports**; truy cập qua domain của Dokploy.
- Không gắn volume cho `/app` hoặc `/tmp`.
- Không đặt health check HTTP ngắn: một lần nén PDF lâu có thể giữ tiến trình bận, làm health check báo lỗi dù ứng dụng vẫn đang xử lý.

Dockerfile đã đặt **1 worker, 1 thread, timeout 600 giây**. Dữ liệu job nằm trong bộ nhớ một tiến trình. Tăng worker/replica sẽ làm tải file hoặc xem trước lỗi ngẫu nhiên. Một tiến trình cũng giúp tránh chạy xử lý PDF đồng thời bằng nhiều thread.

Nếu có nhiều người cùng nén, yêu cầu sẽ chờ nhau. Chưa có kiểm thử tải để xác định số người/file tối đa. Theo dõi RAM trong tab Monitoring và thử file thực tế trước khi đặt giới hạn RAM quá thấp.

## 5. Deploy lần đầu

1. Nhấn **Deploy**.
2. Vào **Deployments**, mở bản triển khai mới nhất để xem log build.
3. Lần đầu cần tải image Python và thư viện nên có thể mất vài phút.
4. Khi build xong, mở **Logs**. Cần thấy Gunicorn khởi động, lắng nghe `0.0.0.0:8765` và có một worker.

Nếu build báo không có Dockerfile/lock file, kiểm tra bước 1, nhánh Git và Build Path. Không chạy `run.bat` hoặc `python app.py` trong Dokploy.

## 6. Gắn tên miền và HTTPS

### Có tên miền riêng — nên dùng cho file thật

Ví dụ muốn dùng `resize.tenmiencuaban.com`:

1. Vào trang quản lý DNS của tên miền, tạo bản ghi `A` tên `resize`, trỏ tới IP máy chủ chạy ứng dụng. Dùng `113.166.120.18` nếu ứng dụng chạy trên chính máy Dokploy này.
2. Nếu quản lý DNS bằng Cloudflare, có thể để **DNS only** trong lần cấp chứng chỉ đầu tiên.
3. Trong ứng dụng Dokploy, vào **Domains → Add Domain**:

| Trường | Giá trị |
|---|---|
| Host | Tên miền thật của bạn, không thêm `http://` hoặc `https://` |
| Path | `/` |
| Internal Path | Để trống |
| Strip Path | Tắt |
| Container Port | `8765` |
| HTTPS | Bật |
| Certificate | `Let's Encrypt` |

4. Lưu. Nếu không truy cập được hoặc cấp chứng chỉ thất bại, cần quản trị server kiểm tra DNS và mở/chuyển tiếp TCP `80`, `443` về Traefik của Dokploy.
5. Mở địa chỉ `https://` của ứng dụng và xác nhận chứng chỉ hợp lệ.

Cổng `3000` dành cho trang quản trị Dokploy; tên miền ứng dụng không thêm `:3000` hay `:8765`.

### Chưa có tên miền — chỉ thử bằng file mẫu

Trong **Domains**, chọn **Generate Domain**, đặt **Container Port = 8765**, **Path = /**, lưu và mở địa chỉ được sinh ra. Domain miễn phí mặc định dùng HTTP. Không tải hồ sơ thật, file nhạy cảm hoặc dùng mật khẩu thật qua HTTP. Khi cần dùng thật, cấu hình HTTPS trước.

## 7. Đặt mật khẩu truy cập

Sau khi có HTTPS, vào **Advanced → Security**, thêm **Username** và **Password** rồi lưu. Nếu giao diện yêu cầu redeploy để áp dụng, thực hiện redeploy. Dùng tên đăng nhập và mật khẩu riêng cho ứng dụng, không dùng lại mật khẩu quản trị Dokploy.

Mở cửa sổ ẩn danh để kiểm tra: trình duyệt phải hỏi mật khẩu trước khi hiển thị ứng dụng. Đây là Basic Auth do Dokploy cung cấp, không phải hệ thống tài khoản của ứng dụng. Người biết cùng mật khẩu dùng chung dịch vụ; ứng dụng chưa có phân quyền theo từng người.

Không publish trực tiếp cổng `8765` ra internet vì sẽ có đường truy cập bỏ qua lớp bảo vệ domain. Nếu phiên bản Dokploy của bạn không có mục Security, yêu cầu quản trị đặt lớp xác thực tại reverse proxy hoặc giới hạn truy cập qua mạng riêng trước khi dùng file thật.

## 8. Kiểm tra sau triển khai

Sau khi truy cập đúng địa chỉ HTTPS và đăng nhập:

1. Tải một ảnh JPG nhỏ, chọn mục tiêu 5 MB. File nhỏ hơn mục tiêu sẽ giữ nguyên; tải kết quả và mở thử.
2. Tải một ảnh lớn hơn mục tiêu để kiểm tra nén thực sự.
3. Tải PDF không có mật khẩu, kiểm tra tải xuống và nội dung chữ.
4. Chọn **So sánh** cho ảnh và PDF, thử đổi trang PDF.
5. Chọn nhiều file trong một lượt, xác nhận ZIP tải về và mở được đủ file.
6. Tải lại trang, kiểm tra không có lỗi tải tài nguyên. Xem Logs/Monitoring nếu API lỗi hoặc RAM tăng mạnh.

Không dùng file quan trọng trong lần thử đầu tiên. Tải kết quả về ngay; ứng dụng không phải nơi lưu hồ sơ.

## 9. Cập nhật và vận hành

- Sau mỗi lần sửa mã, push lên GitHub rồi **Deploy** lại. Lần đầu để deploy thủ công; chỉ bật Auto Deploy khi đã kiểm tra xong.
- Restart/redeploy hoặc worker bị timeout/thiếu RAM sẽ mất danh sách kết quả cũ. Kết quả tải xuống trước đó trên thiết bị vẫn còn.
- Hiện chưa có tự dọn file định kỳ: ảnh/PDF gốc, kết quả và preview có thể tích tụ khi dùng lâu. Theo dõi dung lượng đĩa của server; khi cần dọn, chờ người dùng tải xong rồi thay container bằng một lần redeploy. Không dùng restart worker như cam kết xóa sạch dữ liệu.
- Không mount `/tmp` ra volume: app chưa hỗ trợ khôi phục danh sách job từ đĩa.
- Gunicorn ghi access/error log ra console. URL tải/xem trước chứa mã job; chỉ cho người quản trị đáng tin cậy truy cập log. Không coi mã job là hệ thống phân quyền người dùng.
- 500 MB là giới hạn tổng body mỗi request, gồm cả multipart; file đúng 500 MB có thể bị từ chối. Reverse proxy/CDN có thể áp giới hạn upload và thời gian chờ thấp hơn. Chưa kiểm chứng file gần giới hạn này qua Dokploy.

## Lỗi thường gặp

| Hiện tượng | Kiểm tra / xử lý |
|---|---|
| Không thấy repo GitHub | Quyền của GitHub App, tài khoản/tổ chức và tên repo |
| Clone báo authentication failed | Repo riêng tư cần GitHub provider được cấp quyền hoặc SSH key; không dùng Git HTTPS ẩn danh |
| Dockerfile hoặc lock file không tồn tại | Đã push chưa, đúng nhánh chưa, Build Path `/`, Context `.` |
| 502 Bad Gateway | Gunicorn có chạy không, Container Port phải là `8765`, Command không bị ghi đè |
| 413 Request Entity Too Large | Tổng upload vượt 500 MB hoặc giới hạn của proxy/CDN |
| 504 / timeout khi nén | File nặng, yêu cầu đang chờ, timeout proxy/CDN hoặc thiếu tài nguyên; tăng timeout Gunicorn không tự tăng timeout proxy |
| File vừa nén đã báo không tìm thấy | Có nhiều worker/replica, worker vừa restart hoặc vừa deploy; trở về cấu hình một tiến trình rồi nén lại |
| Domain không mở được | DNS, IP server triển khai thực tế, NAT/firewall và cổng 80/443 |
| HTTPS không cấp được | DNS chưa đúng, cổng 80/443 chưa tới Traefik, hoặc cấu hình domain/chứng chỉ chưa đúng |
| Không hỏi mật khẩu | Kiểm tra trong cửa sổ ẩn danh; Security đã lưu/áp dụng chưa; không truy cập qua published port |

## Kiểm tra Docker trên máy trước khi deploy

Cần Docker Desktop chạy Linux containers:

```powershell
cd D:\project-annhome\resizeAssets
docker build -t resizeassets:dokploy .
docker run --rm --name resizeassets-check -p 127.0.0.1:18765:8765 resizeassets:dokploy
```

Giữ cửa sổ đó mở. Ở PowerShell khác:

```powershell
cd D:\project-annhome\resizeAssets
.venv\Scripts\python.exe test_deployment.py http://127.0.0.1:18765
```

Script tạo file mẫu, kiểm tra trang chủ, tài nguyên, upload JPG/PDF, tải file, preview, ZIP và từ chối mã job sai. Không chạy script này trên dịch vụ không thuộc quyền quản lý của bạn. Dừng container bằng Ctrl+C ở cửa sổ đầu.

Kiểm tra thuật toán hiện có:

```powershell
.venv\Scripts\python.exe test_compress.py
```

## Tài liệu chính thức đã đối chiếu

- [Dokploy: Dockerfile Build Type](https://docs.dokploy.com/docs/core/applications/build-type)
- [Dokploy: Domains](https://docs.dokploy.com/docs/core/domains)
- [Dokploy: Advanced / Security / Ports](https://docs.dokploy.com/docs/core/applications/advanced)
- [Flask: chạy bằng Gunicorn](https://flask.palletsprojects.com/en/stable/deploying/gunicorn/)
