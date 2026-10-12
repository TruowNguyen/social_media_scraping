# Discovery Queue v1

Ngày: **08/10/2026**. Contract `discovery-queue-contract-v1`. Đã có SQLite queue/history, review CLI và gated dispatch, kiểm chứng offline theo [implementation report](../../docs/acquisition-implementation.md); chưa live acceptance/ACP. Queue dành cho link/nguồn do Google tìm thấy nhưng chưa đủ điều kiện lấy content theo [Source Registry](source-registry.md).

Liên quan FR-01/04/05/06/12/16/17. Candidate fields/identity ở [Source Adapter](source-adapter.md); metadata retention ở [Exclusion](exclusion-rules.md).

## 1. Scope và invariants

- Google tìm Facebook/TikTok/YouTube. Registry approval của Google query chỉ cho phép search, không cấp approval cho mọi nguồn trong kết quả.
- Link bài ngoài nguồn đã duyệt được queue; link container được queue như đề xuất nguồn. Google snippet không chứng minh membership, public access, author/channel identity hoặc relevance.
- TikTok browser keyword/hashtag search là scope query đã duyệt riêng: video public từ search không đòi creator phải có account watchlist. Quyền này không tự áp dụng cho Google-discovered creator/video.
- Nguồn đích đã duyệt phải tồn tại, enabled, VERIFIED, access_verified, public, login state xác định, adapter hỗ trợ và ở watchlist của run. Name confirmation không đủ.
- Approval queue không tự enable source, thêm vào watchlist hoặc fetch content. Nguồn mới đăng ký draft/disabled; operator kiểm chứng và bật riêng.
- Bài thương mại rõ intent được prefilter DROP trước queue: không lưu snippet/title/raw hoặc media trong queue. Tên container chứa “tuyển dụng” không là post intent, không bị DROP theo tên.

## 2. Queue entry và identity

| Field | Type / rule |
| --- | --- |
| `schema_version` | `discovery-queue-entry-v1` |
| `discovery_id` | Stable queue entry ID |
| `entry_kind` | `CONTENT_ITEM` hoặc `SOURCE_CONTAINER` |
| `platform`, `source_url`, `canonical_url`, `platform_item_id` | Target platform/identity như candidate contract; native ID nullable |
| `proposed_source_type` | Nullable `FACEBOOK_GROUP`, `TIKTOK_ACCOUNT`, `TIKTOK_SEARCH`, `YOUTUBE_CHANNEL`; hashtag container có thể đề xuất query scope, chưa có identity không đoán |
| `origin_source_ref` | Nullable group/profile/channel stable reference; FB slug giữ string |
| `title`, `search_snippet` | Nullable Google evidence; được lưu sau prefilter, không full text bài |
| `source_id`, `query_id`, `crawl_run_id` | Acquisition source/query/run từ Google; thêm observations cho các lần tìm thấy |
| `status` | `PENDING`, `APPROVED`, `REJECTED` |
| `reason` | `UNAPPROVED_SOURCE`, `UNKNOWN_ORIGIN_SOURCE`, `SOURCE_NOT_READY`, `UNSUPPORTED_SOURCE_TYPE` hoặc `CONTAINER_DISCOVERY` |
| `first_seen_at`, `last_seen_at` | UTC timestamps; giữ first seen khi gặp lại |
| `approved_source_id` | Nullable registry target ID sau khi bind/register; không thay acquisition source_id |
| `reviewed_by`, `reviewed_at`, `review_note` | Nullable trước review; reviewer/time bắt buộc cho APPROVED/REJECTED |
| `dispatch_state` | `NOT_READY`, `READY`, `FETCHED`, `FAILED`, `OUT_OF_WINDOW`; riêng với review status |

Queue unique theo platform + entry kind + native item ID, fallback canonical URL. Container dedup theo verified origin reference/URL. Khi URL fallback sau này resolve native ID, merge alias/observations; giữ review history, không tạo pending copy mới. Không merge chỉ theo title/snippet/near-text.

## 3. Review và transitions

| Transition | Điều kiện / kết quả |
| --- | --- |
| New → PENDING | Eligible discovery ngoài source gate; lưu Google evidence và lineage |
| PENDING → APPROVED | Reviewer xác định/bind nguồn đích hoặc đăng ký draft source; reviewer/time/note ghi audit; dispatch vẫn NOT_READY nếu chưa đủ gate |
| PENDING → REJECTED | Reviewer ghi lý do; không fetch item hoặc enable source |
| APPROVED → READY | Registry gate + supported adapter + watchlist scope đầy đủ; runtime đánh giá, không reviewer tự gán READY |
| READY → FETCHED/FAILED/OUT_OF_WINDOW | Operator gọi bounded processing/rerun với current window; dedup và source outcomes theo adapter contract |

Review không sửa trực tiếp kết quả model hoặc `KEEP/DROP/REVIEW` nghiệp vụ. Queue approval là quyết định scope acquisition. REJECTED không tự quay về PENDING khi Google tìm lại; chỉ cập nhật last_seen/observation. Reviewer có thể reopen explicit về PENDING và lưu lịch sử; không âm thầm overwrite quyết định cũ.

Với content item chưa xác định nguồn, reviewer phải xác định nguồn đích trước khi APPROVED. Không auto mở bài để tìm full text bên ngoài gate. Có thể dùng link container/identity metadata tối thiểu trong tác vụ verification operator yêu cầu; không gọi media/LLM. YouTube video chưa biết channel nằm PENDING/UNKNOWN_ORIGIN_SOURCE.

Không auto fetch khi duyệt. Sau source ready, CLI xử lý entry đã duyệt hoặc rerun Google/source theo window mới; bài cũ không tự được tính fresh. Container APPROVED chỉ tạo/bind registry proposal, không trở thành content record và không mở toàn bộ group/account trong cùng Google job.

Interface CLI dự kiến: `discoveries list` lọc status/platform/run; `discoveries approve <id> --source-id ... --reviewer ...`; `discoveries reject <id> --reviewer ... --note ...`; `discoveries reopen <id> --reviewer ... --note ...`; `discoveries process <id> --start ... --end ...`. Đây là command contract cho implementation sau, chưa có executable.

## 4. Persistence, duplicates và dispatch

- SQLite queue/observations/review history trong SmartCity storage riêng; không dùng legacy dedup DB làm queue và không dùng Excel làm source of truth.
- Approve vào source mới phải có stable source ID và draft record: enabled=false, verification_status=PENDING_VERIFICATION, access_verified=false, access_type=UNKNOWN, requires_login=null nếu chưa kiểm chứng. “Draft” là semantics, không thêm `verification_status=DRAFT` vào enum hiện tại.
- Batch approval chỉ bind vào nguồn đúng platform/identity. Facebook Page/profile phát hiện được giữ pending với UNSUPPORTED_SOURCE_TYPE; không bind vào FACEBOOK_GROUP để vượt gate.
- Nếu content đã được thu trước đó qua approved acquisition, Google observation có thể attach vào record đó sau prefilter mà không fetch lại; không dùng sự tồn tại record để approve creator hoặc group mới.
- Queue dùng upsert item/observations; processing rerun và crash recovery không tạo content duplicate. Source không còn ready phải dừng dispatch và giữ entry, không mất approval history.
- Khi prefilter được áp lại và intent trở thành clear DROP, loại raw snippet/content khỏi retained payload theo rule; chỉ rejection audit được lưu. Queue rejected bởi scope khác với prefilter DROP intent.
- Kết quả queue list/export không chứa credential/session; logs chỉ IDs/reason/counters, không dump toàn response hoặc snippet mặc định.

## 5. Acceptance / traceability

Tất cả acceptance **PLANNED**; chưa có behavioral/live evidence.

| Case ID | Input/scenario | Expected | PRD |
| --- | --- | --- | --- |
| DQ-AC-01 | Google tìm bài ngoài registry | PENDING; snippet có provenance; zero full fetch/media/LLM | FR-01/04 |
| DQ-AC-02 | Duyệt bài và tạo nguồn mới | Source draft/disabled; queue APPROVED nhưng NOT_READY | FR-01 |
| DQ-AC-03 | Source đã ready và trong watchlist; process explicit | Dispatch đúng adapter/window, giữ Google lineage | FR-04/17 |
| DQ-AC-04 | Nguồn disabled/unverified, hết login hoặc unsupported | Không fetch; queue giữ history/reason | FR-01/16 |
| DQ-AC-05 | Hai query/URL alias tìm lại cùng item | Một entry, nhiều observations; first_seen giữ nguyên | FR-05/12 |
| DQ-AC-06 | REJECTED được search lại; reopen explicit | Không tự pending; reopen có reviewer/time/note | FR-01/16 |
| DQ-AC-07 | YouTube watch URL không biết channel | UNKNOWN_ORIGIN_SOURCE; không đoán channel từ snippet | FR-01/04 |
| DQ-AC-08 | Link group/profile/channel thay link bài | SOURCE_CONTAINER; không tạo content record | FR-04/12 |
| DQ-AC-09 | Google snippet là tuyển dụng rõ / container tên tuyển dụng | Bài DROP không queue raw; container không bị loại theo tên | FR-06 |
| DQ-AC-10 | Source verified nhưng item ngoài current window | OUT_OF_WINDOW; không tính fresh chỉ vì approved | FR-04/17 |
| DQ-AC-11 | Google tìm lại item đã có từ TikTok search | Attach observation, không refetch/auto approve creator | FR-05/12 |
| DQ-AC-12 | Crash sau approval hoặc persist content | Rerun giữ review history, không duplicate item | FR-05/17 |

Điều kiện gate khi triển khai: tests phải quan sát không có full-fetch call trước readiness; reviewer history và source state thực trong storage. Mock pass chỉ được ghi OFFLINE_VERIFIED; khả năng truy cập nền tảng cần evidence live riêng.
