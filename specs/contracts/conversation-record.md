# Conversation record v2: raw content, thời gian và thread

**Đồng bộ 11/10/2026 — core IMPLEMENTED, full acceptance pending:** nodes/revisions/observations/reviews/checkpoints/outbox, source tasks/leases/inventory, scan threads, classification consumer và workspace đã có runtime. Xem [raw dashboard](../../docs/operations/dashboard-raw-v2.md), [worker](../../docs/operations/classification-worker.md), [workspace](../../docs/operations/dashboard-workspace.md) và [trạng thái hiện hành](../../docs/current-state.md). Pilot/backfill có comments/replies nhưng coverage vẫn PARTIAL; full target contract dưới đây không tự là danh sách mọi acceptance đã đạt.

Contract thiết kế ngày 09/10/2026; core đã triển khai, toàn bộ GT acceptance chưa hoàn tất. Scope: [Facebook group tracing](../features/facebook-group-tracing.md), requirements GT-001–008. Dữ liệu post v1 giữ compatibility qua mapping; raw v2/migration có schema riêng, không rename semantics âm thầm.

**Mở rộng Threads PLANNED:** [contract đa nền tảng](multi-platform-conversations.md) đề xuất reader v2/v3, platform-scoped identity và storage queue. `ContentNode`/native aliases hiện vẫn chỉ nhận Facebook; contract đề xuất không thay đổi trạng thái runtime của bảng dưới đây.

## 1. Content node

Một node là một bài, một comment hoặc một reply. UID tác giả, native ID nội dung và registry ID nguồn là ba định danh khác nhau.

| Field | Type / rule |
| --- | --- |
| schema_version | Literal `conversation-record-v2` |
| node_id | Stable internal ID |
| platform | `FACEBOOK` trong increment đầu |
| node_type | `POST`, `COMMENT`, `REPLY` |
| platform_item_id | Native ID của node; nullable khi không lấy được |
| root_post_id | Internal ID bài gốc; POST tự tham chiếu |
| parent_node_id | POST: null; COMMENT: bài; REPLY: comment/reply cha nếu biết |
| relationship_status | `RESOLVED`, `PARTIAL`, `UNRESOLVED`; cha chưa đọc tạo reference stub, không invent text |
| canonical_url | Link node đã xác minh nếu có; nullable |
| display_url / url_type | URL dùng mở UI; `DIRECT` hoặc `PARENT_FALLBACK`; fallback không làm identity comment |
| author_uid / author_name / author_url | Nullable; UID chỉ native tác giả thật, tên có thể ẩn danh; không suy UID từ tên |
| raw_text | Text riêng node đọc được; null nếu chưa đọc, empty string chỉ khi xác minh không có text |
| media_refs | References của node; không nhầm ảnh/avatar của cha/người khác |
| engagement | Nullable count từng loại; unknown khác 0 |
| published_at | UTC instant khi xác định được; không thay bằng discovered_at |
| publication_precision | `INSTANT`, `APPROXIMATE`, `DATE_ONLY`, `UNKNOWN` |
| published_date_local / timestamp_raw / timestamp_basis | Ngày địa phương khi chỉ có ngày, chuỗi UI gốc và cách xác định |
| edited_at | UTC nullable; chỉ ghi khi có evidence thời gian sửa |
| first_seen_at / last_seen_at | UTC quan sát đầu/cuối, không phải ngày xuất bản |
| extraction_status / missing_fields | `COMPLETE`, `PARTIAL`, `FAILED`, `REFERENCE_ONLY`; danh sách trường/lý do thiếu |
| availability_status | `AVAILABLE`, `UNAVAILABLE`, `DELETED_CONFIRMED`, `UNKNOWN`; không gán deleted chỉ vì login lỗi |

Identity: platform + native node ID (kèm kind khi namespace yêu cầu). Fallback chỉ dùng canonical URL riêng node đã xác minh. Comment chỉ có parent URL và không có native ID phải là provisional node có observation key/locator; không gộp mọi comment thành parent, không dùng hash text rỗng hoặc author UID làm identity. Reconciliation phải có evidence, ghi alias history; nếu chưa chắc thì giữ unresolved, không giả định đã dedup hoàn toàn.

Source không nằm duy nhất trong node: bảng `node_sources(node_id, source_id, source_url, group_reference, first_seen_at)` cho nhiều occurrences. Một nội dung được phát hiện qua nhiều run/query không tạo nhiều node. Group của comment dựa thread/source xác minh, không dựa từ khóa caption.

## 2. Raw revisions và observations

- `content_revisions`: revision_id, node_id, raw_text, media_refs, content_hash, observed_at, extraction_status, parser_version. Hash hỗ trợ phát hiện thay đổi trên **cùng identity**, không gộp những node khác nhau có cùng text. Không có timestamp sửa thật thì chỉ ghi thời điểm thấy revision.
- `observations`: observation_id, node_id, revision_id, source_id, crawl_run_id, query_id/query_type nếu có, discovered_via, discovered_at, collected_at, browser/parser version, evidence locator và access mode. Repeated observations được giữ theo policy bền vững, không tạo canonical duplicate.
- `node_reviews`: node_id, review_status, notes, project_override, actor/timestamp/history. Rerun/reanalysis giữ review. Review của post không tự áp cho comments.

Raw tồn tại độc lập với relevance. Analysis DROP không delete raw/revisions/review. Retention/admin delete là thao tác riêng và audit rõ; không chạy purge v1 trên tables v2. Credentials/cookies/tokens không được ghi vào bất kỳ record/log/export nào.

## 3. Analysis riêng, có version

`node_analyses`: analysis_id, node_id, revision_id, rule_version, taxonomy_version, model_version nullable, analyzed_at, relevance `KEEP|DROP|REVIEW`, intent_labels, issue/domain/subcategory, project matches/context, evidence spans + origin_node_id, explanation và confidence nullable. Không suy business confidence từ acquisition completeness.

Chọn latest analysis tương ứng revision hiện tại; analysis cũ vẫn truy vết được. Node chưa phân loại có processing state `UNCLASSIFIED`, không ngầm là KEEP. Context group chỉ là project hint; context post không tự biến mọi comment thành khiếu nại. Nội dung parent quảng cáo/tuyển dụng có thể DROP trong view phản ánh nhưng child complaint KEEP. Reprocess chạy trên raw đã lưu; không cần phát hiện lại và không overwrite review.

## 4. Time window

Window chuẩn `[start_utc, end_utc)`, UI chuyển từ `Asia/Saigon` và ghi timezone. Chọn ngày 08/10/2026 trọn ngày tương ứng `2026-10-07T17:00:00Z` đến trước `2026-10-08T17:00:00Z`.

- Mặc định xét published_at của **node đang lọc**. Parent ngoài window được lấy làm context, không được tính thêm vào số nội dung trong window.
- `INSTANT`: xác định IN_WINDOW/OUT_OF_WINDOW từ timestamp.
- `DATE_ONLY`: có thể khớp ngày địa phương trong view ngày, nhưng đánh dấu `DAY_MATCH_ONLY`; không khẳng định nằm trong khoảng giờ cụ thể. Chỉ count riêng cùng độ chính xác.
- `APPROXIMATE`: lưu uncertainty interval nếu xác định được; đánh dấu `UNCERTAIN` nếu chạm biên window. Không invent instant từ “1 ngày trước”.
- `UNKNOWN`: `UNRESOLVED`; mục cần xác minh riêng. Không dùng collected_at/first_seen_at làm published_at.
- Lựa chọn filter “ngày thu thập/ngày phát hiện” phải là time basis explicit. Không trộn với báo cáo ngày phản ánh phát sinh.

## 5. Runs, inventory, scan và coverage

| Entity | Fields tối thiểu |
| --- | --- |
| crawl_runs | run_id, mode, requested_window, timezone, selected_sources/projects, config_version, start/end, status, budgets, stop_reason |
| group_post_inventory | source_id, root_post_id, first_seen/last_seen, last_comment_scan_at, priority/next_scan_at, inventory origin |
| scan_tasks | task_id, source_id, root_post_id nullable, task_type INVENTORY/POST/COMMENTS/REPLIES, status, lease, retry_count |
| checkpoints | task_id, checkpoint_version, verified cursor/locator or rescan anchor, last_committed_batch, updated_at; DOM locator không bảo đảm còn hợp lệ sau restart |
| scan_coverage | task_id, started/finished_at, scope, pagination status, UI sort, observed counts, UI total nullable, status, stop_reason, unresolved items |

Run statuses: `QUEUED`, `RUNNING`, `PARTIAL`, `COMPLETED_OBSERVED`, `BLOCKED`, `FAILED`, `CANCELLED`. Coverage statuses theo feature. Trạng thái hoàn tất run chỉ khi mọi scope dự kiến có coverage hoàn tất quan sát được; partial inventory không được nâng thành toàn bộ group.

Commit raw/observations cùng checkpoint của batch trong transaction; crash không tiến checkpoint qua dữ liệu chưa commit. Cursor hết hạn thì rescan overlap/dedup, không skip phần không biết. Retry có giới hạn trong budget và nguồn khác không bị chặn. Profile lock một job/profile; lease tasks tránh hai workers quét cùng scope.

## 6. API và export mapping dự kiến

- GET nodes/library: filters nguồn/dự án/window/time_basis/type/relevance/precision; pagination/counts dựa node, không dựa run. Response có coverage summary và unresolved-time count.
- GET thread/{root_post_id}: parent context, children/replies và relation/extraction/coverage; phân trang thread không cắt mất relationship.
- Start/continue run: source scope, window, mode và budget snapshot; không bắt buộc query keyword cho group tracing.
- Reprocess/review: node IDs + rule version hoặc review fields; giữ raw.
- Export UID→author_uid, Tên→author_name, Date→node publication time/precision, Comment→raw_text, URL→display_url với url_type; bổ sung node/root/parent IDs để nối thread. Không xuất UID tác giả thay cho content ID.

## 7. Migration và acceptance

Backup trước migration, mapping canonical v1 record thành POST với references/observations/reviews giữ nguyên; v1 timestamp unknown vẫn unknown. Legacy post-only output được projection qua adapter, không giả comments. Exclusion aliases v1 giữ provenance nhưng không chặn raw tracing v2. Không phục hồi được raw đã purge bằng schema migration.

Validation/ACP: GT-AC01–14 ở [feature](../features/facebook-group-tracing.md). Cần fixtures, migration/rollback và pilot thật; tài liệu này chưa có kết quả kiểm thử runtime.
