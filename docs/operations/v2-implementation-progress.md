# Triển khai workflow v2 — 09/10/2026

> **Snapshot lịch sử theo ngày trong tài liệu.** Các trạng thái “chưa triển khai”, disabled hoặc lỗi probe chỉ áp dụng cho lượt kiểm tra đó. Đối chiếu code/config hiện hành ngày 11/10/2026 tại [trạng thái dự án](../current-state.md); không dùng snapshot này để kết luận runtime hiện tại.

**Kiểm tra bổ sung:** [audit parser/schema Facebook](facebook-schema-audit.md) xác định permalink pilot hiển thị “Bạn hiện không xem được nội dung này”; sau sửa access detector trả `CONTENT_UNAVAILABLE`. Parser giữ caption khi thiếu timestamp đúng schema. Regression mới nhất 166 contract + 9 Chromium fixture tests pass; chưa nghiệm thu native caption/comments.

## Đầu vào, mục tiêu và output nghiệm thu

| Phần | Đầu vào | Mục tiêu | Output nghiệm thu |
| --- | --- | --- | --- |
| P1: kho raw | SQLite v1, source registry, conversation contract | Lưu POST/COMMENT/REPLY trước filter; giữ identity, revisions, observations, review | Models/store/migration; backup/restore trên copy; invariant tests; report P1 |
| P2: threads và lịch | Group đã duyệt, permalink/inventory, window UTC, profile Facebook | Quét comment/reply theo thời gian riêng; quét lại bài cũ; durable ticks | Parser, thread/inventory worker, SQLite tasks/checkpoints; offline tests; kết quả native Facebook ghi riêng |
| P3: filter và context | Raw đã commit, taxonomy v1, source occurrence | Filter từng node; không dùng DROP của cha để loại con; dẫn chứng có revision | Request đúng schema; filter audit; target/root/parent context; input tests |
| P4 increment: jobs/batching | Request đã kiểm tra, taxonomy/model/prompt binding | Chống job trùng; giữ valid partial; retry bounded; oversized rõ | SQLite jobs/analyses, byte-bound batches, fake-provider tests; chưa có adapter Gemini thật |

Các module v2 có CLI riêng; dashboard và scheduler v1 chưa được chuyển sang v2. Không dùng kết quả crawl v1 để nghiệm thu raw-first/comments.

## Kết quả đã kiểm chứng

- P1: 15 tests riêng; migration/restore trên bản sao production giữ 24 records, 289 observations, 2 reviews và 2 review-history entries. Dữ liệu production không bị ghi đè. Xem [report P1](../../reports/p1-raw-storage-validation.json).
- Comment/reply parser: 5 contract tests và 2 tests Chromium DOM mô phỏng. Thời gian của comment độc lập với bài cha; native ID không bị gộp theo text rỗng.
- Lịch/task: 6 tests fake clock, final ticks, catch-up, lease/restart, profile-busy retry và quét luân phiên inventory. Khung ngày giờ VN: 05:00–08:30 và 17:00–18:30, interval 45 phút, thêm lượt chốt.
- Input/batching: 5 tests; jobs/validation: 6 tests với fake provider. Đây không phải kết quả của Gemini hoặc số đo độ chính xác model.
- Regression cuối: **164 contract tests PASS**; CLI help/import chạy được. [Báo cáo tổng](../../reports/v2-implementation-validation.json).
- Native Facebook pilot: `EXTRACTION_FAILED / LISTING_SELECTOR_MISMATCH` trên một permalink VinCons; lưu được một reference node, chưa đọc được nội dung/comment. Diagnostic thấy 88 JSON scripts nhưng không có article, Story hợp lệ hoặc comment link trong DOM quan sát. Chưa kết luận nguyên nhân là đăng nhập hay bài không khả dụng. [Pilot](../../reports/p2-thread-live-pilot.json), [diagnostic](../../reports/p2-browser-diagnostic.json).

## Lệnh chạy đã có

Chạy tại thư mục gốc repo bằng `.venv\audit\Scripts\python.exe`. DB dưới đây là DB pilot riêng.

```powershell
# Xem raw đã lưu; không gọi mạng
.\.venv\audit\Scripts\python.exe -m engine.conversation_cli --db sessions/pilot/v2/p2-live.sqlite3 list

# Quét một bài thuộc group đã duyệt, kể cả bài cha cũ ngoài window
.\.venv\audit\Scripts\python.exe -m engine.conversation_cli --db sessions/pilot/v2/p2-live.sqlite3 scan-thread --source-id fb_group_139108668844789 --post-url https://www.facebook.com/groups/139108668844789/posts/987006180721696 --start 2026-10-08T00:00:00+07:00 --end 2026-10-09T00:00:00+07:00

# Đưa các tick đã đến hạn của ngày vào hàng chờ; chạy lại không nhân task
.\.venv\audit\Scripts\python.exe -m engine.conversation_cli --db sessions/pilot/v2/p2-live.sqlite3 enqueue-days --source-id fb_group_139108668844789 --first-day 2026-10-09 --last-day 2026-10-09

# Xử lý một task; browser vẫn dùng khóa profile hiện có
.\.venv\audit\Scripts\python.exe -m engine.conversation_cli --db sessions/pilot/v2/p2-live.sqlite3 work-once --seconds 1200 --max-threads 20

# Chạy service mỗi ngày trong terminal; Ctrl+C dừng, queue/checkpoints được giữ
.\.venv\audit\Scripts\python.exe -m engine.conversation_cli --db sessions/pilot/v2/p2-live.sqlite3 serve --source-id fb_group_139108668844789 --first-day 2026-10-09

# Filter raw, tạo file batch và jobs; chưa gửi API
.\.venv\audit\Scripts\python.exe -m engine.conversation_cli --db sessions/pilot/v2/p2-live.sqlite3 prepare-classification --model ag/gemini-3.7-flash-low --output sessions/pilot/v2/classification-input.json
```

`serve` gọi lại enqueue theo giờ hiện tại và xử lý queue tuần tự khi terminal còn chạy; khi restart dùng cùng DB/first-day để catch-up. Chưa đăng ký tự khởi động với Windows. `work-once` giữ outcome lỗi/partial, không báo đã thu đủ. Lượt mở khung giờ chỉ cập nhật inventory; các lượt sau dùng `[slot_start, tick)`.

## Giới hạn và việc còn lại

1. Sửa/kiểm chứng native Facebook permalink/comment parsing trên nguồn truy cập được, có manifest đối chiếu. Pilot hiện chưa đạt LIVE-01/02/03; không thể xác nhận thu hết dữ liệu trong window.
2. Inventory chỉ chứa bài browser đã thấy và quét luân phiên; chưa có backfill đầy đủ lịch sử group, rescan URL thay cho cursor pagination được xác minh. Coverage luôn partial/unknown.
3. Service CLI đã có, chưa bật chạy nền hay tích hợp UI v2; cần test worker/source isolation, lịch thật hai ngày và restart. Nếu profile bận ở discovery/thread, task được trả về pending với cooldown; chưa kiểm thử live trường hợp này.
4. Context builder hiện dùng alias seed của hai dự án. Cần chuyển sang project resolver/config mở rộng trước thêm dự án mới.
5. Byte-bound batching chỉ là giới hạn pilot thận trọng, chưa xác minh context/output capacity của gateway. Oversized không cắt raw; cần review/reprocess riêng.
6. Jobs có lease/idempotency/validated partial storage; chưa có dispatcher outbox tự động, backoff dịch vụ, Gemini adapter/capability probe. Runtime taxonomy vẫn draft/disabled; chưa gửi API.
7. P5/P6: API/UI table/thread/review/Excel v2 và native end-to-end/held-out quality chưa triển khai/nghiệm thu. Dữ liệu v2 chưa tự xuất hiện trong kho giao diện v1.

Ưu tiên tiếp theo là P2 native extraction + service, sau đó adapter Gemini và giao diện v2. Không ghi ACP hoàn thành khi những gate này chưa đạt.
