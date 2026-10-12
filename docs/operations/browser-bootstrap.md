# Browser bootstrap và tài nguyên pilot

Đối chiếu 11/10/2026: Playwright/Chromium, browser manager và profile lock đã có; Facebook đã có mẫu nguồn/native ID/time và backfill bằng profile dự án. TikTok live vẫn chưa acceptance. Browser binary/profile paths và commands dưới đây giữ cách bootstrap; số phiên bản cài đặt ngày 08/10 là evidence lịch sử, không pin mọi môi trường mới.

Cách vận hành [acquisition v1](acquisition-runbook.md) và [raw dashboard v2](dashboard-raw-v2.md) dùng Playwright cục bộ; browser kết nối với agent không phải dependency của CLI. Probe login/CAPTCHA/invalid-key ban đầu trong [report ngày 08/10](acquisition-live-probes.json) là lịch sử; trạng thái config ở [trang hiện hành](../current-state.md).

Chạy từ repository root. Venv hiện tại được quản lý bằng uv và không có pip module; dùng uv khi cài thêm:

```powershell
uv pip install --python .\.venv\audit\Scripts\python.exe -r requirements-browser.txt --cache-dir .\.venv\uv-cache
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Get-Location) '.venv\playwright-browsers'
.\.venv\audit\Scripts\python.exe -m playwright install chromium
.\.venv\audit\Scripts\python.exe -m engine.browser_session --platform facebook --smoke
.\.venv\audit\Scripts\python.exe -m engine.browser_session --platform tiktok --smoke
```

Mở browser tương tác để tự đăng nhập, rồi đóng cửa sổ khi xong:

```powershell
.\.venv\audit\Scripts\python.exe -m engine.browser_session --platform facebook --login
.\.venv\audit\Scripts\python.exe -m engine.browser_session --platform tiktok --login
```

Profile nằm ở `sessions/browser/facebook` và `sessions/browser/tiktok`, được Git ignore. Bootstrap/crawl khóa profile, một nền tảng bận không chặn nền tảng khác. Login timeout mặc định 1.200 giây, `--timeout` 1–1.200; đóng context/release lock khi kết thúc. Sau process bị kill chỉ xử lý đúng lock khi xác minh browser/job chủ đã dừng; không xóa profile. Browser job manager có deadlines/source isolation đã implement.

Browser binaries và profile mặc định theo repository root của module, không phụ thuộc CWD. Profile hiện có được tái sử dụng, không bị xóa hoặc tạo lại mỗi lần chạy. Có thể override `PLAYWRIGHT_BROWSERS_PATH` qua env/.env. Fresh venv dùng pip thì `python -m pip install -r requirements-browser.txt` cũng được. Playwright cài FFmpeg phụ trợ của browser; **không coi đây là FFmpeg/ASR stack cho yt-dlp đã thiết lập**. transformers/faster_whisper/model tier chưa cài.

Mỗi lần `--login` đều mở trang chủ Facebook/TikTok; quay về trang chủ không đồng nghĩa bị đăng xuất. Lệnh in đường dẫn profile để đối chiếu giữa hai lượt. Sau khi đóng cửa sổ, đợi command kết thúc rồi mở lại; không dừng cưỡng bức process khi browser đang ghi dữ liệu. Nếu cùng profile vẫn yêu cầu tài khoản/mật khẩu, ghi nhận là session reuse chưa đạt và kiểm tra riêng; không đánh dấu đăng nhập thành công chỉ dựa trên profile tồn tại.

Browser kết nối với agent và Chromium/profile riêng của dự án là hai tài nguyên khác nhau. Smoke local không chứng minh phiên Facebook, platform access hoặc kết nối công cụ UI của agent. Chạy fixtures/CLI không cần đường dẫn skill riêng trên máy tác giả.

Google: đặt SERPAPI_API_KEY trong `.env`/environment. Adapter và atomic request ledger đã implement, cap 20 attempted requests/run và 200/tháng UTC; Google source enabled/VERIFIED, có successful pilot được ghi theo ngày trong runbook. Không xuất key hoặc coi cấu hình enabled là kiểm tra key/quota live hiện tại.

Resource implementation dùng persistent context/profile riêng theo [Playwright BrowserType](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context); cài Chromium theo [Playwright browsers](https://playwright.dev/python/docs/browsers). Không sử dụng default Chrome profile.
