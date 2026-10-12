# Truy vết nội dung Facebook chưa đọc được — 11/10/2026

## Số liệu hiện tại

Đọc kho raw lúc 13:00 giờ Việt Nam: 2.969 nội dung, 309 chưa có caption/comment; 3 bài đã có chữ OCR nên 306 chưa có đầu vào phân loại.

| Loại nội dung | Tổng | Chưa có text | Tỷ lệ |
| --- | ---: | ---: | ---: |
| Bài viết | 453 | 26 | 5,7% |
| Bình luận | 2.021 | 105 | 5,2% |
| Trả lời | 495 | 178 | 36,0% |

Phần lớn ô trống là bình luận/trả lời, không phải 309 bài viết. Có 6 bài FAILED: 2 CONTENT_UNAVAILABLE, 1 NAVIGATION_TIMEOUT, 3 AMBIGUOUS_THREAD_DIALOG. 20 bài PARTIAL thiếu caption; các lý do media/thời gian/tương tác có thể cùng xuất hiện trên một bài nên không cộng thành số bài.

105 bình luận trống gồm 83 quan sát từ hydration và 22 từ DOM. Cả 178 reply trống có quan sát gần nhất từ DOM; 177 thiếu cả tác giả và thời gian. Thiếu text không tự chứng minh tất cả là lỗi selector, ảnh/sticker hoặc nội dung đã bị xóa.

[Audit SQLite](../../reports/facebook-parser-audit-20261011.json) chỉ ghi số lượng, trạng thái, ID và permalink; không in caption, tên người dùng hoặc URL ảnh có chữ ký.

## Đối chiếu Facebook thật

Cách kiểm tra: Playwright Python + Chromium, profile Facebook đã lưu, browser headless. Không dùng SerpApi, API Facebook hoặc Gemini; không ghi dữ liệu vào DB.

1. Bài `1821743615526214`, group `1675953926771851`: Story có ID/thời gian nhưng không có caption. DOM đang hiển thị caption 41 ký tự **ngoài** `role=article`, trong dialog bài. Parser trước chỉ tìm article nên bỏ qua caption này. Đây là lỗi mã đã được xác nhận.
2. Reply `2158765162190162`, bài `2158366085563403`, group `1280258833374137`: kho lịch sử trống nhưng khi mở permalink reply, hydration có 84 ký tự và thời gian chính xác. Không thể kết luận nội dung đã mất hoặc bị cookie chặn. Cần mở/tải lại reply và cập nhật raw; sửa mã không tự sửa nội dung đã lưu.
3. Bình luận `1821756622191580`, group `1675953926771851`: vẫn không có text từ hydration/DOM trong lần đối chiếu, dù có metadata và thời gian. Chưa xác minh loại nội dung ảnh/sticker hay trạng thái khác; không bịa caption hoặc dùng nội dung cha thay thế.

Quan sát DOM còn cho thấy article bình luận cha chứa jump anchor không có text trỏ đến reply. Parser lấy link comment đầu tiên có thể nhận diện nhầm article cha thành reply. Bản sửa ưu tiên permalink có chữ đang hiển thị, rồi mới xét link hiển thị khác.

[Đối chiếu trước sửa](../../reports/facebook-parser-live-diagnostic-20261011.json), [xác nhận sau sửa](../../reports/facebook-parser-live-recheck-20261011.json).

## Đã sửa và kiểm thử

- Fetch caption: khi không có article bài gốc, dùng dialog duy nhất đã xác minh Story đúng bài và có tham chiếu đúng post trong dialog. Không đọc caption của feed phía sau hoặc article bình luận. Chỉ mở Xem thêm thuộc vùng bài gốc; giữ metadata thời gian/media từ hydration.
- Nhiều message khác nhau trong cùng vùng không được chọn tùy tiện: báo POST_MESSAGE_SELECTOR_AMBIGUOUS.
- Parser bình luận ưu tiên permalink hiển thị để tránh gán nội dung cha vào reply từ hidden jump anchor.
- 21 kiểm thử parser/Chromium đạt, có các ca caption ngoài article, feed phía sau, dialog không thuộc post, hidden reply anchor, text dài và pagination. 264/264 hồi quy toàn hệ thống đạt, gồm Chromium và OCR; [kết quả](../../reports/ocr-test-result.json).
- Kiểm chứng live sau sửa: bài đã đọc được 41 ký tự với thời gian INSTANT; bài cha của reply đọc được 99 ký tự, reply 84 ký tự với thời gian INSTANT. Đây là mẫu hữu hạn, chưa chứng minh đã đọc được mọi nội dung.

## Giới hạn và bước tiếp theo

1. Crawl lại các nội dung thiếu text theo permalink, lưu revision/observation qua kho raw hiện có; không xóa dòng trống hoặc gán nội dung của bài cha. Các phép thử trên chưa cập nhật raw lịch sử.
2. Cần bổ sung tải/đợi reply và vòng kiểm tra tiến độ theo native ID; hiện loop dừng khi không còn control quan sát được hoặc hết thời gian/step limit, chưa chứng minh đã tải mọi reply.
3. Comment/reply chưa có media resolver và OCR runtime. OCR hiện chỉ hỗ trợ ảnh POST, tối đa 3 ảnh/bài và 50 ảnh/lượt. Vì vậy một comment chỉ có ảnh chưa cung cấp được chữ cho classifier. Không suy ra 105 comment trống đều là ảnh từ số liệu này.
4. Với bài không truy cập được, timeout hoặc nhiều dialog: giữ outcome riêng, thử lại có giới hạn; không báo thành công rỗng.
5. Cần manifest đối chứng thêm caption dài, ảnh bình luận, reply lồng nhau và nội dung không còn truy cập được. Browser coverage vẫn PARTIAL/UNKNOWN.

Trạng thái: **IMPLEMENTED / OFFLINE_VERIFIED / LIVE_BROWSER_VERIFIED (bounded)**. Thu lại dữ liệu lịch sử, OCR comment/reply và coverage đầy đủ còn chưa nghiệm thu. Không chạy hoặc gửi dữ liệu đến classifier trong lượt này.

## Lượt thu lại tiếp theo — 11/10/2026

Sau snapshot chẩn đoán phía trên, đã thu lại 306 target lịch sử bằng browser/profile thật và phục hồi 195 input (17 POST, 5 COMMENT, 173 REPLY) vào đúng identity. Trong POST, 9 có caption và 8 có chữ OCR riêng. Còn 100 target thiếu chữ và 11 không truy cập được; coverage đầy đủ/OCR ảnh comment chưa nghiệm thu. Đối chiếu backup giữ IDs/parent/reviews/analyses và không có duplicate identity. Người dùng sau đó cho phép Gemini chạy toàn hàng chờ; 2.692 node đã DONE, không còn job chờ/lỗi hiện hành. [Kết quả phục hồi và phân loại](facebook-recovery-classification-20261011.md).
