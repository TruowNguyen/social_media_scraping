# Kiểm tra ca sáng 13/10/2026

Trạng thái: **LIVE_RECOVERED / OFFLINE_VERIFIED**. Cơ chế tự khôi phục mới có trong mã nguồn và được nạp ở lần khởi động dashboard tiếp theo; giữ lượt Facebook hiện chạy để tiếp tục lưu dữ liệu.

## Nguyên nhân và đối chiếu

- Hai file `sessions/browser/facebook.lock` và `threads.lock` còn PID 26272 và 31584. Kiểm tra tiến trình thực tế: hai PID đã kết thúc, không có browser sử dụng hai profile trước khi khôi phục. Khóa cũ chỉ dựa vào sự tồn tại của file nên tắt đột ngột để lại `PROFILE_IN_USE` vô thời hạn.
- Facebook: các lượt ca sáng có 14/14 nguồn báo `PROFILE_IN_USE`; tác vụ được đưa lại vào hàng chờ, tiếp tục thử nhưng không mở được browser. Threads: các query của cả hai dự án thất bại cùng lỗi, không có nội dung mới trong các lượt này.
- Giao diện trước khôi phục là phiên chốt lúc **10:34:10**, lọc ngày đăng **13/10**: **3 nội dung = 1 POST + 2 COMMENT**, không phải 3 bài viết hay 3 phản ánh đã xác nhận.
- Database khi bắt đầu kiểm tra có **4 POST + 2 COMMENT** mới được lưu hôm nay, tất cả từ group `139108668844789`; gồm bài ngày 12/10 và bài chưa rõ ngày đăng, nên không đồng nhất với kết quả lọc ngày đăng hôm nay.
- Worker phân loại liên tục đã dừng; bật lịch crawl không tự bật lại worker này. Vì vậy nội dung mới đủ điều kiện còn chờ phân loại.

## Khôi phục và sửa

1. Lưu hai file khóa cũ dưới `reports/*-orphan-lock-20261013.json` sau khi kiểm tra PID và browser; giữ nguyên profile/cookie/database.
2. Facebook tự tiếp tục các tác vụ đang chờ; Threads có thể chạy ở lịch kế tiếp **11:15**, chưa xác nhận lượt Threads mới thành công.
3. Khởi động lại worker Gemini `--serve` theo quyền chạy liên tục đã được chấp thuận; không tạo lại các kết quả hoàn thành còn hợp lệ.
4. `locked_profile` bổ sung khóa OS `.guard` giữ suốt phiên, tự nhả khi process chết. File guard được giữ để tránh race giữa các inode. File `.lock` cũ chỉ được thu hồi khi PID đã chết và kiểm tra không còn browser dùng profile; thông tin chủ khóa không hợp lệ, lỗi kiểm tra hoặc browser còn sống đều giữ trạng thái bận.
5. Làm mới phiên kết quả người dùng với nguyên bộ lọc. Phiên chốt **10:43:19** hiển thị **15 nội dung = 5 POST + 10 COMMENT**, ngày đăng 13/10. Đây là dữ liệu thu được và trạng thái xử lý, không phải 15 phản ánh được chấp nhận.

## Nghiệm thu và giới hạn

- **46 kiểm thử đạt**: profile, schedule/task lease, dashboard raw v2 và Threads. Có kiểm thử process con giữ khóa, bị kill, process khác tiếp quản; khóa sống và browser mồ côi không bị thu hồi; giữ nguyên dữ liệu phiên; thoát lỗi nhả khóa. Log: `reports/profile-recovery-tests-20261013.log`.
- Đối chiếu live xác nhận Facebook tiếp tục đọc inventory/thread và số node mới tăng sau khi gỡ khóa. Báo cáo: `reports/morning-crawl-recovery-20261013.json`; ảnh giao diện: `reports/morning-crawl-recovered-20261013.png`.
- Không xác nhận đã thu hết ca sáng hoặc đủ mọi comments: worker vẫn có quota/time budget, inventory theo lượt hữu hạn, parser và timestamp có thể thiếu. Các nguồn chưa đến lượt vẫn giữ lỗi cũ trong lịch sử cho đến khi có outcome mới.
- Lịch đang lưu khác mặc định ban đầu: Facebook 09:00–13:30 và 17:00–21:30; Threads 09:00–12:30 và 17:00–21:30; đều 45 phút. Giữ cấu hình người dùng hiện có.
- Chưa cài tự khởi động classifier cùng Windows; dừng/reboot có thể cần bật lại worker. Bản sửa tự khôi phục khóa được nạp lần khởi động dashboard tiếp theo, chưa restart giữa lượt crawl đang phục hồi.
