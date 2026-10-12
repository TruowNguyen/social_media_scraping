# Dashboard raw v2 — 09/10/2026

## Đầu vào, mục tiêu và output nghiệm thu

Đầu vào: group public đã bật/xác minh trong Registry, profile Facebook riêng hiện có, khoảng ngày/khung giờ VN, taxonomy runtime và API Gemini đã cấu hình. Mục tiêu: bỏ đường crawl Facebook v1 trên dashboard, lưu post/comment/reply trước khi lọc, dùng chung DB với classifier. Output: durable source task/outcome, raw nodes/revisions/observations, quyết định filter độc lập, kết quả phân loại, bảng tra cứu và Excel.

## Cách dùng

1. Mở `http://127.0.0.1:8765`, Ctrl+F5.
2. Tab **Thu thập**: chọn VinCons (tổ chức), VinWonders Vũ Yên hoặc tất cả, chọn ngày và chạy. [Lịch raw v2](dashboard-crawl-schedule.md) 05:00–08:30 / 17:00–18:30, chu kỳ 45 phút **có lượt chốt cuối khung**; form chạy ngay không tự đổi lịch đã lưu.
3. **Kho dữ liệu**: lọc group/phạm vi, keyword, loại bài/comment/reply, ngày đăng hoặc lần thu; review/notes và Excel theo phiên đã áp dụng. Raw DROP vẫn giữ, v1 đánh dấu lịch sử.
4. **Phản ánh**: phạm vi dự án theo nguồn/alias giúp đọc cả nội dung đang chờ; issue/intent/relevance dùng kết quả hoặc filter đã lưu. [Bộ lọc hiện hành](reflections-workspace.md) chỉ tra cứu, không chạy crawler/model. Bỏ lọc ngày để xem node thiếu thời gian; project context không tự là kết luận model.

## Luồng và giới hạn

`/api/crawl` và lịch gọi `dashboard_conversations.crawl` → `execute_task` → inventory post → fair rescan permalink đã biết → `trace_thread`/`scan_comments` → raw SQLite → OCR POST → filter từng node → worker Gemini → dashboard. Worker `--serve` mặc định poll 15 giây; trạng thái thực xem health. Comments bài cũ xét ngày riêng, intent bài cha không quyết định con. Google/SerpApi discovery là tab riêng.

DB duy nhất: `sessions/acquisition/acquisition.sqlite3`, chứa raw, lịch sử acquisition/Google, reviews và kết quả phân loại. [DB riêng cũ đã được hợp nhất và bỏ](unified-database-backfill.md). Custom `--conversation-db` phải dùng cùng đường dẫn cho dashboard và classifier. Source tasks/outcomes được lưu trước browser, lease bảo vệ khi crash; dashboard resume task thuộc chính lượt dashboard. Profile bận giữ task PENDING với cooldown; source disabled không mở browser. Nút crawl/lịch có giới hạn 20 phút/run, tối đa 100 candidate inventory/group và 20 thread/group. CLI backfill 14 ngày dùng budget lớn hơn được ghi trong runbook. Nguồn lỗi không xóa raw đã thu; coverage PARTIAL/UNKNOWN không được chuyển thành chứng nhận đầy đủ.

Các post cũ chưa từng nằm trong inventory vẫn có thể bị bỏ sót comment mới. Coverage toàn watchlist/comment/reply chưa nghiệm thu. OCR ảnh POST và UI hội thoại đã implement theo [OCR](facebook-image-ocr.md)/[workspace](dashboard-workspace.md); benchmark OCR, UAT và OCR ảnh child/video còn thiếu. Worker chưa tự khởi động cùng Windows.

## Bằng chứng

- Regression: 184 contract tests và 2 Chromium fixture tests (route nút crawl, giữ comment dưới bài tuyển dụng, ngày comment riêng, raw thiếu giờ, filter, review/notes và Excel).
- Pilot Facebook thật: `reports/dashboard-raw-v2-live-pilot.json`; group `139108668844789`, window UTC `[2026-10-08T16:05:37.952978Z, 2026-10-09T16:05:37.952978Z)`, inventory 3 post, thử 2 thread, đọc được 6 comment trên post `986690324086615`. Thread còn lại không đọc được comment và được ghi UNKNOWN, không kết luận không có comment. Không có reply live được chứng nhận.
- Profile lock sót từ process đã kết thúc được gỡ sau khi kiểm tra PID và không còn Chromium dùng profile; không đổi cookie hay phiên. Pilot bị khóa trước đó được hủy task để giữ đúng giới hạn pilot, không replay ngoài ý muốn.
- Raw live dùng chung chứa 4 POST và 6 COMMENT (5 comment có text, 6 có thời gian xác minh); worker đã phân loại các node đủ dữ liệu, giữ raw dù DROP. Kết quả này không là số phản ánh/ngày hay đánh giá accuracy. Biên bản triển khai và kiểm tra giao diện thật: `reports/dashboard-raw-v2-validation.json`.
