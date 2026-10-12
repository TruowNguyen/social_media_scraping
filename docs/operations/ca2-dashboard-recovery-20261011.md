# Khôi phục bảng dữ liệu ca 2 — 11/10/2026

- Triệu chứng: tab Phản ánh giữ thông báo “Đang đọc dữ liệu đã lưu…”, không có hàng dữ liệu.
- Xác nhận: database vẫn có 3.070 nội dung. Trong window `[17:00,18:30)` giờ Việt Nam có 7 POST và 12 COMMENT xác định được thời gian đăng. Các lượt 17:45 và 18:30 đều PARTIAL; không xác nhận đã thu hết group.
- Lỗi khóa được kiểm chứng: dashboard khởi động lại gặp `sqlite3.OperationalError: database is locked` tại `BEGIN IMMEDIATE`; worker reconciliation trước đây giữ giao dịch ghi xuyên suốt chuẩn bị input và đối chiếu lịch sử toàn kho.
- Sửa: bỏ giao dịch ghi bao quanh toàn bộ reconciliation; quyết định lọc và enqueue giữ giao dịch riêng. Chỉ consume các outbox event có trước preparation, sau enqueue thành công; event thay đổi đồng thời giữ PENDING. Rerun idempotent sửa được trường hợp crash giữa enqueue và consumption.
- Giao diện giới hạn request 30 giây, hiển thị lỗi và cho thử lại thay vì chờ vô hạn; hủy request khi đổi tab vẫn hoạt động.
- Đã khởi động lại dashboard và worker, giữ database, đánh giá, kết quả model và lịch hàng ngày.
- Kiểm chứng khi worker hoạt động: HTTP 200; Phản ánh hôm nay 252 nội dung (~3,65 giây), Kho dữ liệu quan sát hôm nay 1.354 nội dung (~4,32 giây); health ACTIVE, scheduler alive. Hai số khác nhau do ngày đăng và ngày quan sát là hai phạm vi khác nhau.
- 20 contract tests đạt, gồm thử writer thứ hai và outbox phát sinh đồng thời. Không gọi Gemini trong kiểm thử fixture.
- Còn cần xử lý riêng: inventory/thread parser failures và giới hạn coverage các lượt ca 2. Không suy ra mọi lỗi parser đều do khóa SQLite; lỗi tổng quát hiện chưa lưu đủ exception để xác nhận từng nguồn.
