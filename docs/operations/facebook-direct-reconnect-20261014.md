# Facebook Chạy ngay: trạng thái và kết quả — 14/10/2026

## Sự cố xác nhận

Người dùng báo Facebook Chạy ngay không đọc được dữ liệu, chờ kết nối lại. Kiểm tra trực tiếp xác nhận crawler vẫn chạy: job `30852edac0a045b7980ebeda3e355184` xử lý 14 group, nhưng API job trả `rows=[]` và không có tiến độ cho đến khi cả lượt kết thúc.

- Giao diện chờ `refreshHealth()` trước `pollJob()`; khi đọc trạng thái chung chậm/lỗi, cập nhật lượt bị trì hoãn. Khởi tạo tab Thu thập cũng chờ health.
- Health tính lại trạng thái phân loại toàn kho, dùng chung khóa đọc với bảng. Đo trước sửa: health 4,46 giây; version 7,33 giây; API job 0,023 giây. Payload health khoảng 341 KB ở thời điểm đo.
- Kết quả cuối trước sửa chỉ lọc theo nguồn/window, chưa giới hạn observations của lượt hiện tại. Số nội dung thiếu thời gian đếm cả lịch sử nguồn.
- Lỗi worker bị gộp thành `SEARCH_FAILED` kể cả Facebook; lỗi từng permalink chưa được đưa vào cảnh báo job.
- Inventory có thể sử dụng hết giới hạn 120 giây của nguồn, không dành thời gian mở bài/bình luận. Không khẳng định đây là nguyên nhân mọi bài thiếu caption.

## Thay đổi

1. Dashboard dùng `/api/health?lightweight=1`, không tính lại phân loại toàn kho. Endpoint cũ vẫn hỗ trợ thống kê đầy đủ. Rút gọn payload nguồn/current run; lỗi health giữ trạng thái gần nhất kèm thời điểm và thông báo thử lại.
2. Đọc job mỗi 5 giây độc lập với health 15 giây; reconnect ban đầu độc lập. Lỗi đọc tiến độ giữ job và kết quả trước đó, không tạo lượt crawl mới. Có nút **Cập nhật tiến độ**; khóa nút bắt đầu khi Facebook đang chạy.
3. Worker lưu tiến độ sau inventory, mỗi hội thoại và mỗi nguồn: nguồn hiện tại, phase, thời điểm cập nhật, group đã xử lý, bài/bình luận/trả lời ghi nhận, trong window, thiếu thời gian. Không tuyên bố bao phủ đầy đủ.
4. Đếm và kết quả job theo observations của inventory/trace thuộc lượt đó. Nội dung đã có được quan sát lại vẫn tính là ghi nhận, không gọi là bản ghi mới. Window vẫn theo thời gian đăng gốc `[start,end)`; thiếu thời gian không xác minh trong window.
5. Inventory tối đa 45% thời gian còn lại của source job (trừ inventory-only), dành phần còn lại đọc bài/bình luận. Raw vẫn được lưu trước filter/classify.
6. Facebook lỗi cấp lượt dùng `CRAWL_FAILED`, giữ tiến độ/raw; đưa lỗi từng hội thoại vào warnings. Lưu loại exception cho chẩn đoán mà không ghi credentials hay nội dung vào thông báo lỗi.

7. Pilot phát hiện `OperationalError` làm outcome nguồn ghi đè inventory/threads đã checkpoint: đã sửa giữ các observations và tiến độ trước lỗi. Raw không bị mất dù báo cáo cũ từng trả 0.
8. Hàng chờ classifier trước đó giữ khóa ghi trong lúc validate/hash/enqueue toàn bộ đầu vào và đọc toàn bộ job chờ. Đã chuyển tính toán ra ngoài khóa, enqueue từng job, claim theo trang 100 và giao dịch ngắn từng job, kiểm tra lại eligibility/revision/lease trong khóa. Kết quả hoàn thành còn hợp lệ tiếp tục được tái sử dụng. Kiểm thử hai worker cạnh tranh một job xác nhận chỉ một worker nhận được job.
9. Trace thật chỉ ra `conversations.py:141` từ chối thay đổi parent của reply: hydration dạng phẳng không trả parent nhưng dữ liệu cũ đã xác minh reply. Parser giữ parent/type/URL đã biết khi chỉ thiếu parent ở lần đọc mới; mâu thuẫn parent/root rõ ràng vẫn bị từ chối. Lineage ghi `parent_restored_from_saved_identity`; không suy ra một quan hệ mới từ nội dung.

## Bằng chứng và giới hạn

- Lượt trước `dashboard_fa15c4617cef44cf9bd5d5cd7e3c5f86`: 523 node được quan sát, 178 bài, 297 bình luận, 48 trả lời; 99 trong window, 342 ngoài window, 82 chưa xác minh thời gian. Đây là dữ liệu thật trong DB, có thể gồm nội dung quan sát lại.
- Lượt hiện tại chọn **14/10/2026 00:00–00:10:51 Việt Nam**, không phải cả ngày 13/10. Snapshot đang chạy: 289 node, 268 ngoài window, 21 thiếu thời gian, 0 xác minh trong window. Snapshot này chưa phải kết quả cuối.
- Vẫn có `NAVIGATION_TIMEOUT`, `THREAD_PARSER_FAILED`, `CONTENT_UNAVAILABLE`, và một nguồn `INVENTORY_FAILED`. Bản sửa trạng thái không chứng minh tất cả parser case đã phục hồi hoặc đã crawl hết group.
- Log cũ còn ghi Threads heartbeat bị `database is locked`; callback heartbeat riêng chưa được refactor trong lượt này. Thu ngắn khóa ghi classifier giảm một nguyên nhân gây tranh chấp dùng chung, không chứng minh mọi SQLite contention đã hết.

Kiểm thử cuối: **119 kiểm thử đạt**, gồm contract classifier/queue, Facebook parser/storage, dashboard, runtime recovery và browser Chromium. UI được kiểm chứng desktop 1440 và mobile 390, health chậm, HTTP 503, job mất, reconnect, giữ bảng/nháp, không dispatch thêm acquisition. Nhãn tiếng Việt được kiểm tra lại sau QA ảnh. Ảnh fixture tại `reports/facebook-direct-progress-1440.png` và `-390.png`, không phải ảnh dữ liệu live.

Impeccable detector có cảnh báo padding wrapper bảng hiện hữu; cell/caption đã có padding 12–16px trong CSS. Không thay bố cục bảng trong bản sửa trạng thái này. Screen reader thực và độ chính xác phân loại chưa được nghiệm thu bằng các kiểm thử trên.

## Pilot sau cập nhật

Pilot giới hạn một nguồn `fb_group_139108668844789`, Playwright Facebook với profile đã lưu, window 13/10/2026 00:00–24:00 Việt Nam. Dùng `SearchService.start()` thật với danh sách một nguồn trong harness; không mock adapter/provider. Không coi pilot này là một lượt HTTP bấm nút trên cả 14 group.

- Lần đầu: tiến độ đạt 26 node/10 trong window rồi SQLite lỗi; raw vẫn giữ nhưng báo cáo cuối ghi 0. Đây là bằng chứng kích hoạt sửa checkpoint/outcome.
- Sau sửa checkpoint và classifier: `dashboard_1596b75efb1e4a378ba82bc6e93e430d` kết thúc PARTIAL, 24 node (15 bài, 9 bình luận), 10 trong window/10 result rows, không có `SOURCE_WORKER_FAILED`; còn `THREAD_PARSER_FAILED`. Chẩn đoán có 3 ValueError đổi parent và 1 timeout browser; từ đó bổ sung sửa reply dạng phẳng.
- Sau sửa reply: `dashboard_faa0761131c945e4824b13047fff6478` kết thúc PARTIAL, ghi nhận **69 node: 18 bài, 43 bình luận, 8 trả lời**; 10 xác minh trong window, 8 chưa xác minh thời gian, 10 result rows. Tiến độ được cập nhật trong lúc chạy. Không xuất hiện `THREAD_PARSER_FAILED` hoặc `SOURCE_WORKER_FAILED` trong lượt này; còn `CONTENT_UNAVAILABLE`, giới hạn thời gian/OCR và coverage chưa đầy đủ. Các số ghi nhận có thể bao gồm quan sát lại dữ liệu đã lưu, không phải 69 nội dung mới hoặc 69 phản ánh.
- Report trước sửa reply: `reports/facebook-direct-live-before-reply-fix-20261014.json`. Report sau sửa reply: `reports/facebook-direct-live-20261014.json`.

Backend đã nạp lại khi cả Facebook/Threads và profile đều rảnh; classifier được nạp lại giữa hai batch khi không có job đang thuê còn hiệu lực. Giữ nguyên database, phiên browser, cấu hình lịch và hàng chờ. Supervisor tự khởi động lại worker đã kết thúc.

Đo live sau cập nhật ban đầu: health nhẹ 0,54 giây, job active 0,027 giây, version 0,746 giây. Có một lần đọc bảng vượt 30 giây khi worker đang chạy; sau đó đọc lại Kho 5.574 nội dung thành công trong 7,407 giây. Không khẳng định mọi lần đọc bảng trên máy này đều dưới 30 giây. Dùng py-spy để đọc stack backend (không dùng `--locals`); công cụ chỉ được cài trong venv cho chẩn đoán, không phải dependency runtime.

Đối soát cuối bằng request localhost có quyền truy cập: cả ba endpoint trả HTTP 200; runtime 0,137 giây, health nhẹ 9,983 giây, Kho 5.574 nội dung 12,177 giây khi đo đồng thời. Report `reports/facebook-direct-final-read-20261014.json`. Lần probe trước từng timeout, nên không coi thông báo kết nối lại là chỉ do giao diện hoặc mọi request đọc đã hết chậm. UI thật cũng đã hiển thị lại bảng Kho, phân trang và nút export. Tối ưu SQL pagination/materialized view còn là công việc tiếp theo.

## Sử dụng

Sau cập nhật backend, tải lại trang bằng Ctrl+F5. Vào **Thu thập → Facebook → Chạy ngay**. Theo dõi group/phase và số nội dung xác minh trong window; mở **Kho dữ liệu** để xem raw đang được lưu. Nếu gặp thông báo kết nối lại, dùng **Cập nhật tiến độ**; không cần bấm tạo lượt khác. Xem **Lịch sử** để phân biệt lỗi một nguồn với cả lượt.

Chọn ngày theo giờ Việt Nam. Ngày hiện tại kết thúc ở thời điểm bấm chạy; lựa chọn ngày không mở rộng window của một lượt đã khởi tạo. Bài cũ có bình luận mới vẫn được quét trong giới hạn rescan, không cam kết toàn bộ bình luận.
