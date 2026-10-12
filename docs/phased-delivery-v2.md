# Kế hoạch triển khai theo phase và điều kiện chấp nhận

**Đồng bộ 11/10/2026:** raw/tasks/classifier/OCR/workspace đã có code và limited live evidence. [Trạng thái hiện hành](current-state.md) là điểm đọc implementation; [24 tasks/14 live cases](execution-and-live-acceptance-v2.md) giữ acceptance gốc. Money budget DEFERRED_BY_USER; token/context/retry bounds là giới hạn kỹ thuật. Không coi mọi live case đã pass.

Kế hoạch phase ngày 09/10/2026. Core v2 đã triển khai; các gates P0–P6 bên dưới vẫn là full target scope, chưa ACCEPTED toàn bộ. Workflow lịch → crawl → raw → filter → batch → classify → analysis → UI; [TODO](../TODO.MD) và requirements matrix ghi implementation subset.

## 1. Phạm vi và nguyên tắc chấp nhận

- Pilot Facebook group public đã xác minh, 1–2 group trước, rồi mở rộng. Thu text post/comment/reply và media references. OCR, archive video/ảnh, profile/page/private group và gom vụ việc ở phase sau MVP.
- Khung giờ mặc định: 05:00–08:30 và 17:00–18:30 mỗi ngày, Asia/Saigon; chu kỳ 45 phút. Cấu hình chỉnh được. Khung crawl dữ liệu khác thời điểm job thực thi.
- Lưu thành công một batch raw rồi mới filter/classify batch đó; không cần đợi toàn group crawl hết mới xử lý. LLM chạy độc lập, không giữ browser/profile trong khi đợi API.
- Chống trùng ở storage/upsert; raw không bị xóa vì filter DROP; parent DROP không loại child. Filter không gate bằng một keyword; thiếu dữ liệu/intent mơ hồ vào REVIEW hoặc chờ extraction.
- Mỗi phase có bàn giao, kiểm thử và evidence. IMPLEMENTED không tự là OFFLINE_VERIFIED, LIVE_VERIFIED hoặc ACCEPTED. Tài liệu này chưa ghi case nào pass.
- Gate kỹ thuật bắt buộc pass trước khi bật phase tương ứng trên dữ liệu thật. Các ngưỡng chất lượng dưới đây là **đề xuất nghiệm thu pilot**, chưa là SLA hay kết quả thực tế; mentor xác nhận trước đánh giá held-out.

## 2. P0 — Chốt contracts, taxonomy và bộ mẫu

Snapshot review P0 ban đầu: [taxonomy draft](../specs/taxonomy/v1/README.md) 1.0.0-draft.1. Runtime 1.0.0 APPROVED/enabled đã có riêng trong config; provider Gemini đã nối. Mentor/held-out labels và full phase gates vẫn pending.

**Tasks:** SL-T01, GT-T01; TX-001–005, BC-001/006. Không phụ thuộc API live để soạn fixtures.

**Thực hiện:**

1. Chốt identity/relationship/time/null/extraction/coverage theo [conversation](../specs/contracts/conversation-record.md); chốt output LLM v2, taxonomy mapping với PRD v1.
2. Registry hiện có VinCons (tổ chức) và VinWonders Vũ Yên; review IDs/alias/groups/priorities/evidence khi mở rộng scope. Không coi group mapping là project fact.
3. Xác nhận provider/model/endpoint, env var key, schema support/context/token/RPM/TPM, ngân sách ngày/tháng. Không ghi key vào tài liệu.
4. Chuẩn bị golden fixtures và held-out pilot labels riêng: bài cũ có comment mới, parent quảng cáo/child complaint, replies, cùng text khác IDs, thời gian mơ hồ, nhiều issue, project conflict, API lỗi.

**Bàn giao:** versioned schemas/taxonomy approved cho pilot; mẫu nhãn người duyệt; provider decision và budget config draft.

**Điều kiện chấp nhận:**

- P0-AC01: mọi issue có ID duy nhất, definition/include/exclude/required evidence và mapping hợp lệ; TX-AC01–06 có input/expected cụ thể.
- P0-AC02: mỗi dự án pilot có source mapping đã xác nhận; project từ group được đánh dấu context, không là fact.
- P0-AC03: schema v2 tách native item ID/author UID; target/context có provenance; labels KEEP/DROP/REVIEW và unknown time không nhập nhằng.
- P0-AC04: mentor/Ops duyệt phạm vi và nhãn pilot; provider quyết định trước live API. API chưa sẵn không chặn P1–P3 offline.

## 3. P1 — Kho raw, dedup và migration

**Tasks:** SL-T02, GT-T02; GT-002/005/008. Phụ thuộc contracts P0.

**Thực hiện:** thêm nodes/revisions/relationships/source occurrences/observations, run tasks/checkpoints/coverage, reviews và queue/outbox skeleton; backup/migration/rollback; legacy projection; ngăn purge v1/excluded aliases làm mất raw v2. Unique constraints/transactions là nơi bảo đảm dedup, không chỉ in-memory crawl set.

**Bàn giao:** migration và raw repository; read path v1-compatible; fixture DB và kiểm thử storage.

**Điều kiện chấp nhận:**

- P1-AC01: migrate toàn bộ records hiện còn trong DB; IDs, aliases, notes/review và observations đúng mapping, không thất lạc. Dữ liệu đã purge được ghi là không thể recover tự động.
- P1-AC02: ingest cùng native ID 3 lượt vẫn một node; khác IDs cùng text/UID vẫn nhiều nodes; edit tạo revision, không đổi published_at.
- P1-AC03: ghi raw + observation + checkpoint transactional; crash không tiến checkpoint qua dữ liệu chưa commit.
- P1-AC04: DROP chỉ là nhãn, raw/review còn; DB reopen/restart không mất dữ liệu. Legacy CLI/output checks phù hợp pass.
- P1-AC05: rollback rehearsal trên DB copy thành công; xử lý dữ liệu phát sinh sau backup có replay/export plan, không overwrite DB live âm thầm.

Evidence: GT-AC04/06/09/11/13, counts/mapping audit, migration/rollback log không secrets.

## 4. P2 — Crawl đầy đủ phạm vi truy cập và lịch tự động

**Tasks:** SL-T03, GT-T03/04 và phần schedule acquisition của GT-T05; GT-001/003/004/006. Phụ thuộc P1.

**Thực hiện:** parser text dài/comments/replies; inventory/backfill bài cũ; all-comments UI nếu có; pagination/checkpoints; quét luân phiên bài cũ, không cutoff tuổi bài; source errors và profile lock. Tách schedule dispatcher từ dashboard trước khi nối v2; cấu hình chỉ bật khi triển khai được kiểm chứng.

**Semantics lịch phải implement/test:**

| Nội dung | Quy tắc |
| --- | --- |
| Tick khung sáng | 05:00, 05:45, 06:30, 07:15, 08:00, **08:30 lượt chốt** |
| Tick khung chiều | 17:00, 17:45, **18:30 lượt chốt**; không tạo thêm tick 45 phút trùng 18:30 |
| Window dữ liệu | Theo ngày local và khung `[start,end)`; lượt giữa khung dùng end=min(tick,slot_end). Lượt mở khung ưu tiên inventory/resume, không giả có window không rỗng |
| Chống trùng | Các lượt có thể quét lặp scope trong khung để bù late discovery; storage dedup. Overlap không nhân raw/analysis |
| Lượt chốt | Phải ghi final task bền vững, không phụ thuộc tab browser mở. Job bận thì task xếp hàng, không bỏ silently |
| Restart/missed tick | Lưu execution key schedule/date/slot/tick; reconcile missed windows thành catch-up task bounded. Run muộn vẫn dùng requested window ban đầu, không lấy now thay slot_end |
| Chưa quét hết | Giữ backlog/checkpoint, tiếp tục tác vụ bù ở trigger tiếp theo hoặc catch-up worker khi enabled; không đổi kết quả cũ thành COMPLETE |
| Thời gian nội dung | Xét riêng timestamp post/comment/reply; parent ngoài window giữ context. Thiếu/mơ hồ timestamp có bucket chưa xác minh |

Lượt chốt không đảm bảo Facebook đã hiển thị ngay mọi comment: cho phép reconciliation scan có window đóng sau đó; không cam kết độ trễ 0. Phản ánh đúng biên end thuộc quy tắc end-exclusive đã chốt, UI phải mô tả rõ.

**Bàn giao:** CLI/service tracing, scheduler durable, per-source/task coverage, initial inventory và backlog trên pilot.

**Điều kiện chấp nhận:**

- P2-AC01: bài 20/09/comment 08/10 và reply mới dưới comment cũ xuất hiện đúng ngày node; không bị ngày parent chặn.
- P2-AC02: pagination/load-more/replies được duyệt hết trong fixture; missing selector/time budget/login/CAPTCHA tạo typed partial/error, không success rỗng.
- P2-AC03: restart/duplicate ticks/job bận không nhân run/task và không mất lượt chốt; một job/profile. Thử clock giả đủ một ngày xác nhận danh sách ticks trên, ngoài khung không tạo periodic tick mới.
- P2-AC04: final task dùng end của khung; restart sau khung catch-up đúng window; missing time không lấy collected_at giả ngày đăng.
- P2-AC05: bài cũ được quét luân phiên; post inventory chưa đầy và tuổi scan có thể xem; checkpoint resume không mất node đã commit.
- P2-AC06: **100% nodes truy cập được trong tập permalink đối chứng cố định** được thu hoặc có exception cụ thể được reviewer xác nhận; unresolved accessible omissions không được pass gate. Đây không là cam kết 100% toàn lịch sử group.

Evidence: GT-AC01/02/05/06/07/08/10/14, schedule offline tests và live đối chứng 1–2 group; tách thu thập coverage khỏi classification quality.

## 5. P3 — Filter sau lưu và taxonomy/context builder

**Tasks:** SL-T04 + phần filter GT-T05; TX-001–005, BC-001. Phụ thuộc P1 và P0 taxonomy; có thể chuẩn bị bằng fixtures khi P2 chưa xong.

**Thực hiện:** filter saved raw từng node; rõ intent recruitment/sales/rental/loans/goods exchange có thể ANALYSIS_SKIPPED_IRRELEVANT và reason, raw vẫn giữ. Mixed/complaint/ambiguity không hard-DROP. Context builder target+root/parent; project candidates/basis; taxonomy profile; insufficient evidence trạng thái riêng. Không bỏ node vì không chứa exact keyword.

**Bàn giao:** taxonomy loader, filtering decision audit, contextual input v2; API preview cho mẫu.

**Điều kiện chấp nhận:**

- P3-AC01: recruitment/sales parent không làm child complaint skip; cùng raw có thể đổi filter version và xét lại.
- P3-AC02: fixture complaint có từ bán vé/tuyển dụng/vay nợ hoặc mô tả “chờ hơn nửa tiếng chưa vào được” không bị bỏ vì một từ/thiếu keyword.
- P3-AC03: caption/context tách target và origin IDs; “đúng rồi” không gán toàn bộ claim cha như phản ánh độc lập chắc chắn.
- P3-AC04: unknown/conflicting project vào shared/candidate profile hoặc REVIEW, không âm thầm DROP; CONTENT_EXPLICIT khác GROUP_CONTEXT/PARENT_CONTEXT.
- P3-AC05: taxonomy config invalid không enqueue; context thiếu/truncated được đánh dấu; raw original không bị sửa theo payload.

Evidence: TX-AC01–06, BC-AC01/07, GT-AC03/11; **0 false-DROP trên golden complaint fixtures** là gate bắt buộc.

## 6. P4 — Batch jobs và LLM classification

**Tasks:** SL-T05; BC-002–006. Phụ thuộc P3 và provider/config trước live.

**Thực hiện:** queue/lease/outbox reconciliation, cache key gồm revision/context/taxonomy/prompt/model/config/schema; batch theo tokens+items+reserved output; worker gọi API; strict validation/evidence; bounded retry/backoff/budget; reprocess versioned. Crawl worker không đợi LLM.

**Bàn giao:** independent classification service, validated analyses, attempt/usage audit, config limits, fake-provider harness và API smoke report.

**Điều kiện chấp nhận:**

- P4-AC01: request luôn qua batch builder, không direct one-request-per-item code path ngầm; batch 1 item hợp lệ khi flush/ít backlog. Token/output/context limits tính đủ system/taxonomy/wrapper, oversized có xử lý explicit.
- P4-AC02: unknown/duplicate/missing IDs, invalid JSON/schema/issue/project/evidence bị reject; không map theo array index. Valid items lưu, retry riêng lỗi khi envelope parse hợp lệ.
- P4-AC03: quotes có provenance và tồn tại trong input; unsupported claims không được gọi valid vì model score cao. URL/UID/ngày ghép từ raw, không model-generated.
- P4-AC04: 429/5xx/key lỗi/timeout/quota hết xử lý đúng; attempted retries tính budget, raw/crawl không mất hoặc bị chặn bởi API. Secrets không có trong client/log/export.
- P4-AC05: crash/2 workers/rerun không nhân analysis/jobs hoàn tất; sửa parent hoặc đổi taxonomy tạo job mới; review giữ. Billing exactly-once không được hứa khi provider không hỗ trợ.
- P4-AC06: prompt-injection fixtures không làm caption thành instructions. Sau retries invalid result về UNCLASSIFIED/REVIEW_REQUIRED, không fabricate business KEEP/DROP.
- P4-AC07: live 1 batch nhỏ được validate, ghi provider/model/version/usage/time/budget; API HTTP 200 đơn thuần chưa đủ gate.

Evidence: BC-AC01–08 tương ứng, schemas/attempt audit; chất lượng classification nghiệm thu riêng tại P6.

## 7. P5 — Giao diện và Excel

**Tasks:** SL-T06, GT-T06; GT-007/BC-005. Phụ thuộc services/contracts P1–P4; UI prototype có thể sớm hơn.

**Thực hiện:** tabs Thu thập, Dữ liệu gốc, Phản ánh, Nguồn & lịch; taxonomy YAML version preview (editor CRUD deferred); table UID/Tên/Date/Comment/URL/Loại/Group/Dự án/nhãn/Đánh giá/Ghi chú; thread/evidence; pending/stale/coverage; export full filters.

**Bàn giao:** dashboard v2 dùng persisted data, review endpoints, Excel projections và metadata.

**Điều kiện chấp nhận:**

- P5-AC01: reload/new run không reset library, reviews và notes; ngày filter là node publication, time basis/precision/unknown rõ.
- P5-AC02: raw view có ads/skipped/pending; phản ánh view KEEP và REVIEW tách; parent DROP không che complaint child; thread context ngoài window có nhãn, không tăng count trong window.
- P5-AC03: counts nội dung khác counts issues; UID tác giả khác node ID; missing UID/direct comment URL không được bịa, fallback link ghi rõ.
- P5-AC04: export **tất cả** rows theo filter khớp UI/DB, không chỉ page; long text không truncate silently; formula handling, metadata coverage/version, reviews/notes đúng.
- P5-AC05: trạng thái crawl và classification riêng; queued/partial/failed/stale không ghi hoàn tất; lịch đóng tab vẫn được backend chạy khi service hoạt động.

Evidence: GT-AC11/12, UI integration screenshots cùng fixtures và Excel row/count reconciliation.

## 8. P6 — End-to-end pilot và rollout

**Tasks:** SL-T07, GT-T07, BC-AC08. Phụ thuộc P0–P5.

**Thực hiện:** chạy pipeline thực trên 1–2 group, cả sáng/chiều qua ít nhất 2 ngày pilot; có backfill old-post/new-comment và restart/job busy test. Lập held-out review sample 100–200 nodes đề xuất, ít nhất 30 relevant complaints nếu nguồn cho phép; ghi counts mỗi issue/project. Nếu không đủ mẫu, kéo dài pilot hoặc ghi quality gate chưa đủ evidence, không tạo nhãn giả để đạt ngưỡng.

**Ngưỡng đề xuất cần mentor xác nhận trước held-out evaluation:**

| Gate | Điều kiện đề xuất |
| --- | --- |
| Thu thập | P2-AC06 đạt trên tập đối chứng; inventory/coverage ngoài tập đó báo rõ |
| Filter | 0 false-DROP trên golden complaint cases; báo tỷ lệ bị filter nhầm trên held-out |
| Nhận diện phản ánh | Recall >=95% relevant nodes trong sample; báo KEEP recall riêng và KEEP+REVIEW capture recall riêng để REVIEW không che failure |
| Phân loại issue | Precision >=90% cho issue đã gán trong held-out; báo per-issue/multi-label, class ít mẫu chỉ descriptive chưa claimed pass riêng |
| Evidence | 0 nonexistent quotes/unknown issue IDs trong analyses accepted; reviewer đánh giá entailment, không chỉ substring validation |
| Độ trễ | Sau khi raw commit, 95% eligible nodes hoàn tất classify trong 15 phút ở workload/budget pilot bình thường; không tính provider outage như thành công, báo riêng |
| Ngân sách | Không vượt budgets đã cấu hình; công bố requests/retries/token/cost hoặc UNKNOWN nếu provider không trả usage |
| Dữ liệu/UI | 0 data-loss/duplicate identity/notes-loss cases; exports khớp filter |

Định nghĩa metric: acquisition mẫu dùng tập readable nodes người duyệt xác nhận; KEEP precision/recall tính theo nhãn người duyệt; KEEP+REVIEW capture không là accepted-KEEP recall; issue precision là số predicted labels đúng / tổng predicted labels. Báo false negatives, REVIEW, insufficient evidence, excluded nodes và chưa phân loại, không chỉ các result thành công. Confidence của model không thay metric.

**Điều kiện chấp nhận P6-AC01:** evidence đủ P0–P5, metrics và exceptions rõ; mentor/Ops ghi ACCEPTED hoặc ACCEPTED_WITH_LIMITATIONS có phạm vi cụ thể. Missing sample/coverage hoặc defect mất dữ liệu không được đánh dấu complete chỉ vì chạy được dashboard.

**Rollout:** feature flag→1–2 group→mở từng group đủ điều kiện→all approved watchlist. Chốt budgets/profile throughput trước tăng tải. Rollback worker/UI không xóa raw; migration rollback theo P1. OCR và gom vụ việc không là gate MVP text.

## 9. Theo dõi bàn giao và ACP

Mỗi task ghi trạng thái PLANNED→IN_PROGRESS→IMPLEMENTED→OFFLINE_VERIFIED→LIVE_VERIFIED (khi cần)→ACCEPTED. Acceptance là mentor/Ops xác nhận, không do model tự ghi. Engineering chịu responsibility implementation/tests, QA/reviewer đối chứng; chưa gán tên người cụ thể.

Evidence package dự kiến `reports/v2/<phase>/`: test summary, fixture IDs, run/source/window/budget, counts/coverage, redacted API validation/usage, defects và reviewer decision. Chỉ tạo khi thực hiện; không tạo file fake passed trong phase viết kế hoạch. TODO ghi result path/reviewer/date và remaining gaps khi task thay trạng thái.

Thứ tự ưu tiên: **P0 → P1 → P2 → P3 → P4 → P5 → P6**. Taxonomy/provider prep và UI prototype làm song song phần không phụ thuộc; không bật pipeline mới mặc định trước live pilot. Ước lượng thời gian sau feasibility parser comments/API, chưa hứa ngày hoàn thành.
