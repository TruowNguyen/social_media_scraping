# Dashboard sau tối ưu UX — 10/10/2026

Đã triển khai và phục vụ tại **http://127.0.0.1:8765**. Nhấn `Ctrl+F5` để tải giao diện mới. Dùng [kế hoạch UXR](../dashboard-ux-implementation-plan.md) làm traceability; kết quả tự động không thay thế nghiệm thu của người vận hành.

## Cách sử dụng

1. **Phản ánh:** chọn nhanh Giữ / Cần xem xét / Loại / Chưa phân loại, hoặc điền bộ lọc rồi bấm **Áp dụng bộ lọc**. Bộ lọc đang nhập tách khỏi bộ lọc đã áp dụng. Nút xử lý hàng chờ ghi rõ phạm vi **toàn hệ thống**, một lượt tối đa 10 nội dung; không giới hạn theo bộ lọc bảng và không phân loại lại kết quả còn hiệu lực.
2. **Kho dữ liệu:** xem raw đã lưu trước khi lọc, gồm bài viết, bình luận và trả lời. Tin đã bị bộ lọc/model loại vẫn có trong kho raw để truy vết; dùng Phản ánh và các bộ lọc khi đánh giá tín hiệu.
3. Bấm tên nội dung hoặc **Đánh giá** để mở chi tiết: bài gốc, nội dung cha, nội dung đang xem, hội thoại đã lưu, kết quả hệ thống và đánh giá của người dùng. Nếu thiếu ngữ cảnh hoặc link chỉ dẫn về bài gốc, giao diện ghi rõ giới hạn. Mở chi tiết không gọi crawler/model.
4. Nhập đánh giá/ghi chú rồi **Lưu đánh giá**. Nháp được giữ theo node/revision trên trình duyệt tối đa 7 ngày, có danh sách mở lại nháp ngoài bộ lọc. Khi hai phiên cập nhật cùng nội dung, phiên cũ nhận xung đột; nháp còn nguyên để so sánh trước khi áp dụng lên phiên bản hiện tại. **Bỏ bản nháp** là thao tác riêng.
5. **Làm mới dữ liệu** sau khi lưu để nhận đánh giá mới vào phiên bảng. **Xuất Excel** xuất mọi trang của đúng phiên bảng, cùng thứ tự, số dòng và ghi chú đã lưu tại thời điểm chốt. Bộ lọc chưa áp dụng và bản nháp không đi vào Excel. File có sheet Phạm vi và tách cột kết quả model, xử lý, đánh giá, ghi chú, chất lượng, UID, URL và nguồn.
6. **Thu thập:** bốn phần Chạy ngay / Lịch hằng ngày / Lịch sử / Nguồn theo dõi. Kết quả lượt chạy giữ khoảng thời gian của chính lượt đó, kể cả khi sửa ô ngày cho lượt sau. Lịch giữ hai khung **05:00–08:30, 17:00–18:30**, chu kỳ **45 phút**, gồm lượt chốt cuối khung. Lịch chỉ chạy khi máy và backend đang hoạt động. Tắt lịch không hủy lượt đang chạy.
7. **Tìm link Google:** dùng SerpApi, nhận keyword/hashtag và ngày. Đây là discovery link; không đảm bảo đã thu mọi bài mới. Nguồn mới vẫn qua hàng chờ duyệt.

Mobile mặc định danh sách và bộ lọc thu gọn; có thể chuyển sang bảng. Bốn tab hỗ trợ phím mũi tên/Home/End. Escape đóng chi tiết và giữ nháp; Tab di chuyển trong dialog.

## Đọc thời gian và trạng thái

- **Ngày đăng:** thời gian riêng của bài/bình luận/trả lời. Bài cũ vẫn làm ngữ cảnh cho bình luận mới. Thiếu hoặc mơ hồ giờ đăng không được xác nhận thuộc khoảng ngày.
- **Có lần thu trong khoảng:** khớp một observation; hiển thị lần thu phù hợp. **Lần thu mới nhất:** chỉ khớp lần thu cuối. UI dùng giờ Việt Nam, bao gồm ngày kết thúc; lưu timestamp UTC.
- **Dự án theo model** khác **theo nguồn/bí danh**. Pending không được coi là đã có model xác định dự án. Kho raw dùng nguồn/bí danh.
- Chất lượng trích xuất, trạng thái xử lý, bộ lọc/model và đánh giá người dùng là các lớp riêng. PASS chỉ cho phép xử lý tiếp; không phải KEEP.
- Registry đủ điều kiện chạy không đồng nghĩa truy cập thành công. Heartbeat worker chưa có là **chưa xác định**; đã cũ là **STALE**. Không dùng trạng thái nút dashboard để suy ra mọi worker đang sống.
- Kiểm tra dữ liệu mới mỗi 15 giây khi trang hiển thị. Bảng giữ nguyên phiên; hiện thông báo để người dùng cập nhật. Tạm dừng kiểm tra khi đang đọc dialog, có nháp, selection hoặc bộ lọc chưa áp dụng. Không tự đóng hội thoại hay thay editor đang tập trung.

## Contract và lựa chọn triển khai

| API | Hành vi |
| --- | --- |
| `GET /api/views?kind=CLASSIFY hoặc LIBRARY&…` | Chốt rows/count/order/review/metadata trong phiên đọc SQLite; trả 25–100 dòng/trang. `refresh=1` bỏ cache đọc 15 giây. |
| `GET /api/views?view_id=…&page=…` | Đọc phiên đã chốt; writer mới không đổi thành viên hoặc dữ liệu của phiên. |
| `GET /api/records/{node_id}`; `/api/threads/{root_id}` | Ngữ cảnh đã lưu; thread phân trang tối đa 100, coverage COLLECTED_ONLY. |
| `POST /api/reviews` | Explicit IDs tối đa 100, revision + expected review version, transaction toàn bộ hoặc không mục nào; request ID idempotent. Dùng lại `node_reviews` và `node_review_history`. |
| `GET /api/views/export.xlsx?view_id=…` | Excel theo snapshot, string cells không thực thi công thức, UID giữ dạng text. |
| `GET /api/health`; `/api/classifications/preview` | Lịch, nguồn, run history, heartbeat và phạm vi global queue. |
| `POST /api/classifications/retry` | Chỉ current FAILED job được đưa về PENDING. Không tự gọi model; DONE/oversized không được reset bằng action này. |

Schema migration additive ở startup, không chạy DDL mỗi request đọc. Thêm `dashboard_views`, `dashboard_review_requests`, index parent; heartbeat worker tạo bảng riêng lúc worker khởi động. Giữ DB `sessions/acquisition/acquisition.sqlite3`.

Phiên lưu tối đa 24 giờ, tối đa 128 phiên; phiên cũ có thể bị thu hồi sớm khi vượt giới hạn. Hết phiên trả 410, UI yêu cầu làm mới, không xuất nhầm dữ liệu mới. Cache tối đa 32 bộ lọc, 15 giây. Cache kiểm tra job chỉ tái sử dụng payload/binding bất biến; vẫn đối chiếu revision raw/context và taxonomy hiện tại mỗi lần đọc.

Nháp v1 dùng **localStorage thay cho IndexedDB** được đề xuất: ghi chú tối đa 2.000 ký tự/node, TTL 7 ngày; bắt lỗi quota/storage và cảnh báo lưu thủ công, không chứa nháp trong URL. Đây là nháp trên máy/trình duyệt, không đồng bộ giữa thiết bị; đánh giá đã lưu dùng SQLite chung.

## Khôi phục lỗi và rollout

- Lỗi phân loại FAILED: mở chi tiết, đọc mã lỗi, đưa về hàng chờ sau khi khắc phục API/cấu hình. Input quá dài cần điều chỉnh batching/input trước khi thử lại.
- Login/CAPTCHA/access denied: kiểm tra bằng đúng profile Facebook đã lưu, hoàn tất thủ công rồi chạy lại. Parser mismatch cần sửa extraction; không coi là không có bài.
- PROFILE_IN_USE: chờ chủ profile hoàn tất. Không xóa lock khi chưa xác minh PID chủ đã dừng và không có browser dùng profile. Không có nút GUI xóa lock tự động.
- Run hiển thị nguồn đang xử lý và thời điểm cập nhật outcome. Cập nhật trước/sau source, không phải heartbeat browser liên tục; nguồn chậm vẫn chịu time budget hiện có. Nguồn lỗi không xóa kết quả nguồn khác.
- Đã backup SQLite bằng backup API: `sessions/backups/uxr-20261010T075022Z.sqlite3`, quick_check OK, 2.241 nodes. Restart dashboard chỉ khi `/api/jobs/active` không có job; đã đối chiếu lịch trước/sau giữ nguyên.
- Rollback UI: phục vụ lại bộ `dashboard.html/dashboard.js/dashboard_classification.js/dashboard.css` cũ tại điểm nghỉ crawl; giữ các bảng additive và dữ liệu/review mới. Không restore DB backup mù vì có thể mất dữ liệu sau backup. Bộ cũ là phương án kỹ thuật rollback, không phải giao diện mặc định.

## Bằng chứng và nghiệm thu còn lại

[Live-read](../../reports/workspace-live-read-validation.json): đủ 2.241 nội dung (348 bài, 1.507 bình luận, 386 trả lời), Excel từng chế độ đủ 2.241 dòng; DB quick_check OK, lịch giữ nguyên, không tạo yêu cầu crawl/model trong kiểm tra.

[Hiệu năng sau tối ưu](../../reports/workspace-performance-final.json): 5 mẫu đọc fresh nối tiếp local/chế độ, nearest-rank p95 **1,244 giây Phản ánh**, **1,124 giây Kho**; cache khoảng **0,003 giây** ở smoke trước. Không phải benchmark đa người dùng.

Chromium fixture kiểm tra nháp/reload/nháp ngoài bộ lọc, lưu lỗi 500, xung đột, ba lượt kiểm tra nền, hội thoại phân trang, bảng/Excel giữ scope, raw crawl bridge, model fake, bộ lọc dự án, keyboard và mobile. [Ảnh desktop](../../reports/workspace-desktop.png), [mobile](../../reports/workspace-mobile.png), [chi tiết mobile](../../reports/workspace-detail-mobile.png). Detector đã chạy một lượt; hai cảnh báo kicker/side accent đã sửa, table wrapper là false positive vì từng ô có padding 12–14px.

**Chưa tự xác nhận nghiệm thu người dùng/mentor (UR-21), screen reader thực tế hoặc mọi tổ hợp zoom 200%.** Cần người vận hành thực hiện health → chọn phản ánh → đọc hội thoại → lưu đánh giá → xuất báo cáo, ghi vướng mắc. Không nâng điểm UX 21/40 thành điểm mới khi chưa đánh giá lại; không dùng kiểm thử giao diện để tuyên bố crawl bao phủ toàn bộ Facebook hoặc model phân loại chính xác.
