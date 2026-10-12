# Đầu việc triển khai và nghiệm thu live workflow v2

**Đồng bộ 11/10/2026:** raw storage, thread tasks/rescan, Gemini worker, OCR POST và workspace đã triển khai; có limited live pilots/backfill. [Trạng thái hiện hành](current-state.md) và runbooks ghi evidence theo ngày. Parser failure của pilot ban đầu đã có [recheck](operations/facebook-root-cause-recheck.md); không dùng nó để kết luận toàn hệ thống chưa có caption/comments/Gemini/UI. Bảng LIVE-01–14 vẫn là target acceptance, chưa xác nhận toàn bộ đã pass.

Ngày 09/10/2026. Workflow: **lịch → crawl posts/comments/replies → commit raw → filter → batch LLM → validate → analysis → UI/Excel**. Đây là kế hoạch thực thi; không phải báo cáo đã test live. Ngân sách tiền API **DEFERRED_BY_USER**, không dùng làm blocker; giới hạn token/context và retry vẫn cần để request hoạt động đúng.

Liên quan: [kiến trúc](implementation-plan-v2.md), [phase gates](phased-delivery-v2.md), [schema đã implement](operations/classification-contract-v2.md), [TODO](../TODO.MD). V2 tasks dưới đây phân rã SL-T01–07, không là dự án thứ hai hoặc cộng trùng GT tasks.

## 1. Baseline đã kiểm tra và khoảng trống

Schema/validator input-output đã pass 34 tests (20 classification, 8 taxonomy, 6 architecture); taxonomy snapshot và 26 synthetic cases có sẵn. Người dùng đã chấp nhận scope taxonomy, chọn Gemini cấu hình. Không tự yêu cầu lại quyền triển khai vì YAML vẫn draft: metadata approval/runtime flag sẽ được xử lý trong task cấu hình, với provenance đúng người đã chấp nhận; không ghi mentor approval giả.

Runtime acquisition còn v1: `engine/acquisition.py` filter trước fetch/save và có purge; `src/acquisition/browser_adapters.py` lấy post, không có comment/reply acquisition. Dashboard gọi engine với 10 candidates/source, 120 giây/source, 600 giây/run: không dùng số giới hạn này để khẳng định coverage đầy đủ. Schema/validator chưa có batch worker/model call/storage analyses integration.

Vì vậy không test “đã thu đủ và classify v2” bằng nút crawl cũ. Chỉ bắt đầu pilot v2 sau P1/P2 tương ứng; tất cả kết quả live dưới đây hiện NOT_RUN. Không đổi schedule/DB chạy thật trong lượt viết kế hoạch.

## 2. WBS: đầu việc, dependencies, bàn giao và acceptance

Trạng thái DONE_OFFLINE chỉ áp đúng module đã kiểm thử, không nâng cả phase. Owner dự kiến Engineering; nghiệp vụ do người dùng/mentor review, chưa chỉ định người cụ thể.

| ID / phase | Đầu việc cụ thể | Phụ thuộc | Bàn giao / điều kiện nghiệm thu | Hiện tại |
| --- | --- | --- | --- | --- |
| V2-01 / P0 | Taxonomy definitions, project profiles và synthetic labels | Scope người dùng | 17 definitions, profiles, 26 cases, references đúng; user scope acceptance có provenance; human labels riêng | DONE_OFFLINE; human labels pending |
| V2-02 / P0 | Input/output schemas và request-bound validator | V2-01 | Unknown/stale IDs, evidence/issue sai, partial results được xử lý; 34 tests đã pass | DONE_OFFLINE |
| V2-03 / P0 | Bộ samples thật và checklist nghiệm thu | V2-01 | Manifest permalink/node, parent/child, timestamps, expected labels và reviewer; không copy dev cases vào held-out | PLANNED |
| V2-04 / P1 | Conversation models/identity/time/relationships | V2-02, conversation contract | POST/COMMENT/REPLY, root/parent, native vs author IDs, UTC/precision; null không giả 0/time | DONE_OFFLINE (P1 increment) |
| V2-05 / P1 | SQLite migration, backup và legacy projection | V2-04 | Backup nhất quán, records/notes mapping khớp; dry-run/rollback trên copy; dữ liệu purged không giả phục hồi | DONE_OFFLINE (P1 increment) |
| V2-06 / P1 | Upsert raw/revisions/observations và outbox | V2-05 | Atomic batch/checkpoint; cùng ID không nhân node; context edits invalidation; không mất enqueue sau crash | DONE_OFFLINE (P1 increment) |
| V2-07 / P1 | Tách raw retention khỏi prefilter/purge | V2-06 | Ads/recruitment raw còn; excluded aliases v1 không chặn v2; cleanup cũ không đụng tables v2 | DONE_OFFLINE (P1 increment) |
| V2-08 / P2 | Post parser và full caption | V2-06/07 | Text dài đầy đủ hoặc missing status explicit; native post/source IDs đúng, media refs không nhầm | IN_PROGRESS; offline increment, live pending |
| V2-09 / P2 | Comment/reply parser, native IDs, time/link/author | V2-08 | Open load-more/replies; không lấy parent time; direct/fallback URL rõ, anonymous/UID unknown nullable | IN_PROGRESS; offline increment, live pending |
| V2-10 / P2 | Inventory/backfill và quét bài cũ | V2-09 | Old-post/new-comment có; fair scan tuổi bài; no parent cutoff; inventory gap có coverage | IN_PROGRESS; offline increment, live pending |
| V2-11 / P2 | Durable tasks/checkpoints/coverage/source isolation | V2-10 | Resume khi timeout/crash; typed login/CAPTCHA/parser outcome, dữ liệu đã commit giữ nguyên | IN_PROGRESS; offline increment, live pending |
| V2-12 / P2 | Scheduler khung ngày, final ticks, missed-run catch-up | V2-11 | Ticks/window/restart/idempotent run key đúng; 1 job/profile; slot close không bị bỏ vì job bận | IN_PROGRESS; offline increment, live pending |
| V2-13 / P3 | Saved-raw filter và re-filter | V2-07/09 | Filter audit có rule version; mixed complaint không DROP; parent không gate child; raw không bị xóa | IN_PROGRESS; offline increment, live pending |
| V2-14 / P3 | Resolver/project registry/context builder | V2-13 | VinCons portfolio khác site; target/parent revisions; candidates/basis/evidence đúng; unresolved REVIEW | IN_PROGRESS; offline increment, live pending |
| V2-15 / P4 | Durable classification jobs/leases/idempotency | V2-06/14 | Unique revision/context/taxonomy/prompt/model key, crash/outbox repair; notes/reviews giữ | OFFLINE_VERIFIED (jobs/outbox/retry) |
| V2-16 / P4 | Token batch builder, flush và oversized handling | V2-15 | Không vượt model context/input/output; ít items vẫn flush; không silent truncation raw; count/token limits | OFFLINE_VERIFIED (batch limits; many-item live pending) |
| V2-17 / P4 | Gateway Gemini adapter và capability probe | V2-02; độc lập raw phase để feasibility | Dùng .env hiện có; protocol/model/schema khả dụng qua response thật; key không log; token limit được cấu hình/kiểm chứng | LIVE_VERIFIED (configured gateway protocol/model single item) |
| V2-18 / P4 | Validation→save analysis, partial retry/reprocess | V2-16/17 | Chỉ lưu results validated; retry missing/invalid riêng, backoff bounded; unclassified failure rõ; raw vẫn đọc được | OFFLINE_VERIFIED + single-item LIVE_VERIFIED |
| V2-19 / P5 | V2 API services/read views và status endpoints | V2-11/18 | Raw vs analysis views, node dates, counts, stale/pending/coverage; không nhồi logic vào dashboard handler | IN_PROGRESS (classification API increment) |
| V2-20 / P5 | Table/thread/review/notes và schedule UI | V2-19 | Columns đúng, context rõ, reload/rerun giữ reviews, schedule không tự đổi scope | IN_PROGRESS (classification table/filter increment) |
| V2-21 / P5 | Excel all-filter export và metadata | V2-20 | UI/DB/export IDs/counts khớp, long text không cắt, formula safety, time basis/version/coverage | PLANNED |
| V2-22 / P6 | End-to-end offline regression/failure injection | V2-04–21 | Migration, fake provider, partial/restart, old-post/comments, UI/export checks pass | PLANNED |
| V2-23 / P6 | Facebook + Gemini live pilot, 2 ngày/two slots | V2-03/22 | Live matrix bên dưới, held-out labels, raw→filter→classify evidence; không fake PASS khi thiếu samples | PLANNED |
| V2-24 / P6 | ACP report và rollout từng group | V2-23 | Người dùng/mentor xác nhận kết quả/scope/remaining gaps; backup/rollback sẵn; giữ raw | PLANNED |

**Đường triển khai chính:** V2-04→05→06→07→08→09→10→11→12→13→14→15→16→18→19→20→21→22→23→24. V2-03 và V2-17 có thể chuẩn bị trước phần khác khi đủ schema/resources; không tự chạy API probe trong lượt lập kế hoạch này. Chưa ước lượng ngày xong trước feasibility comments/gateway.

## 3. Checklist test trước khi chạy hệ thống thật

### P1: storage/migration

Tạo DB pilot dưới `sessions/pilot/v2/`; không overwrite DB production. Nếu lấy bản sao DB đang mở, dùng SQLite backup API để có snapshot nhất quán (không chỉ copy file `.sqlite3` rồi bỏ WAL). Kiểm kê records/reviews/aliases/observations trước và sau; có mapping report. Migration dry-run, rollback, rerun, edit, crash transaction đều phải pass. Data sau backup cần replay plan nếu rollback production.

### P2: crawler/scheduler

Fixture HTML phải gồm ranked comments, more-comments, nested replies, pinned post, old/new mixed, relative/date-only time, anonymous và missing caption. Fake clock kiểm thử đầy một ngày, biên giờ VN/UTC, job bận, restart, duplicate tick và profile lease. Những test này không được tự ghi LIVE_VERIFIED.

### P3/P4: filter/classifier

Chạy raw fixtures qua filter thực, context builder, token batching, fake provider và validator thực. Fake provider trả valid/missing/duplicate/unknown IDs, stale revision, invented quote, invalid JSON, output cutoff, 429/5xx/timeout. Kiểm tra raw count không giảm và valid partial result không bị gọi lại. Đo API thật riêng, không gán fake-provider result thành model accuracy.

### P5: UI/export

Server test chạy port khác dashboard đang dùng, DB pilot riêng. Browser test table/date/thread, notes persistence, refresh và export qua actual API. Reconciliation bằng node IDs và time basis, không chỉ so tổng số dòng. Kiểm tra build/package có JSON schemas, legacy CLI/import/schema không regress.

## 4. Chuẩn bị pilot live trên hệ thống

1. Chọn một group VinCons và một group Vũ Yên từ Registry đã verified/enabled; chọn dựa truy cập/comments thực tế, không tự giả một group có samples đủ.
2. Manifest đối chứng: chọn 10–20 bài mỗi group đề xuất, gồm post cũ ngoài window có comment trong window, nhiều replies, caption dài, parent ad/child complaint. Record IDs, permalink, readable comment/reply IDs, own timestamps/precision và thời điểm người duyệt quan sát. Nếu không tìm được case, báo NOT_OBSERVED và bổ sung sample khi có; không bịa hoạt động hoặc đăng bài/comment thử.
3. Khóa profile độc quyền; kiểm tra active jobs trước khi mở browser. Tái sử dụng session hiện có khi được phép, không copy cookie ra logs/LLM. Pilot và production không chạy đồng thời cùng profile. Không disable schedule đang chạy âm thầm để test; thiết kế job orchestration xử lý ownership rõ.
4. Cấu hình pilot DB riêng, window cố định, version snapshots; ban đầu manual v2 CLI/service trên một source/permalink để inspect, sau đó schedule v2 trên hai khung. Lệnh v2 chưa implement không được in như lệnh hiện chạy được.
5. Model gateway đọc .env; capture redacted request metadata/result validation/usage/timing. Không đọc URL bằng LLM để giả đã crawl, không dùng Google snippets thay text Facebook.
6. Người dùng/reviewer review samples thật, bao gồm rejected/pending/unknown time để đo missed cases. Tách dev golden và held-out; cần đủ relevant cases mới kết luận metric.

**Window ví dụ kiểm thử lịch sử 08/10/2026:**

| Slot VN | UTC window |
| --- | --- |
| 05:00–08:30 | `[2026-10-07T22:00:00Z, 2026-10-08T01:30:00Z)` |
| 17:00–18:30 | `[2026-10-08T10:00:00Z, 2026-10-08T11:30:00Z)` |

Ngày lịch sử dùng để validate retrieval/window; test scheduler thật dùng ngày pilot thực tế với cả hai slots, không đổi clock máy hoặc gọi backfill là scheduled live test.

## 5. Live acceptance matrix

LIVE-01 đã thử một permalink và **FAIL — LISTING_SELECTOR_MISMATCH**; các case còn lại **NOT_RUN**. [Evidence hiện tại](operations/v2-implementation-progress.md). Khi chạy ghi observed/expected IDs/counts và evidence path; HTTP 200, file JSON tồn tại hoặc giao diện có dòng không đủ để PASS.

| Case | Thao tác trên hệ thống thật | Điều kiện PASS | Evidence cần lưu |
| --- | --- | --- | --- |
| LIVE-01 | Probe approved group, mở post mẫu/comments | Access/extraction status đúng; đọc được actual post/comment text hoặc typed BLOCKED | Source/run/access mode/parser version và reference |
| LIVE-02 | Thu manifest comments/replies trong window | Tất cả nodes readable trong tập đối chứng được thu; không còn omission truy cập được chưa giải thích | Expected/observed/missing IDs, manual observation time, coverage |
| LIVE-03 | Quét bài cũ có comment/reply mới | Child nằm trong window, parent ngoài window là context; không parent-date cutoff | Parent/child IDs và own timestamps/precision |
| LIVE-04 | Thu parent quảng cáo và child complaint | Cả hai raw có trước filter; parent skipped/DROP không che child classify | Raw committed_at, filter decision at, queue/analysis at theo node |
| LIVE-05 | Crawl lại cùng source/window | Node identity count không tăng vì duplicates; observations tăng, revisions chỉ khi đổi | DB count/identity diff và observations |
| LIVE-06 | Timeout/cancel sau batch rồi chạy tiếp | Raw đã commit còn, backlog/partial rõ, resume không skip/duplicate | Task/checkpoint/transaction/run outcome |
| LIVE-07 | Chạy lịch hai slots trong ngày pilot | Ticks + final jobs đúng; window đúng VN, no overlapping browser profile | Scheduled_for/actual_started_at/window/execution keys |
| LIVE-08 | Restart service/job bận sát lượt chốt | Lượt chốt queued hoặc catch-up, không mất/nhân job; slot_end cố định | Before/after task state, restart/catch-up traces |
| LIVE-09 | Filter saved raw thực | Complaint/mixed không false-DROP; re-filter không giảm raw count; clear ads excluded khỏi phản ánh | Rule version, labels, reviewer và raw before/after |
| LIVE-10 | Gửi batch thật qua gateway Gemini | Input valid, >=2 items nếu đủ eligible; JSON/result/usage/capability thực; IDs/evidence hợp lệ | Redacted batch/model/protocol/version/validation/latency |
| LIVE-11 | Review classifier trên held-out thật | Metrics/false negatives/REVIEW/unclassified được báo đầy đủ theo taxonomy | Labels người duyệt, confusion/issue summary và cost nếu trả usage |
| LIVE-12 | Controlled provider failure/retry | Raw usable, invalid result không accepted, retries bounded và valid item giữ | Injected error marked separately với real API failures; attempt/retry state |
| LIVE-13 | Lọc table theo ngày/group/issue, review và export | Node set UI/DB/Excel khớp; reload giữ notes; thread/evidence đúng | Filter payload, node IDs, screenshot/export comparison |
| LIVE-14 | Một nguồn login/CAPTCHA/parser lỗi | Source PARTIAL/BLOCKED, nguồn khác chạy; không báo success rỗng | Typed error/outcomes, coverage và no-secret check |

LIVE-12/14 không cố tình khóa tài khoản hoặc tạo CAPTCHA: nếu không xảy ra tự nhiên, dùng failure injection trên service pilot với real stored nodes và ghi **INJECTED**, không claim provider/platform failure đã observed live. Injection là system integration evidence, không thay LIVE-01/02/10 native access/model checks.

## 6. Điều kiện nghiệm thu và metrics

### Gate bắt buộc, không cần ngân sách tiền

- Không mất raw/review, không nhân identity khi rerun/restart; filter chỉ sau commit, parent không gate child.
- Native/timestamps/evidence không invent; wrong schema/IDs/issue/quotes reject; null/unknown không giả trong window.
- Capture đủ tập readable đối chứng hoặc exceptions được xác nhận với coverage LIMITED; còn omission accessible chưa xử lý thì chưa đạt gate. Điều này không chứng minh all-group history coverage.
- Lịch bền vững có final runs/catch-up và exclusive profile. API lỗi không làm mất raw hoặc rollback crawl batch đã commit.
- UI/export khớp cùng node set/filter; lỗi/missing/pending chưa classify không bị giấu thành completed.

### Gate chất lượng đề xuất, cần review trước pilot

Theo P6: relevant-node KEEP recall >=95%, issue precision >=90% trên held-out, 0 nonexistent evidence accepted, 0 golden complaint false-DROP; latency 95% eligible nodes <=15 phút sau raw commit ở workload/API bình thường. Báo KEEP+REVIEW capture riêng, không coi REVIEW là successful KEEP để nâng recall.

Sample đề xuất 100–200 real nodes, >=30 relevant complaints nếu nguồn có đủ; mỗi issue ít samples thì báo descriptive, không claim class-level quality đã pass. Nếu không đủ samples thì gate QUALITY_INCONCLUSIVE và tiếp tục lấy đối chứng, không sinh synthetic vào held-out. Hiệu năng/token limits phải đo trên gateway đang cấu hình, không suy từ tên Gemini.

Money budgets chưa triển khai theo yêu cầu; nếu API trả usage thì ghi token/requests làm telemetry, không tạo budget gate hoặc tự đổi provider/model. Retry vẫn có bounded attempt/time limits để tránh loop vô hạn.

## 7. Bàn giao evidence, rollout và ghi nhận ACP

Evidence directories dự kiến `reports/v2/<phase>/<run_id>/`: manifest, config/schema/taxonomy/parser/prompt versions, migration audit, offline result, run tasks/window/coverage, validation, redacted API metadata, UI/export reconciliation, defects/reviewer outcome. Chỉ tạo pass report khi đã chạy; không làm file fake LIVE_VERIFIED.

Per-case status: NOT_RUN/PASS/FAIL/BLOCKED/NOT_OBSERVED/INJECTED_PASS. Acceptance decision của reviewer tách status testcase: ACCEPTED/ACCEPTED_WITH_LIMITATIONS/NOT_ACCEPTED. Invariant mất dữ liệu hoặc omission readable không được hidden dưới accepted-with-limitations; limits chỉ cho scope không truy cập/không quan sát đã công khai.

Rollout từng group sau pilot; ghi scope/schedule/model version. Service v2 feature flag/shadow, rollback UI/worker không xóa raw. Database rollback phải có handling cho dữ liệu sau backup. Không overwrite production bằng pilot DB. Các task có thể proceed dưới authorization triển khai đã có; chỉ cần thông tin nghiệp vụ/API chưa rõ, không xin lại approval chung sau mỗi phase.

**Bước bắt đầu tiếp theo:** V2-04–07 (P1 raw models/migration/upsert/filter separation). Sau gate P1 mới nối parser comments và lịch v2, rồi classifier. Test thật toàn pipeline chỉ có giá trị sau khi những phần này đã implement.
