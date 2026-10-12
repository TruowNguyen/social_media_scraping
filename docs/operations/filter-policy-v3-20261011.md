# Bộ lọc thương mại và OCR theo ngữ cảnh — 11/10/2026

## Đầu vào và mục tiêu

Raw POST/COMMENT/REPLY trong SQLite, caption/text, OCR riêng, taxonomy hai dự án và Gemini đang cấu hình. Loại nội dung thuần tuyển dụng/thương mại; giữ phản ánh thật và trường hợp thiếu bằng chứng. Intent bài cha không quyết định bình luận. Raw và đánh giá người dùng được giữ.

## Thay đổi đã triển khai

- “Không phải trung gian” không tự bảo vệ tin tuyển dụng. Lời hứa quảng cáo “không phải xếp hàng”, “tránh kẹt xe” không tự chứng minh phản ánh; phản ánh thực tế còn lại vẫn được bảo vệ.
- Bổ sung chào bán điện thoại và câu “inbox em mua vé”; giữ nhãn ý định độc lập cả khi quyết định là REVIEW.
- OCR chưa chắc chắn của chính nội dung vẫn yêu cầu review. OCR bài cha không chặn DROP thương mại khi text target đủ rõ và kết quả không trích OCR chưa chắc chắn làm bằng chứng. “Tôi cũng bị vậy” vẫn cần review ngữ cảnh.
- OCR target đã lưu vẫn được xét khi caption riêng là chào bán; phản ánh trong ảnh không bị caption thương mại che mất. Không tự tải lại ảnh trong bước đối soát filter.
- Provider và validator dùng chung chính sách OCR; vẫn kiểm tra ID, revision, quote, dự án/nhóm vấn đề và từ chối DROP + COMPLAINT.
- Hiển thị lý do tiếng Việt thực tế từ model; bảng/mobile có mục “Lý do · Bộ lọc/Model”. Trích dẫn issue, khi có, lấy từ evidence đã lưu và được escape HTML.
- `commercial-context-v3` vào job hash chỉ cho đầu vào thương mại/OCR chịu ảnh hưởng; đầu vào khác giữ hash cũ và DONE hợp lệ. Schema request/result và taxonomy không đổi.
- Sửa tranh chấp SQLite được phát hiện khi triển khai: `pending_run` và `results` mở store không khởi tạo schema/khóa ghi; scheduler retry SQLITE_BUSY/LOCKED mà không chết thread hoặc tắt lịch.

## Đối soát dữ liệu thật

Worker tạm dừng giữa batch, không còn RUNNING, rồi sao lưu tại `sessions/backups/filter-policy-v3-predeployment-20261011.sqlite3`.

Đối soát không gọi API: 2.254 kết quả hợp lệ được tái sử dụng, 416 job mới, 188 FILTER_DROP (tăng 22), 111 MISSING_TEXT; tổng vẫn 2.969 node. [Report đối soát](../../reports/filter-policy-v3-reconciliation-20261011.json).

Pilot hàng chờ thật: 10/10 kết quả qua validator, hai request batch 6 + 4 đều HTTP 200, không invalid item/lỗi. [Report pilot](../../reports/filter-policy-v3-live-cycle-20261011.json). Đây là kiểm chứng luồng, chưa xác nhận accuracy trên tập nhãn độc lập.

Dashboard đã nạp bản sửa; worker `--serve --poll-seconds 15` được bật lại theo quyền chạy liên tục. Sau pilot còn 406 đầu vào chờ; worker tiếp tục xử lý, không tuyên bố hoàn thành toàn bộ 416. [Snapshot triển khai](../../reports/filter-policy-v3-deployment-20261011.json), [cycle gần nhất](../../reports/filter-policy-v3-worker-latest.json). Log: `reports/filter-policy-v3-worker.out.log` và `.err.log`; dashboard dùng `reports/filter-policy-v3-dashboard.out.log` / `.err.log`. Lịch giữ 05:00–08:30 / 17:00–18:30, chu kỳ 45 phút. Chưa tự khởi động cùng Windows.

**Kết quả cuối:** lượt v3 đã hết hàng chờ. Một case cuối không qua validator do ngoại lệ OCR context coi nhắc bảng giá là thương mại độc lập; siết ngoại lệ về offer rõ hoặc quảng cáo, không áp cho câu hỏi giá. `independent-commercial-context-v3.1` chỉ đổi binding của một đầu vào này, giữ 2.673 DONE khác. Pilot riêng 1/1 được chấp nhận, HTTP 200; không reset attempts/lịch sử job cũ. [Report v3.1](../../reports/filter-policy-v3-1-live-cycle-20261011.json).

Counts hiện hành sau hoàn tất: 2.674 DONE, 184 FILTER_DROP, 111 MISSING_TEXT; không có PENDING/RUNNING/FAILED. Trong DONE: KEEP 13, REVIEW 423, DROP 2.238. FILTER_DROP cuối là 184 so với snapshot đối soát ban đầu 188; bản sửa cuối đã xét OCR target đã lưu ngay cả khi caption thương mại. Không dùng chênh lệch counts để suy ra chất lượng phân loại. [Kết quả và đối chiếu lịch sử](../../reports/filter-policy-v3-final-results-20261011.json). Worker ACTIVE, scheduler `worker_alive=true`, stderr cả hai rỗng. Lượt không có đầu vào mới tái sử dụng 2.674 DONE, `NO_PENDING_JOBS`, `api_calls=0`. `job_counts` gồm job lịch sử, không dùng số FAILED/PENDING lịch sử để báo lỗi hàng chờ hiện hành.

[Kiểm tra integrity](../../reports/filter-policy-v3-integrity-20261011.json): 2.969 node, tất cả analyses cũ/reviews/review history giữ nguyên; FK violations = 0, quick_check = ok.

## Acceptance và kiểm chứng

| Trường hợp | Expected | Kiểm chứng |
| --- | --- | --- |
| Tuyển công nhân, không phải trung gian | DROP / RECRUITMENT | Offline |
| Bán vé, không phải xếp hàng; bán điện thoại; inbox mua vé | DROP thương mại | Offline |
| Quảng cáo hứa không xếp hàng nhưng tác giả chờ lâu/không vào được | REVIEW trước Gemini | Offline |
| Nợ lương, trao đổi ca làm, nghi lừa đảo | Không tự DROP vay nợ/đổi hàng | Offline |
| OCR cha chưa chắc chắn + quảng cáo độc lập ở target | Model được DROP, không dùng context OCR làm evidence | Validator offline |
| OCR target chưa chắc chắn hoặc comment phụ thuộc cha | Không DROP, bắt buộc review | Validator offline |
| Rule mới | Chỉ invalidation thương mại/OCR, giữ hash không chịu ảnh hưởng | Offline + đối soát thật |
| Lý do loại | Đọc được trên bảng/mobile, phân biệt Bộ lọc/Model | Chromium fixture |
| SQLite writer đang giữ khóa | pending_run đọc được; scheduler sống qua SQLITE_BUSY | Offline |
| Gemini hàng chờ thật | JSON/evidence hợp lệ, lưu từng result | Pilot 10/10 |

Contract cuối: 229 tests, 228 đạt và một test OCR engine thật bỏ qua theo opt-in. Gồm scheduler/SQLite, caption bán hàng + OCR phản ánh, câu hỏi bảng giá và binding v3.1 chỉ đổi đúng scope. Chromium: 5/5 đạt trên SQLite fixture, gồm bộ lọc/xóa lọc/export và desktop/mobile. Ảnh trước/sau nằm dưới `reports/filter-policy-v3-{before,after}-{desktop,mobile}.png`.

Detector UI cảnh báo rule border-left cũ; rule này đã được override thành border 1px trong CSS hiện hữu. Đã đối chiếu ảnh desktop/mobile, không mở rộng scope thiết kế.

## Giới hạn

REVIEW là kết luận cần đánh giá, không đồng nghĩa job chưa phân loại. MISSING_TEXT không phải DROP. Pattern chưa bao phủ mọi cách viết và caption thiếu; chưa đo precision/recall trên 416 đầu vào. Các invalid output trong lượt liên tục vẫn bị từ chối/retry theo worker, không nới schema để lấy completion.

Khi thay chính sách tiếp theo, tăng `POLICY_VERSION` và mở rộng predicate đầu vào bị ảnh hưởng theo scope; test, đối soát trước API. Không xóa jobs/analyses cũ để ép rerun. Làm mới dữ liệu trên giao diện để đọc snapshot mới.
