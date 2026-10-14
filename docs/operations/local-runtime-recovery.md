# Tự khởi động và chạy bù trên Windows

Code triển khai ngày 13/10/2026. Dùng kho hiện tại `sessions/acquisition/acquisition.sqlite3`; không di chuyển/xóa raw, reviews, OCR hay kết quả phân loại. Quyền gọi Gemini nền giữ theo chấp thuận hiện có.

## Cài và chạy

```powershell
Set-Location 'D:\task\social_listening\social_media_scraping'
.\scripts\Install-LocalRuntime.ps1
```

Script đăng ký tác vụ **SocialListeningRuntime** cho người dùng hiện tại, trigger **khi đăng nhập Windows**, chạy với quyền Limited/Interactive. Không yêu cầu mật khẩu; không sửa chế độ ngủ hoặc bật máy. Task có MultipleInstances=IgnoreNew, không giới hạn thời lượng, cho phép chạy trên pin và thử lại tối đa 3 lần cách một phút nếu task lỗi. Chạy script lại cập nhật cùng task, không tạo task thứ hai. `-NoStart` chỉ đăng ký, chưa chạy ngay.

Tác vụ chạy `engine.runtime_supervisor`. Supervisor giữ khóa OS riêng chống khởi động trùng; mỗi 10 giây kiểm tra process dashboard/classifier. Process đang có được nhận quản lý, không kill/tạo bản sao. Worker đã kết thúc được tạo lại với backoff; lỗi kiểm tra process giữ trạng thái DEGRADED, không đoán rằng worker đã chết. Cơ chế không tự kill một process còn sống nhưng đang bị treo; trường hợp đó vẫn cần truy vết.

Mỗi 60 giây supervisor gọi endpoint cùng origin `/api/runtime/catchup`; dashboard đối soát lịch và tạo nhiệm vụ bù. Endpoint đọc `/api/runtime/status` không xây bảng toàn kho, không gọi Gemini hay browser.

Chạy thủ công nếu chưa cài task:

```powershell
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.runtime_supervisor
```

Mở http://127.0.0.1:8765. Giữ supervisor chạy để giám sát worker; `Ctrl+C` dừng giám sát, giữ các worker đang chạy để không ngắt crawl giữa chừng. Cài task để supervisor chạy nền không phụ thuộc terminal. Nếu supervisor đã chạy, gọi lại lệnh chỉ báo đã chạy và thoát.

## Quy tắc chạy bù

- Chỉ áp dụng lịch **DAILY_SLOTS đang bật**, theo giờ Việt Nam. Facebook và Threads giữ cấu hình/worker riêng, mỗi profile một browser job.
- Lần đầu ghi nhận lịch: lưu snapshot cấu hình và đối soát **các ca đã đóng hôm nay**, với cờ `initial_current_day_assumption`. Không áp lịch hôm nay vào các ngày cũ chưa từng quan sát cấu hình.
- Các lần mở lại: đối soát các ca đã đóng trong **7 ngày**, dựa trên snapshot đã lưu trước downtime. Không replay mọi tick 45 phút; một nhiệm vụ bù cho mỗi ca và scope/configuration.
- Cấu hình được quan sát khi supervisor đối soát, tối đa khoảng 60 giây khi online. Không tự biết thời điểm chính xác nếu file lịch bị sửa lúc hệ thống tắt. Thay cấu hình giữa ca tạo `SKIPPED_PARTIAL_HISTORY`, không giả rằng cấu hình đó áp dụng toàn ca.
- Ca đang mở do scheduler hiện có xử lý. Tick đến hạn/worker đang bận được ưu tiên; bù chỉ dispatch khi nền tảng rảnh. Không mở browser thứ hai cạnh job đang chạy.
- Lượt thường đã quét toàn khoảng ca và đủ source/query snapshot được ghi nhận `ATTEMPTED`; không tạo lượt bù trùng. `ATTEMPTED` là **đã thực hiện lượt quét giới hạn**, không phải đã thu hết mọi bài/bình luận.
- Bù dùng raw v2: inventory → rescan bài cũ/bình luận mới → lưu raw/observations → OCR/filter/classifier hiện có. Không lấy ngày thu làm ngày đăng; thiếu timestamp không xác nhận thuộc ca.
- Ca vượt lookback giữ bản ghi `EXPIRED`; nguồn/query đã đổi hoặc tắt giữ `SKIPPED_CONFIG_CHANGED`; login/CAPTCHA giữ `BLOCKED`. Lượt Threads lỗi có retry giới hạn 3; Facebook tiếp tục tác vụ durable cùng run khi profile bận. Không retry login vô hạn.
- Các ca lịch tắt không được tự tạo mới. Ca đã biết nhưng nguồn/lịch hiện tắt giữ pending để không tự thu ngoài phạm vi đã bật.
- Classifier xử lý dữ liệu đã lưu ngay khi máy hoạt động, không đợi crawl hết ca. DONE hợp lệ được reuse; sau crash một request chưa commit có thể phải gửi lại, không cam kết API exactly-once.

Đổi giới hạn trong `.env` rồi restart dashboard khi không có browser job:

```dotenv
RUNTIME_CATCHUP_DAYS=7
```

Giá trị hợp lệ 1–30. Ca đã đánh dấu EXPIRED không tự hồi sinh khi tăng lookback; backfill thủ công cần xác định lại phạm vi. Browser có quota/time budget và có thể thiếu parser/timestamp; chạy bù không phục hồi được nội dung đã xóa/ẩn trong downtime.

## Xem trạng thái

```powershell
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.runtime_supervisor --status
Get-ScheduledTask -TaskName 'SocialListeningRuntime' | Select-Object TaskName,State
Invoke-RestMethod 'http://127.0.0.1:8765/api/runtime/status'
```

Supervisor state: `sessions/runtime/status.json`; ledger và lịch sử: bảng `runtime_catchup`, `runtime_schedule_history` trong DB chung. State gồm PID/quyền sở hữu process, counts và 20 ca gần nhất; không chứa key/cookie/nội dung bài. Task Running không tự chứng minh worker khỏe; xem thêm `classifier_active`, `facebook_running`, `threads_running` và trạng thái catch-up.

Logs process mới: `reports/dashboard-supervised.*.log`, `reports/classification_worker-supervised.*.log`; process đã có giữ log cũ. Classifier mới ghi report `reports/classifier-supervised-latest.json`.

## Tắt tự khởi động

```powershell
Disable-ScheduledTask -TaskName 'SocialListeningRuntime'
```

Lệnh này chỉ tắt trigger tự chạy sau đăng nhập, không dừng các process hiện đang chạy. Để ngừng thu mới, tắt lịch cả hai nền tảng trong dashboard và chờ tác vụ hiện tại kết thúc. Supervisor vẫn duy trì classifier/hàng chờ khi đang chạy. Không dùng kill toàn bộ Python hoặc xóa profile để dừng.

## Kiểm chứng

Contract tests bảo vệ downtime nhiều ngày, idempotency/reuse, timezone/closing slots, lịch disabled/config changed, lookback, crash trước dispatch, đang COLLECTING, login blocked, khóa profile, process adoption/backoff và worker con thật bị kill rồi được thay thế. API fixture bảo vệ Origin và status không đọc toàn kho. Các fixtures không gọi Facebook/Threads/Gemini ngoài máy.

Live: task đã được đăng ký và Start-ScheduledTask thật; supervisor đã khởi động backend mới, nhận classifier cũ đang hoạt động, raw crawl được tiếp tục bằng durable run. Chưa reboot/logoff máy người dùng để nghiệm thu trigger qua phiên Windows mới; chưa xác nhận coverage đầy đủ của ca chạy bù nhiều ngày live. Bằng chứng bổ sung ở `reports/local-runtime-live-20261013.json` và `reports/runtime-recovery-tests-20261013.log`.
