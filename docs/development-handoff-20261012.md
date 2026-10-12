# Bàn giao branch dev — 12/10/2026

Branch `dev` chứa refactor `engine → src`, config/specs/contracts, raw acquisition Facebook/Threads, xử lý OCR, Gemini batching và dashboard đa nền tảng. [README](../README.md) là hướng dẫn cài/chạy; [TODO](../TODO.MD) giữ tiến độ và acceptance.

Ngày 12/10/2026 đã chuyển sang repository độc lập **TruowNguyen/social_media_scraping** (public, `isFork=false`), thay thế fork cũ và giữ nguyên URL. Branch mặc định là `dev`. Sau khi chuyển, theo yêu cầu của chủ repo, khởi tạo lịch sử mới từ snapshot code hiện hành: `main` và `dev` bắt đầu cùng một root commit của `TruowNguyen`, không kế thừa commit hoặc trailer đồng tác giả cũ. [Nguồn gốc code](code-origin.md) vẫn được ghi nhận. Backup đầy đủ trước khi thay lịch sử ở `reports/repository-before-history-reset-20261012.bundle`; bản trước chuyển repo ở `reports/repository-before-migration-20261012.bundle`. Các backup chỉ lưu local. Remote `origin` giữ `git@github.com:TruowNguyen/social_media_scraping.git`.

Sau bước thay lịch sử, chủ repo yêu cầu xóa hẳn repository rồi tạo lại cùng tên để bắt đầu cả metadata GitHub từ đầu. Repository tạo lại chỉ nhận snapshot hiện hành với root commit của `TruowNguyen`; `main` và `dev` cùng snapshot, mặc định `dev`. Bản backup ngay trước lần tạo lại nằm local tại `reports/repository-before-recreation-20261012.bundle`. Không tải lại branch/tag chứa lịch sử nguồn.

Checkout mới dùng lệnh clone bên dưới. Máy khác còn lịch sử trước 12/10 nên clone vào thư mục mới và chuyển lại cấu hình/phiên/dữ liệu local cần dùng; không `git pull` để gộp hai lịch sử độc lập. Đối chiếu commit trên branch để kiểm tra tác giả hiện hành.

## Chạy từ checkout mới

```powershell
git clone --branch dev https://github.com/TruowNguyen/social_media_scraping.git
Set-Location social_media_scraping
py -3.13 -m venv .venv\audit
.\.venv\audit\Scripts\python.exe -m pip install -r requirements-acquisition.txt
.\.venv\audit\Scripts\python.exe -m pip install --no-deps -e .
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Get-Location) '.venv\playwright-browsers'
.\.venv\audit\Scripts\python.exe -m playwright install chromium
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item .env.example .env }
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.acquisition_cli validate
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.dashboard
```

Mở `http://127.0.0.1:8765`. Checkout mới chưa có database, profile browser hoặc lịch đã lưu của máy hiện tại. Trạng thái VERIFIED trong config là metadata kiểm chứng trước đó; vẫn phải chuẩn bị phiên trên máy chạy và kiểm tra lại truy cập. Lưu/bật lịch trong **Thu thập**, chọn nền tảng; cấu hình YAML không tự bật lịch Threads.

Facebook dùng Chromium của Playwright; Threads dùng Chrome đã cài, profile riêng. Đăng nhập thủ công bằng [lệnh browser session](operations/threads-acquisition.md), đóng cửa sổ/hoàn tất lệnh trước khi chạy crawl. OCR cần [requirements/binary Tesseract](operations/facebook-image-ocr.md). Google cần `SERPAPI_API_KEY`; phân loại cần `GEMINI_API_KEY`, `GEMINI_API_BASE_URL`, `GEMINI_MODEL`, endpoint OpenAI-compatible. Sau khi cấu hình:

```powershell
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.classification_worker --serve --poll-seconds 15
```

Worker gửi nội dung/ngữ cảnh/OCR đến provider đã cấu hình; chỉ chạy sau khi người vận hành cho phép sử dụng dữ liệu. Giữ terminal/dashboard hoạt động để lịch chạy. Không tự khởi động cùng Windows.

## Phần mới nhất

- UI: trạng thái cả hai nền tảng ở mọi tab; nguồn/chi tiết/lịch sử ghi rõ Facebook/Threads và dự án/truy vấn.
- Threads schedule v2: `project_ids`, chạy tuần tự trên một profile, CAS và idempotency; giữ compatibility lịch một dự án. Hai ca mặc định 05:00–08:30, 17:00–18:30, 45 phút, có lượt chốt ca.
- Bộ lọc theo contract backend; giữ taxonomy/ý định/decision/status riêng, ngày đăng khác ngày thu. Sửa race khi chuyển tab lúc khôi phục trang, giữ nháp/đánh giá và snapshot Excel.
- Acquisition lưu raw trước filter/classify; identity/dedup theo platform, revisions/observations được giữ. Kết quả DONE còn hợp lệ được tái sử dụng.

Snapshot live cuối của đợt UI: **3.137 nội dung = 3.071 Facebook + 66 Threads**. Truy vấn VinCons có 20 nội dung, gồm nhiễu “Vincent”, không phải 20 phản ánh. Một số lượt Threads báo `BROWSER_NAVIGATION_FAILED`. Coverage Facebook/Threads, nested parent, độ chính xác phân loại, OCR/API Threads và lịch nhiều ngày còn chưa nghiệm thu. [Chi tiết có ngày](operations/workspace-platforms-20261012.md).

## Kiểm chứng trước bàn giao

```powershell
.\.venv\audit\Scripts\python.exe -X utf8 -m unittest discover -s tests
$env:ACQUISITION_BROWSER_TESTS = '1'
.\.venv\audit\Scripts\python.exe -X utf8 -m unittest tests.integration.test_dashboard_workspace_browser
```

Kiểm tra trước bàn giao 12/10: toàn suite **305** (277 pass, 28 skip do các kiểm thử opt-in/live không được bật), compile Python đạt, acquisition config **VALID** (22 sources, 2 watchlists). Kết quả đợt UI đã có: contract **255** (254 pass, 1 opt-in skip), Chromium workspace **3/3** pass. Đây là kiểm thử offline/local, không phải cam kết full coverage hoặc model accuracy.

`.env`, API keys, cookies, `sessions/`, database, `reports/`, exports và tooling agent/design local được ignore. Vì vậy link `reports/` trong tài liệu lịch sử chỉ hoạt động trên máy có artifacts; không cần tải những artifacts này để chạy code. Khi cập nhật, checkout `dev`, `git pull --ff-only`, cài dependency nếu đổi, rồi khởi động lại dashboard/worker để nạp code; giữ dữ liệu/phiên local.
