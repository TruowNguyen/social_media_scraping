# Contract mở rộng conversation đa nền tảng

**IMPLEMENTED_SUBSET / OFFLINE_VERIFIED / LIVE_PARTIAL · 12/10/2026**. [Threads adapter](../features/threads-adapter.md) đã ghi raw v3 cùng Facebook v2; IDs/reviews cũ giữ nguyên. [Runbook](../../docs/operations/threads-acquisition.md) ghi boundaries: Facebook chưa dùng spool, nested mapping chưa verified, chưa daemon storage riêng. Contract Facebook [v2](conversation-record.md) vẫn mô tả payload baseline.

## 1. Version và compatibility

- Đề xuất envelope mới `conversation-record-v3` cho node Threads và các revision mới sau khi producer hỗ trợ. Reader mới chấp nhận v2 Facebook + v3; projection chuẩn hóa dùng v3. Không đổi nguyên payload/history v2 để chỉ rename version.
- SQLite migration có migration ID và backup; additive columns/tables khi cần. Hàng Facebook hiện tại giữ node IDs, identity aliases, revision IDs, observation IDs, reviews và analysis provenance. Existing classifier input/job hashes không đổi chỉ vì thêm platform; fingerprint chỉ đổi khi evidence/phạm vi thực sự đổi.
- Chỉ bật Threads sau khi mọi consumer đã đọc được v3. Old binary v2 không được chạy trên DB mixed platforms; rollback producer flag khác rollback database.
- Runtime v2 metadata vẫn đúng với rows cũ; ghi capability/schema support riêng trong metadata migration, không âm thầm đổi `conversation_meta` khiến lịch sử trở thành v3.

## 2. Identity và relationships

`platform` enum mới: `FACEBOOK|THREADS`. Author UID, native item ID, shortcode và internal node ID là các trường khác nhau, đều dùng string.

| Nền tảng | Namespace native identity | Mapping node type |
| --- | --- | --- |
| Facebook | Giữ `FACEBOOK:POST:native:<id>` và `FACEBOOK:COMMENT:native:<id>` | POST hoặc COMMENT/REPLY theo relationship; comments/replies chia sẻ native namespace hiện tại |
| Threads | Đề xuất `THREADS:MEDIA:native:<id>` | Root post → POST; trả lời trực tiếp → COMMENT; trả lời comment/reply → REPLY khi parent được xác minh |

Namespace Threads dùng MEDIA vì post/reply là media objects; không tạo identity thứ hai chỉ vì parser phát hiện sâu hơn trong hội thoại. Node type không thay thế platform-scoped identity. Nếu chưa biết cấp parent, relationship PARTIAL/UNRESOLVED, không tự coi direct reply; reconciliation type/parent phải có evidence và history.

- Fallback identity gồm platform + canonical permalink đã xác minh; provisional có platform-scoped observation key khi thiếu cả ID và permalink. Không dedup theo text rỗng, tên/UID tác giả hoặc URL bài cha.
- Permalink shortcode là URL reference, không tự là API media ID. Alias numeric ID ↔ shortcode/URL chỉ gắn khi cùng provider object hoặc evidence verified; không suy từ hình thức chuỗi.
- Normalization Threads chỉ allowlist domain/permalink/profile được xác minh; `threads.net`/`threads.com` là aliases **cần pilot**, không đổi host tùy tiện trước xác minh. Loại tracking nhưng giữ thành phần identity và reject URL ngoài allowlist.
- Quote/repost không tự là COMMENT/REPLY; lưu node POST nếu có own native ID, relation `QUOTES|REPOSTS` riêng. Không gộp bài cross-post Facebook–Threads bằng text hash; có thể liên kết evidence về sau nhưng giữ hai raw identities.
- Parent/root cùng platform; references thiếu text là stubs có trạng thái rõ. FK/validator cấm self/cycle sai và ghép reply vào parent khác platform.

## 3. Raw, observations và scope

Các fields text/author/media/engagement/published_at/precision/extraction/missing/availability giữ semantics v2. Thêm provider-neutral optional metadata: `platform_shortcode`, `platform_topic_tags`, `link_relations`, parser/provider version. Tên hiển thị/tác giả không lấy được giữ null; metric không lấy được null, không invent 0. Tags là actual observed tags, không tự thêm từ query.

Observation bắt buộc run/task/source/query ID+version, original/effective query, requested project scope, `discovered_via`, `provider_method`, observed/collected time, evidence provenance và window. Post/reply có nhiều source/query/run observations; lineage không chỉ lưu query cuối.

`source_id` của search là registry `THREADS_SEARCH`; author/profile khác source scope và group reference=null. Source query permission cho phép các kết quả trả về trong scope đã duyệt, không tự đăng ký giám sát toàn profile. Project scope query là hint, tách `CONTENT_EXPLICIT`, `PARENT_CONTEXT`, `QUERY_CONTEXT`, `UNRESOLVED`. Classifier contract mới phải version/validate `QUERY_CONTEXT` trước sử dụng; không nhét query hint vào GROUP_CONTEXT.

Ngày lọc theo node publication hoặc observed basis explicit. Parent cũ chỉ context; không count vào window reply. Raw content bất kể intent được giữ; sửa caption tạo revision, repeated observation không overwrite review hoặc tự duplicate nội dung. Payload append-only histories; không “last query wins”.

## 4. Durable storage và cùng ghi SQLite

- Acquisition writers đi qua durable spool + storage worker chung. Envelope `ingest-event-v1` đề xuất: event ID, batch ID, platform, payload schema, node/reference proposals, source/query/run lineage, observed_at, checkpoint correlation và payload checksum.
- Event ID deterministic trong cùng producer task/page item; native alias/node identity bảo vệ replay với event ID mới. Batch commit gồm nodes/revisions/observations/outbox/checkpoint acknowledgement tương ứng; nếu thiếu parent, giữ unresolved task và không fabricate caption.
- ACK sau COMMIT; cursor provider chỉ checkpoint sau mọi event của page đã commit. Crash trước/sau ack replay an toàn. Crawler chỉ giữ candidate buffer và provisional identity cache; repository mới là nguồn dedup cuối cùng.
- [Thiết kế commit chi tiết](../../docs/design/threads-adapter-flow.md#5-commit-dedup-và-crash-recovery) quy định page manifest, durable event receipts và atomic checkpoint trong cùng connection với raw writes. Số “Đã lưu” ở UI chỉ lấy từ ACK sau commit, không lấy từ candidate buffer.
- SQLite WAL một writer mỗi thời điểm. Acquisition storage worker không độc quyền với classifier/review/OCR; tất cả phải giữ transaction ngắn, bounded retry khi BUSY/LOCKED, không gọi network/model trong transaction.
- Queue backpressure/pause thay vì drop. DLQ cho poison payload có reason và retry/replay workflow; cursor/source không đánh dấu completed nếu còn unresolved ingest của page.
- Consistency tests phải bao gồm outbox phát sinh đồng thời, source occurrences khác platform, crash khi FK/reference chưa đủ, pending queue khi tắt producer và review trong lúc ingest.

## 5. Outcomes, lịch và projections

Task/run/lease keys gồm platform, schedule ID, source/query version, fixed window. Lock của Facebook không chặn Threads; lỗi provider một nền tảng không disable lịch của nền tảng kia. Không dùng một global `running` boolean cho toàn acquisition.

Coverage có scopes `OBSERVED_SEARCH_RESULTS`, `KNOWN_CONVERSATIONS`, `ACCESSIBLE_REPLIES`; never `ALL_THREADS` chỉ từ search. Window unknown, parent chưa biết, pagination/budget/cursor/visibility đều ghi riêng. Conversation consumer endpoint `/api/threads/{root_id}` có thể tái sử dụng để đọc hội thoại, nhưng URL này không tự là crawler mạng xã hội Threads.

Backend filter platform, project, query/source, node type, date basis, relevance/intent/taxonomy/processing/review; catalog là nguồn enum chung cho UI và Excel. Cột Nguồn Threads hiển thị query/tác giả phù hợp, không gọi tác giả là group. Export giữ platform/native/internal ID, parent/root, URL, raw/OCR, time precision, query observations, classification/review provenance.

Các AC migration/dedup/concurrency/replay/platform filter: THR-AC05–07, THR-AC09–11 trong [plan](../../docs/implementation-plan-threads.md). Đã kiểm thử offline và ghi Threads thật vào shared DB; mức đạt và các gate còn mở ở [TODO](../../TODO.MD), không xác nhận toàn bộ ACP chỉ từ việc ingest thành công.
