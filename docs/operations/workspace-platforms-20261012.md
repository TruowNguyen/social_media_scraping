# Đồng bộ giao diện nền tảng — 12/10/2026

**IMPLEMENTED / OFFLINE_VERIFIED / LIVE_LOCAL_VERIFIED**. Đợt này không bấm chạy crawl/Gemini thủ công. Lịch và worker đã được cho phép trước đó tiếp tục hoạt động; có dữ liệu mới từ lịch tự động trong lúc kiểm chứng.

| Bất tiện | Thay đổi | Backend |
|---|---|---|
| Đầu trang chỉ phản ánh Facebook | Trạng thái Facebook, Threads và phân loại ở mọi tab | `/api/health`, lịch/lease riêng |
| Tên group và keyword khó phân biệt | Nguồn có tiền tố nền tảng trong bộ lọc, bảng và chi tiết | Registry, `node_sources` |
| Lịch Threads chỉ chọn một dự án | Chọn nhiều dự án, phạm vi bài/trả lời, chạy tuần tự | `platform-schedule-v2`, CAS |
| Đã có keyword dễ bị hiểu là đã crawl | Số nội dung duy nhất và lượt gần nhất theo truy vấn | Store/lịch sử thực |
| Lịch sử thiếu dự án | Nền tảng, dự án, query snapshot và window | `acquisition_runs` |
| Reload về lựa chọn mặc định | Giữ nền tảng và dự án trên máy | localStorage |
| Bộ lọc ngày bị tách hàng | Từ/Đến cạnh nhau, bố cục desktop/mobile | Giữ contract lọc |
| Đổi tab khi đang khởi tạo có thể nạp bộ lọc cũ | Bỏ khôi phục của tab đã rời, mở lại controls khi điều hướng | Hủy request/kiểm tra tab |

Phản ánh giữ taxonomy, ý định, quyết định, trạng thái, đánh giá và ghi chú riêng. Kho dữ liệu giữ lọc trích xuất/OCR. Google ghi rõ SerpApi và giới hạn độ mới; mở tab không gửi search. Excel giữ nền tảng/nguồn và snapshot đang xem.

## Lịch đã lưu

Threads: **VinCons và VinWonders Vũ Yên**, bài viết và trả lời; **05:00–08:30**, **17:00–18:30**, **45 phút**, thêm mốc chốt ca. Đã giữ trạng thái đang bật. Không dừng worker Gemini; UI báo theo heartbeat thực, kể cả khi chưa có cập nhật mới.

Đọc v1 chuyển `project_id` thành danh sách một phần tử, không tự mở rộng lịch cũ. API v2 nhận `project_ids`, vẫn nhận payload v1. Mỗi dự án có idempotency key riêng. Một job/profile Threads tại một thời điểm; dự án tiếp theo chạy khi lease rảnh, không bảo đảm cùng giây bắt đầu. Window tích lũy từ đầu ca; catch-up trong ngày vẫn theo cơ chế hiện có.

## Kiểm chứng và giới hạn

- Contract: **255 kiểm thử**, 254 đạt, 1 opt-in bỏ qua; thêm migration/CAS, validation dự án, cùng window, chờ lease, chống trùng và không hiển thị lượt orphan là đang chạy.
- Chromium local: kiểm tra desktop/mobile, bộ lọc/xóa lọc, nháp, review conflict, chi tiết, Excel; thêm lịch nhiều dự án, nguồn/nền tảng, reload, không tràn 390px. SQLite/config tạm, không gọi Gemini/crawler thật.
- Dashboard thực: đầu đợt **3.113 nội dung = 3.070 Facebook + 43 Threads**. Snapshot cuối **3.137 = 3.071 Facebook + 66 Threads**; API lọc Threads trả 66 trong 3,81 giây. Lịch tự động đã bổ sung dữ liệu. IDs cũ và đánh giá được đối soát với backup, không bị xóa.
- Truy vấn **VinCons có 20 nội dung đã lưu**, gồm kết quả nhiễu như “Vincent”; đây không phải 20 phản ánh VinCons. Một số lượt sau báo `BROWSER_NAVIGATION_FAILED`; lỗi được hiển thị theo truy vấn. Không coi số dòng search là chất lượng/coverage đã nghiệm thu.
- Detector có cảnh báo bảng sát viền (padding nằm ở các ô) và border cũ bị override; khai báo border cũ đã dọn. Không tự chấm điểm UX/accuracy từ test.

Backup: `sessions/backups/pre-workspace-platforms-20261012.sqlite3`. Không xóa raw/review hoặc yêu cầu phân loại lại DONE. [Báo cáo đối soát](../../reports/workspace-platforms-validation-20261012.json), [ảnh lịch thật](../../reports/workspace-platforms-schedule-20261012.jpg), [Phản ánh](../../reports/workspace-platforms-reflections-20261012.jpg).

Chưa nghiệm thu: thu đủ window/nested parent, tính liên quan/coverage của VinCons và aliases, lịch nhiều ngày và chất lượng phân loại. [Runbook](threads-acquisition.md).

## Ngày đăng và ngày thu thập

Cột **Ngày đăng** dùng `published_at` của chính nội dung, hiển thị giờ Việt Nam. Bài dùng thời gian bài; bình luận/trả lời dùng thời gian bình luận/trả lời, không dùng ngày bài cha. `collected_at` lấy `last_seen_at`, còn lọc ngày thu có thể dùng observation phù hợp window. Khi lọc theo ngày thu, dòng “Thu: …” hiển thị riêng bên dưới ngày đăng. Thiếu `published_at` phải báo chưa xác định, không thay bằng thời gian crawl. Bản ghi đối chiếu có ngày đăng 18/09 và lần thu 12/10, hai giá trị khác nhau được giữ đúng.
