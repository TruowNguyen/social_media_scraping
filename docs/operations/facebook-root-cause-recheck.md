# Truy vết lỗi Facebook — kiểm tra lại 09/10/2026

> **Snapshot lịch sử theo ngày trong tài liệu.** Các trạng thái “chưa triển khai”, disabled hoặc lỗi probe chỉ áp dụng cho lượt kiểm tra đó. Đối chiếu code/config hiện hành ngày 11/10/2026 tại [trạng thái dự án](../current-state.md); không dùng snapshot này để kết luận runtime hiện tại.

## Kết quả hiện tại

Sau khi người dùng đóng và lưu phiên Facebook, đúng permalink `987006180721696` mở được bằng persistent profile headless. Lượt thread cuối lưu một POST, caption 54 ký tự, thời gian đăng `2026-10-09T11:50:37Z` (18:50:37 giờ VN). Không còn error code `LISTING_SELECTOR_MISMATCH`, `CONTENT_UNAVAILABLE` hoặc `THREAD_PARSER_FAILED` trong lượt cuối.

[Native thread report sau sửa](../../reports/facebook-thread-session-recheck-after-fix.json), [đối chứng group và hai bài khác](../../reports/facebook-root-cause-recheck.json).

Hai bài đối chứng cũng đọc được caption (472 và 283 ký tự) và timestamp INSTANT. Có authentication cookie trong profile; chỉ kiểm tra presence, không log giá trị. Cookie presence không tự xác minh phiên hợp lệ.

## Nguyên nhân và bằng chứng

1. **Profile đang được dùng:** tiến trình `engine.browser_session --platform facebook --login` giữ khóa profile; dashboard không có active crawl job. Diagnostic trả PROFILE_IN_USE đúng thiết kế. Sau khi người dùng đóng cửa sổ và lưu, profile được dùng bình thường. Không xóa lock/đóng tiến trình trái ý người dùng.
2. **Lỗi truy cập ban đầu:** ảnh native trước đó thực sự hiển thị “Bạn hiện không xem được nội dung này”. Access detector cũ không nhận thông báo span, dẫn đến lỗi selector nhầm; đã sửa ở audit trước. Hiện bài đã hiển thị. Chưa chứng minh cookie bị chặn hoặc hết hạn. Phiên được lưu lại và trạng thái bài thay đổi theo thời gian là hai yếu tố đồng thời: published_at hiện đọc được mới hơn các lần kiểm tra lỗi trước đó. Không kết luận chỉ cookie gây ra lỗi, cũng không tự kết luận bài đã bị xóa/khôi phục.
3. **Thao tác comment trên nền popup:** native permalink mở dialog chồng lên group feed. Parser cũ tìm sorting/load-more trên cả page, có thể click control nền bị popup che; một lượt gặp THREAD_PARSER_FAILED. Đã giới hạn DOM comment và control vào dialog đang hiển thị, xử lý cả hai role=dialog lồng nhau. Không tự chọn khi có nhiều dialog độc lập.
4. **Đếm link chưa chứng minh có comment của target:** diagnostic đầu đếm toàn trang, bao gồm nền feed. Một bài đối chứng hiển thị “Chưa có bình luận nào”. Sau giới hạn đúng dialog, native lượt cuối chưa đọc được comment; coverage UNKNOWN, không tuyên bố đã thu đủ.

## Kiểm thử và giới hạn

- Chromium fixture suite trước xử lý nested wrapper: 10 tests pass. Sau thay đổi cuối, 3 thread browser tests pass, gồm nested dialog/background controls không bị click.
- Regression contract 166 tests đã pass trong audit schema trước đó.
- Native lượt cuối: status PARTIAL, root POST trong window, 0 observed comments, full_thread_verified=false. Caption/time live có evidence; comments/replies live trên bài thật có comment và đối chứng đầy đủ vẫn chưa đạt.
- DB dùng `sessions/pilot/v2/session-recheck.sqlite3`, không migrate hoặc ghi đè DB production. Không đăng bài/comment, không thay lịch dashboard.

Ưu tiên tiếp theo: chọn bài đang hiển thị và có comment/reply đọc được, đối chiếu native IDs/timestamps trong cùng window. Không dùng bài không có comment quan sát được để kết luận parser đã thu đầy đủ.
