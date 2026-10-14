# TODO — SmartCity Operational Social Listening

## Giữ kết quả khi khởi động lại / metadata thay đổi — 14/10/2026

**CLASSIFY-EVIDENCE-REUSE-01: IMPLEMENTED / OFFLINE_VERIFIED / LIVE_API_VERIFIED** — Tách bằng chứng phân loại khỏi revision raw, tái sử dụng accepted còn hợp lệ qua metadata-only target/context, bỏ job trùng bằng `EVIDENCE_UNCHANGED`, không để PENDING trùng che accepted. Giữ provenance/model/thời điểm thật; text/context/OCR/taxonomy/prompt đổi vẫn cần xử lý lại. Thêm index tra context theo node/source. **140 test đạt / 1 OCR opt-in skip**. Đã nạp dashboard/classifier lúc rảnh; API thật xác nhận **18 Giữ**, phục hồi đúng identity với kết quả lịch sử, không cần gọi Gemini để phục hồi; phép đo cuối 4,530 giây. [Biên bản](docs/operations/classification-keep-count-20261014.md). Worker vẫn scan local; incremental reconciliation và lịch sử đổi nhãn trên UI chưa thuộc bản sửa này.

## Facebook Chạy ngay — 14/10/2026

**FB-DIRECT-READ-01: IMPLEMENTED / OFFLINE_VERIFIED / LIVE_PARTIAL** — Tách health/job polling và khởi tạo tab; health nhẹ không khóa đọc bảng; tiến độ raw từng group/hội thoại; kết quả và unknown-time theo observations của lượt; lỗi đọc giữ job/raw; tránh bấm crawl trùng; dành thời gian permalink/comments sau inventory. Sửa outcome lỗi ghi đè partial, thu ngắn khóa ghi enqueue/claim classifier, giữ parent/type reply khi hydration thiếu parent. **119 kiểm thử đạt**; đã nạp backend/classifier. Pilot browser thật một group ghi nhận **69 node (18 bài, 43 bình luận, 8 trả lời), 10 trong window**, không tái hiện lỗi parser/worker; còn nội dung không truy cập được và coverage PARTIAL. Kho thật đọc lại được 5.574 nội dung; phép đo API đồng thời: health 9,983 giây, bảng 12,177 giây. [Chẩn đoán, bằng chứng và giới hạn](docs/operations/facebook-direct-reconnect-20261014.md). Chưa tuyên bố mọi parser lỗi đã sửa, mọi request bảng dưới 30 giây hoặc full-window coverage; SQL pagination/materialized view còn mở.

## Threads VinCons đúng đối tượng — 13/10/2026

**THREADS-SCOPE-01: IMPLEMENTED / OFFLINE_VERIFIED / LIVE_PARTIAL** — Parser v5 xác minh URL/ô query và vùng kết quả hiển thị; sau commit raw, scope gate theo alias dự án hoãn hội thoại không có evidence, giới hạn hai hội thoại thiếu evidence/query, kiểm tra commercial intent trước fetch. Giữ rescan bài cũ/child evidence, raw/reviews/lineage và query rộng; thêm sáu seed VinCons, classifier nhận `Vin Cons`. **109 kiểm thử đạt**, bản sửa/config v3 đã nạp; scheduler thật chạy đủ bảy query, quan sát 82 candidate occurrences/11 caption đúng alias, lưu 142 node (25 trong window), vẫn PARTIAL. [Đối chiếu](docs/operations/threads-vincons-scope-20261013.md); report query pilot và production nằm trong `reports/threads-vincons-*-20261013.json`. **Còn mở:** phân loại tập live đang chờ, nghiệm thu seed bằng phản ánh hữu ích, recall bài thiếu alias, nested parent và full-window coverage; không coi caption khớp alias là phản ánh.

## Vận hành không treo máy cá nhân — thiết kế 13/10/2026

**OPS-RUNTIME-RECOVERY-01: LOCAL_IMPLEMENTED / OFFLINE_VERIFIED / LIVE_TASK_API_VERIFIED** — Người dùng chọn local: supervisor tự bật/nhận dashboard + classifier, thay worker kết thúc với backoff; đã đăng ký và chạy task `SocialListeningRuntime` khi đăng nhập Windows. Ledger/snapshot lịch, chạy bù ca đóng tối đa 7 ngày có lịch sử, gộp tick/idempotency, reuse lượt thường, giữ nguyên raw/reviews/DONE. Lần đầu chỉ đối soát hôm nay; config thay giữa ca được báo skip, coverage chưa đủ không coi là thu hết. [Runbook](docs/operations/local-runtime-recovery.md), [thiết kế](docs/implementation-plan-runtime-recovery.md). **112 kiểm thử đạt**, gồm API và process con thật bị kill rồi thay thế; live Task/API đạt và bản cuối đã nạp. Report `reports/local-runtime-live-20261013.json`; chưa reboot/logoff máy người dùng hoặc nghiệm thu full coverage multi-day live.

## Khôi phục ca sáng 13/10/2026

**OPS-PROFILE-RECOVERY-02: LIVE_RECOVERED / OFFLINE_VERIFIED / NEXT_START_DEPLOYMENT** — Facebook 14 nguồn và Threads bị `PROFILE_IN_USE` do file khóa còn PID đã chết. Đã xác minh không còn browser dùng profile, lưu khóa cũ để đối chiếu, giữ cookie và khôi phục Facebook; bật lại worker phân loại liên tục. Phiên UI hôm nay từ 3 nội dung (1 bài/2 bình luận) lên 15 (5 bài/10 bình luận) sau làm mới. Cơ chế khóa OS + thu hồi metadata chỉ khi PID chết và không có browser đã bổ sung, 46 kiểm thử đạt; nạp khi dashboard khởi động lại, giữ lượt crawl đang chạy. Threads live sau khôi phục và full coverage ca sáng chưa xác nhận. [Đối chiếu và nghiệm thu](docs/operations/morning-crawl-recovery-20261013.md).

## Thông báo dữ liệu mới giả — 12/10/2026

**VIEW-NOOP-01: IMPLEMENTED / OFFLINE_VERIFIED / LIVE_IDLE_VERIFIED** — Worker không có API job mới vẫn ghi lại quyết định lọc cũ, đổi `filtered_at`/rowid; marker version toàn kho coi đây là dữ liệu mới. `filter_saved` nay không ghi khi decision/revision/rule không đổi; marker filter hash chỉ xét nội dung quyết định và bỏ timestamp/rowid, tương thích worker cũ. 41 kiểm thử đạt, gồm no-op không ghi và không đổi version, timestamp-only rewrite không đổi version, thay đổi decision thật vẫn đổi version. Đã nạp backend/worker lúc không có request đang chạy; hai lần đối soát cách nhau 44 giây có cùng data_version qua các vòng worker `NO_PENDING_JOBS`, 0 job mới / 0 API call. Phiên bảng trước bản sửa cần cập nhật một lần để nhận marker mới.

## Backend đọc dữ liệu quá tải — 12/10/2026

**BACKEND-READ-LOAD-01: IMPLEMENTED / OFFLINE_VERIFIED / LIVE_API_UI_VERIFIED** — Streaming job history, giới hạn dựng bảng đồng thời, cache thống kê 15 giây / tối đa bốn bảng, health compact, endpoint version 124 byte thay polling dựng snapshot, chặn dashboard trùng trước khi tạo scheduler; sửa trạng thái form giả sau reload. 60 kiểm thử đạt; database thật: health 1,423 giây cold / 0,241 giây cache, version 0,153–0,257 giây, bảng 2,629 giây; request đọc cạnh tranh trả 503 có kiểm soát. Hai dashboard cũ đã được retire sau khi giải phóng profile, một dashboard mới hoạt động; worker phân loại giữ nguyên. [Biên bản, flow, số đo và giới hạn](docs/operations/dashboard-backend-load-20261012.md). **Còn mở:** materialize dữ liệu đọc / SQL pagination, load test nhiều client và đo dài hạn.

## Truy vết không có dữ liệu mới — 12/10/2026

**OPS-CRAWL-FLOW-01: LIVE_PARTIAL / BLOCKER_RECOVERED** — 14 nguồn Facebook bị `PROFILE_IN_USE` vì `sessions/browser/facebook.lock` trỏ PID 27840 đã dừng từ 07:25; không có browser sử dụng profile. Đã lưu bản sao khóa trong reports rồi gỡ khóa mồ côi, giữ cookie/raw/reviews/lịch. Worker tiếp tục các task đã có, đối soát 15:53: tổng 3.137 → 3.167 nội dung (+30 identity mới); có bình luận thật được trích xuất, vẫn có outcome parser lỗi và chưa xác nhận bao phủ đầy đủ. Worker Gemini liên tục từng dừng: đã kiểm tra không có tiến trình trùng, bật lại theo quyền chạy liên tục; heartbeat RUNNING và có cycle PROCESSED. Luồng hiện hành: window cố định → inventory/permalink/comments/OCR → SQLite raw/dedup → filter từng thread → classifier batch đọc raw → dashboard snapshot. Resume không mở rộng window; lượt đang chạy kết thúc lúc 14:24:07, không tự bao gồm bài đăng muộn hơn. UI cần Làm mới dữ liệu để thay snapshot. **Còn mở:** tự thu hồi khóa mồ côi an toàn khi worker bị dừng bất thường; tự phục hồi classifier sau restart; nghiệm thu coverage/parser theo từng nguồn.

## Khôi phục theo dõi lượt chạy — 12/10/2026

**UI-JOB-RECOVERY-01: IMPLEMENTED / OFFLINE_VERIFIED / LIVE_UI_VERIFIED** — Lượt Facebook tiếp tục từ báo cáo bền vững giữ cùng mã job thay vì tạo mã mới mỗi retry. API trả `JOB_NOT_FOUND` khi phiên theo dõi không còn trong cache; UI ngừng poll mã mất, tìm lượt đang chạy, không hiển thị lỗi theo dõi trên tab dữ liệu đã lưu. Đồng bộ trường `job_id` trong phản hồi 409; lỗi đọc tạm thời vẫn cho retry, phản hồi cũ không ghi đè lượt mới. 31 kiểm thử dashboard đạt, gồm 25 lần resume và Chromium desktop/mobile: 404, health cũ, reconnect, 409, reload, giữ bảng và input. Backend đã khởi động lại trong khoảng nghỉ giữa các lượt crawl; kiểm tra API 404 có mã lỗi đúng và reload dashboard local hiển thị 3.137 nội dung / 25 dòng trang hiện tại, không còn thông báo lỗi. [Ảnh nghiệm thu](reports/dashboard-job-recovery-20261012.png). Không dùng kết quả này để xác nhận crawl đủ window hay chất lượng phân loại.

## Bàn giao dev — 12/10/2026

**DEV-HANDOFF-01: OFFLINE_VERIFIED / PUSHED / REPO_STANDALONE_VERIFIED** — Cập nhật README, chỉ mục docs, PRODUCT và [hướng dẫn checkout/cài/chạy](docs/development-handoff-20261012.md). Code đã push lên repository độc lập `TruowNguyen/social_media_scraping`, public, mặc định `dev`; fork cũ đã xóa sau backup/đối chiếu. Theo yêu cầu của chủ repo, `main` và `dev` khởi tạo lịch sử mới từ code hiện hành, tác giả root commit là `TruowNguyen`; backup lịch sử cũ local và ghi [nguồn gốc code](docs/code-origin.md). Toàn suite: 305 kiểm thử, 277 đạt, 28 opt-in skip; compile đạt, config VALID. Packaging bao gồm HTML/JS/CSS dashboard. Credentials, phiên browser, database và exports local được ignore. Cập nhật UI/lịch đa nền tảng có [biên bản riêng](docs/operations/workspace-platforms-20261012.md); full coverage/model quality vẫn chưa nghiệm thu.

## Threads — triển khai và pilot 12/10/2026

**THR-RUNTIME-01: IMPLEMENTED / OFFLINE_VERIFIED / LIVE_PARTIAL; FULL_ACP_PENDING.** Đã có browser adapter, registry/query versions, raw v3, spool/ACK, lịch riêng, Gemini batch và giao diện đa nền tảng. Pilot `VinWonders Vũ Yên` có 43 nội dung thật (4 bài viết, 39 trả lời). [Runbook + giới hạn](docs/operations/threads-acquisition.md), [snapshot nghiệm thu](reports/threads-deployment-final.json), [plan P0–P7](docs/implementation-plan-threads.md). Không xác nhận thu hết window/nested replies hoặc hoàn tất toàn bộ P0–P7.

**THR-DOC-01: DOCUMENTATION_VALIDATED** là snapshot bước thiết kế 11/10, [report](reports/threads-plan-documentation-validation-20261011.json). Trạng thái runtime hiện hành ở bảng dưới.

| Task | Phase / công việc | Trạng thái | Kết quả hiện tại | Điều kiện ACP / evidence cần có |
| --- | --- | --- | --- | --- |
| THR-T01 | P0: query theo dự án/aliases/ambiguous gates | OFFLINE_VERIFIED / LIVE_PARTIAL | 6 seeds, 4 keyword bật; live xác minh một query Vũ Yên | THR-AC01; đối chứng các seed còn lại |
| THR-T02 | P0: capability/provider | LIVE_PARTIAL | Browser RECENT và public replies đọc được; API chưa token/pilot | Matrix trong runbook; API permission/quota còn mở |
| THR-T03 | P0: pilot thật | LIVE_PARTIAL | 43 raw nodes; provider browser; window/query/outcome đã lưu | THR-AC02/03 đạt phần đọc; AC04 chưa đạt nested/full coverage |
| THR-T04 | P1: models/identity đa nền tảng | OFFLINE_VERIFIED | v2 Facebook giữ; v3 Threads, shortcode khác native ID, chặn cross-platform/root reply | THR-AC05; contract tests |
| THR-T05 | P1: migration/backup/rollback | PARTIAL_VERIFIED | Có backup, 3.070 FB giữ fingerprint/reviews; upgrade trong transaction | THR-AC05/06; rehearsal rollback vận hành còn mở |
| THR-T06 | P1: registry/query versions | OFFLINE_VERIFIED / LIVE_PARTIAL | THREADS_SEARCH, CAS config, disabled/archive gates và snapshot lineage | THR-AC01; query không thành group |
| THR-T07 | P2: durable spool/ACK/DLQ | OFFLINE_VERIFIED / LIVE_USED | ACK+checkpoint cùng commit; checksum, crash/replay, expiry fence/recovery đã test | THR-AC06/07; stress backpressure còn mở |
| THR-T08 | P2: storage worker chung | PARTIAL_IMPLEMENTED | Threads dùng spool và repository; Facebook vẫn ghi trực tiếp | THR-AC07; còn migrate Facebook và daemon storage riêng |
| THR-T09 | P2: concurrency/regressions | OFFLINE_VERIFIED | 251 contract (250 đạt, 1 skip); hai producers + review writer test đạt | THR-AC05/06/07; live dual-crawler + classifier chưa đối chứng |
| THR-T10 | P3: browser RECENT/lineage | LIVE_PARTIAL | Search thật, window/quota, 6 candidates, mở 4 hội thoại; metadata ghi rõ | THR-AC01/02; coverage chỉ trong kết quả quan sát |
| THR-T11 | P3: detail/replies/parent mapping | LIVE_PARTIAL | 39 trả lời raw; nested parent UNVERIFIED; 2 unresolved roots được giữ null | THR-AC03/04; chưa nghiệm thu exact parent/full replies |
| THR-T12 | P3: old-root rescan/checkpoint | PARTIAL_VERIFIED | Inventory/rescan fairness; tìm thêm 1 reply khi chạy lại | THR-AC04; cần tập đối chứng bài cũ/reply mới trong window khác |
| THR-T13 | P4: scope resolver | OFFLINE_VERIFIED / LIVE_API_VERIFIED | Input/output v3; QUERY_CONTEXT chỉ hint; KEEP cần evidence nội dung/cha | THR-AC01/08; cần reviewer đánh giá scope precision |
| THR-T14 | P4: Gemini batching/reuse | LIVE_API_VERIFIED | Caption/replies đã được Gemini phân loại validated; giữ DONE hợp lệ, lý do tiếng Việt | THR-AC08; snapshot hiện hành trong report, chất lượng UAT còn mở |
| THR-T15 | P4: OCR Threads | PLANNED | Chưa nối OCR vào Threads | THR-AC12; gate riêng |
| THR-T16 | P5: lịch/lease riêng | OFFLINE_VERIFIED / PILOT_ENABLED | 2 ca/45 phút, closing tick, opening inventory; bật/tắt riêng, trạng thái snapshot | THR-AC09; chưa theo dõi thực tế đủ 3 ngày |
| THR-T17 | P5: catch-up/health/errors | PARTIAL_VERIFIED | Catch-up trong ngày, lease expired recovery; API 401/429/schema offline | THR-AC09/10; token API/live rate-limit chưa chạy |
| THR-T18 | P6: bộ lọc/backend/UI | OFFLINE_VERIFIED / LIVE_UI_VERIFIED | Platform/query/run/date/type, bảng 43 raw, xem context, reviews giữ nguyên | THR-AC11; desktop/mobile đã kiểm tra |
| THR-T19 | P6: lịch UI/Excel | OFFLINE_VERIFIED / LIVE_UI_VERIFIED | Lịch riêng, save khác enable; export theo snapshot có platform/query columns | THR-AC09/11; export 43 rows đối soát trong report |
| THR-T20 | P7: held-out/3 ngày/ACP | IN_PROGRESS / FULL_ACP_PENDING | Pilot thật, dedup/reuse/parser đối chiếu; không tuyên bố toàn bộ yêu cầu đạt | THR-AC01–13; nested mapping, held-out quality, old/new case, 3 ngày còn mở |

**THR-DESIGN-01: DESIGNED / IMPLEMENTED_SUBSET** — [luồng adapter](docs/design/threads-adapter-flow.md), [UX/UI Impeccable](docs/design/threads-workspace-ux.md), [product context](PRODUCT.md). Tab Thu thập chọn nền tảng, query/run/schedule riêng; raw/classifier/filter/Excel dùng chung. Thiết kế đầy đủ vẫn là đích nghiệm thu; phần triển khai và bằng chứng hiện hành đọc trong bảng/runbook, không dùng report kiểm tra tài liệu làm live proof.

Input/expected output chi tiết từng THR-AC01–13 ở [plan mục 8](docs/implementation-plan-threads.md#8-acceptance-và-kiểm-thử-hệ-thống-thật). Kết quả thực thi bổ sung theo report run/query/provider/window, không cập nhật trạng thái bằng suy đoán.

## Đồng bộ trạng thái — 11/10/2026

- **FILTER-V3-01: IMPLEMENTED / OFFLINE_VERIFIED / LIVE_API_VERIFIED / BACKLOG_COMPLETED; QUALITY_UAT_PENDING** — Thu hẹp bảo vệ disclaimer/quảng cáo, phân biệt OCR target/context, giữ OCR phản ánh khi caption bán hàng, đồng bộ provider/validator và lý do trên bảng/mobile. Đối soát giữ 2.254 DONE, enqueue lại 416 đầu vào chịu ảnh hưởng; raw/reviews/lịch sử giữ nguyên. Pilot 10/10 batch 6 + 4; v3.1 xử lý đúng một case bảng giá/OCR, giữ 2.673 DONE khác, pilot riêng 1/1. Kết quả cuối: 2.674 DONE, 184 FILTER_DROP, 111 MISSING_TEXT; không PENDING/RUNNING/FAILED hiện hành. Worker ACTIVE, scheduler sống; lượt không có dữ liệu mới không gọi API. 229 contract chạy (228 đạt, 1 opt-in skip), 5 Chromium đạt. Precision/recall chưa nghiệm thu. [Runbook + acceptance](docs/operations/filter-policy-v3-20261011.md), [snapshot triển khai](reports/filter-policy-v3-deployment-20261011.json), [kết quả cuối](reports/filter-policy-v3-final-results-20261011.json).

Đã đối chiếu tài liệu với code/config hiện hành. [Trạng thái dự án](docs/current-state.md), [requirements matrix](specs/traceability/requirements-matrix.md) và [audit documentation drift](docs/documentation-drift-audit-2026-10-11.md) là điểm đọc trạng thái mới nhất.

- Dashboard đã dùng raw v2 POST/COMMENT/REPLY, giữ raw trước filter/classify, OCR ảnh POST, Gemini worker, hội thoại/reviews và Excel theo phiên bảng.
- 14 Facebook group VERIFIED/enabled; hai scope VinCons/VinWonders Vũ Yên. Google bật, TikTok search tắt; watchlist seed vẫn DRAFT, watchlist acquisition ACTIVE.
- Lịch `dashboard-schedule-v2` có lượt chốt 08:30/18:30. Runtime taxonomy 1.0.0 APPROVED/enabled khác specs review draft 1.0.0-draft.1.
- UXR đã triển khai; UAT/mentor, coverage toàn group/comment, held-out classifier, OCR benchmark, TikTok live và toàn PRD v1/product ACP còn pending.
- Lượt kiểm tra đồng bộ: 258 tests được discover, **237 pass / 21 browser opt-in skip**, không failures/errors; không gọi nền tảng/model thật.

Các bảng PREP/BASE/CORE/SRC/SC/PF/GT/SL/P0 bên dưới giữ **snapshot kế hoạch và kết quả theo ngày 08–10/10**. Trạng thái PLANNED/BLOCKED hoặc mô tả “chưa có runtime” trong snapshot không ghi đè các increment triển khai mới. Điều kiện ACP còn thiếu vẫn giữ nguyên; không đánh dấu toàn task/phase hoàn tất chỉ vì có implementation subset.

## UXR — Kế hoạch tối ưu dashboard sau audit 10/10/2026

Các phase UXR dưới đây đã có implementation/verification như bảng và increment ngày 10/10 cuối file. [Kế hoạch chi tiết](docs/dashboard-ux-implementation-plan.md) giữ dependencies, 21 test cases và ánh xạ đủ 26 vấn đề audit; UAT chưa hoàn tất.

| Phase | Tasks | Output nghiệm thu | Trạng thái / kết quả |
| --- | --- | --- | --- |
| 0 — Baseline/contracts | UXR-01/02/03 | Baseline backup, state/API contracts, wireframes và traceability | IMPLEMENTED / OFFLINE_VERIFIED; xem increment UXR bên dưới |
| 1 — Tính đúng/draft | UXR-04/05/06/07/08 | Không mất note/chi tiết, scope đúng, snapshot bảng/count/export | IMPLEMENTED / OFFLINE_VERIFIED; xem increment UXR bên dưới |
| 2 — Evidence/review | UXR-09/10/11/12 | Hội thoại, shared identity, human review/version, model states riêng | IMPLEMENTED / OFFLINE_VERIFIED; xem increment UXR bên dưới |
| 3 — Vận hành | UXR-13/14/15 | Health/progress, manual vs schedule, recovery/scope lệnh | IMPLEMENTED / OFFLINE_VERIFIED; xem increment UXR bên dưới |
| 4 — Workspace/filters | UXR-16/17/18/19 | Shared filters, restore URL view, desktop/mobile/a11y | IMPLEMENTED / OFFLINE_VERIFIED; xem increment UXR bên dưới |
| 5 — Duyệt/report | UXR-20/21/22 | Bulk/sort, classified Excel, copy/provenance | IMPLEMENTED / OFFLINE_VERIFIED; xem increment UXR bên dưới |
| 6 — Acceptance/rollout | UXR-23/24 | Regression/UAT/live-read evidence, migration và rollback | DEPLOYED / UAT_PENDING; xem increment UXR bên dưới |

Trang Phản ánh mặc định, bảng/panel hội thoại, bảo vệ draft/scope và phiên Excel đã triển khai. Xem [workspace hiện hành](docs/operations/dashboard-workspace.md); thứ tự UXR-01/02 → UXR-04/05/06 là sequencing của kế hoạch gốc.

## UX-01 — snapshot trước UXR, 10/10/2026

- **UX-02 OFFLINE_VERIFIED:** vấn đề theo taxonomy dự án, nhãn gỡ từng bộ lọc, auto-refresh kết quả worker nền, lọc raw khi đổi lựa chọn, xác thực ngày và bảo vệ request đồng thời. 16 test pass lượt đầu; 12 test liên quan pass xác nhận cuối, gồm 3 Chromium fixtures. Chi tiết trong [runbook UX](docs/operations/dashboard-ux.md). Mapping taxonomy mới cần restart backend sau khi lượt crawl đang hoạt động kết thúc.

- **OFFLINE_VERIFIED / LIVE_READ_VERIFIED:** bộ lọc chính/nâng cao, preset, ngày nhanh, phân trang, responsive desktop/mobile; lọc dữ liệu đã lưu không gọi Gemini.
- **Kết quả:** 37 test pass (3 Chromium fixtures); endpoint phân loại giảm từ 29,919 xuống 1,338 giây, cache 0,169 giây; kho dữ liệu 0,954 giây trên 2.153 nội dung. [Runbook](docs/operations/dashboard-ux.md), [bằng chứng](reports/dashboard-ux-validation.json).
- **Impeccable:** launcher hoạt động, workspace root liên kết cùng skill trong repo; chat mới cần nạp lại danh sách skill.
- **Restart backend còn chờ:** lượt crawl 14 group đang chạy; không dừng lượt này để áp dụng hai sửa chữa cho database chỉ chứa raw, đã được kiểm tra bằng fixture. Giao diện và tối ưu truy vấn hiện đã phục vụ trên dashboard.

Cập nhật: **08/10/2026**. Repository: `social_media_scraping`. File này theo dõi **công việc → requirement/spec → trạng thái → kết quả/bằng chứng → điều kiện ACP**. ACP được dùng để chỉ đạt acceptance của công việc, không thay bằng việc chỉ có code hoặc mock pass.

Nguồn yêu cầu: [PRD v0.1](specs/product/prd.md), [specs và quyết định đã chốt](specs/README.md), [gap analysis](docs/prd-to-code-gap-analysis.md), [refactor plan](docs/refactor-plan.md), [implementation plan](docs/implementation-plan.md). Tiêu chí chi tiết ở spec; TODO không thay đổi scope hoặc tự thêm yêu cầu nghiệp vụ.

## 1. Snapshot acquisition/dashboard v1 — 08/10/2026

- Lịch theo yêu cầu mới: **DAILY_SLOTS**, hằng ngày **05:00–08:30 và 17:00–18:30 VN**, cố định **45 phút**. Đã bật/lưu qua dashboard. Grid sáng 05:00/05:45/06:30/07:15/08:00; chiều 17:00/17:45/18:30; ngoài khung không bắt đầu lượt mới, không replay lượt đã lỡ và không chạy chồng. Window mỗi job `[đầu khung, thời điểm chạy)` (không vượt cuối khung), dedup và exclusion giữ nguyên. **72 acquisition/dashboard tests pass**, UI slots + fixed cadence + bật/tắt desktop/mobile fixture pass. [Evidence](reports/daily-slots-schedule-20261008.json). Chưa kiểm chứng các chu kỳ hằng ngày live; cần máy/backend chạy. Khoảng 08:00–08:30 không có thêm lượt riêng với chu kỳ cố định 45 phút.

- Tách UI **Tìm kiếm** (Google discovery theo keyword/hashtag) và **Crawl group theo thời gian** (chỉ Facebook enabled/ready, không keyword/Google jobs). Tab crawl có chạy một lượt và **lịch lặp**, rolling/fixed window, chu kỳ 5–1440 phút, bật/cập nhật/tắt, persistent config/reload, fixed end auto-stop, single-service overlap lock và active-job recovery sau refresh. Mặc định lịch tắt, đề xuất 30 phút/7 ngày; cần backend/máy hoạt động. **69 acquisition/dashboard tests pass**, UI Chromium desktop/mobile fixture pass, 0 platform/API requests trong tests. [Runbook](docs/operations/dashboard-crawl-schedule.md). Chưa live-verify chu kỳ scheduler dài hạn, Windows service hoặc scheduling ACP PRD.

- Recheck exclusion tuyển dụng: thêm “tìm gấp 20 công nhân đi làm ngay”, “tuyển đội thi công”, lao động phổ thông và modifiers numeric/gender. Engine kiểm tra lại nội dung bản ghi cũ trước reuse; dashboard reclassify readonly trước output, không tin PASS cũ. Purge **3 bản ghi tuyển dụng** và observations/aliases bằng rejection policy bảy trường; 0 clear-DROP records còn lại theo rule hiện tại; 0 API requests. **65 acquisition/dashboard tests pass**, bao gồm no-deep-fetch, purge stale full text và chặn stale PASS trên UI; complaint/scam/nợ lương/trao đổi ca giữ REVIEW. [Evidence](reports/exclusion-recheck-20261008.json). Không tuyên bố regex đã nhận mọi cách diễn đạt tuyển dụng; intent mơ hồ vẫn REVIEW.

- UI bổ sung cột **Group** cạnh Link URL: tên từ Registry và link group lấy theo origin của permalink Facebook, hỗ trợ verified aliases. Nếu chưa xác định tên, hiển thị group ID/slug; nền tảng khác để trống. Mapping không lấy nhầm tên nguồn Google làm tên group. Chromium local kiểm tra 10 dòng dữ liệu đã lưu, đủ 5 cột, group links hợp lệ, không lỗi JavaScript; không crawl/API. [Preview](reports/dashboard-group-preview.png).

- Sửa lỗi UI báo chung khi có lượt tìm kiếm đang chạy: backend trả HTTP 409/SEARCH_RUNNING + job_id; UI theo dõi lại lượt hiện tại thay vì báo sai keyword/ngày. Các lỗi input đã biết có thông báo cụ thể, không trả exception cấu hình tùy ý. **10 dashboard tests pass**, gồm HTTP busy/validation. Input “VinCons kẹt xe”, 01/10–08/10/2026 được xác nhận hợp lệ; dashboard khởi động lại sau khi lượt trước đã kết thúc.

- Theo yêu cầu chạy thử trên UI, **bảy Facebook group đã enabled** trong config chính sau pilot access/native ID/time. Registry readiness **7/7**, config VALID; dashboard đang hoạt động. Cấu hình `requires_login=true` chọn cách vận hành bằng profile Facebook đã lưu đã được kiểm chứng; chưa thử anonymous access nên không kết luận mọi group bắt buộc đăng nhập. UI đọc Registry mỗi lượt Tìm kiếm; Facebook browser trực tiếp và Google SerpApi bổ sung, chưa tự chạy crawl/scheduler. Full-window coverage và ACP vẫn chưa xác nhận.

- Kiểm chứng live **7/7 Facebook group** bằng AcquisitionEngine + FacebookGroupAdapter + Playwright/Chromium, **0 API attempts**; một mẫu/group có native ID + thời gian đăng. Window 01/10 19:59:45 → 08/10 19:59:45 VN. Sau đối chiếu: 3 DROP, 1 đăng sau cutoff, 3 bản ghi giữ (2 mới, 1 đã có). Sửa mẫu tuyển dụng numeric/gender bị bỏ sót và purge nội dung đã lưu; **60 acquisition/dashboard tests pass**. Registry access/native ID/time VERIFIED, enabled flags giữ nguyên; full coverage/order/ACP chưa đạt. [Báo cáo](reports/facebook-seven-groups-20261008/README.md), [evidence](reports/facebook-seven-groups-20261008/report.json). Snapshot và ledger cũ bên dưới là lịch sử.

- Ưu tiên freshness: output chỉ nhận published_at/INSTANT thuộc fixed window hiện tại, sắp mới nhất trước; Google snippet/discovery time, timestamp comment và UNKNOWN không vào bảng kết quả mới. Parser Facebook dùng public Story post_id + creation_time, không lấy permalink comment; hỗ trợ selector story_message. Pilot live một group: bài `1819342645766311` đăng **08/10/2026 19:26:03 VN**, FETCHED/IN_WINDOW, unknown_time=0. Nguồn fb_group_1675953926771851 đã bật sau pilot; search form chạy nguồn FB ready trước Google bổ sung. [Pilot](reports/facebook-native-time-pilot/report.json). **8 dashboard + 51 acquisition + 5 Chromium tests pass**. Chưa xác nhận coverage cả bảy groups/TikTok hoặc dữ liệu mới đầy đủ; không nâng ACP acquisition tổng thể.

- Giao diện local đã đổi theo yêu cầu: keyword/hashtag có recommend + tự nhập; khoảng ngày mặc định hôm nay Asia/Saigon; nút tìm Google gọi acquisition engine có exclusion/quota/queue. Output 4 cột link video, dự án/vị trí, description summary, vấn đề; enrichment chưa có để trống. Không tự search khi mở trang, không auto-approve/scheduler. UI Chromium desktop/mobile và flow input/output kiểm chứng offline bằng fixture, 0 API requests; kết quả search UI live chưa được xác nhận.

- Setup lookback **7 ngày = 10.080 phút** cho hai watchlist; Google scope và acquisition watchlist enabled sau Account API/search probe thành công. Google date filter WINDOW gửi khoảng ngày UTC qua tbs và giữ fixed-window cho historical rerun. **50 acquisition tests pass**, config VALID. Chưa chạy lượt live 7 ngày; lịch sử probe/window cũ được giữ. Facebook/TikTok main sources còn disabled; scheduler chưa bật, quota/time budget không tăng.

- Sửa exclusion sau Google keyword pilot: thêm RENTAL/LOAN_DEBT, nhận diện tuyển dụng rõ từ title không cần contact/wage và Unicode cách điệu; giữ complaint/nợ lương/shift exchange để REVIEW. **49 acquisition tests pass**. Lọc lại pilot `run_d3e1884070e148318a7418124924e912`: loại thêm 4 tin tuyển dụng khỏi SQLite queue và export; tổng 6 rejection metadata, còn 1 REVIEW (snippet nhắc tên group tuyển dụng, chưa chứng minh intent của bài). [Báo cáo pilot](reports/google-keyword-20261008T113043Z/report.json). Không gọi API khi lọc lại; chưa xác nhận ACP cho acquisition.

- Venv `.venv/audit`: Python **3.13.13**, collection requirements + editable package + Playwright **1.63.0** đã cài. Chromium **153.0.8010.12** mở trang local thành công; transformers/faster_whisper/models và FFmpeg cho yt-dlp chưa thiết lập.
- Sáu collector legacy: YouTube, TikTok account, X, Telegram, Reddit, Truth Social. Baseline offline giữ nguyên; adapter acquisition mới đã có code/tests và resource probes, chưa full live acceptance.
- Bảy Facebook seeds: **7 PUBLIC, 7 access_verified theo USER_MANUAL_CONFIRMATION, 0 enabled**. Sáu tên có provenance name_verified. Cả bảy vẫn PENDING_VERIFICATION/requires_login=null; probe của một group gặp LOGIN_REQUIRED, chưa có full-item live evidence.
- Registry/query/prefilter/storage và ba adapter mới có runtime, behavioral tests và Chromium DOM fixtures. Specs có **29 requirement IDs, 64 acceptance scenarios**; đã kiểm tra subset, VER-01 còn fixtures/mapping bổ sung. [Validation](docs/baseline/acquisition-validation.json).
- `src/` sở hữu acquisition types/adapters/filter/storage; `engine/` sở hữu Registry/dispatch/CLI. Có SQLite acquisition riêng, queue/review, window/rerun/lineage và JSON export. Canonical enrichment nghiệp vụ, LLM/media processing/Excel/scheduler còn PLANNED. [Implementation](docs/acquisition-implementation.md).
- Theo yêu cầu cleanup tiếp theo: đã bỏ 11 root Python files và `src/compat`; chạy/import trực tiếp package modules. Runner/CI/README/packaging đã cập nhật, không đổi JSON/schema hoặc CWD data paths. [Cleanup validation](docs/baseline/root-cleanup-validation.json).
- BASE-01 có PRD snapshot cùng SHA và matrix đủ 17 FR. Chromium dự án đã probe nền tảng: Facebook LOGIN_REQUIRED; TikTok keyword CAPTCHA, hashtag selector mismatch; SerpApi key hiện có bị từ chối INVALID_KEY, 1 attempted request. [Probes](docs/operations/acquisition-live-probes.json).
- Chưa có task runtime mới ở trạng thái ACP. Chưa đo KPI sản phẩm; không tính tỷ lệ hoàn thành từ số file tài liệu.

Latest acquisition implementation (2026-10-08): Registry, candidate/API, browser adapters, SerpApi, SQLite/lineage and queue CLI now have code and offline evidence. Historical snapshot bullets above describe the preceding refactor stage. All seeds/scopes remain disabled; current resources and gaps are in [implementation report](docs/acquisition-implementation.md) and [live probes](docs/operations/acquisition-live-probes.json). No ACP claim.

## 2. Cách cập nhật trạng thái và ACP

| Trạng thái | Ý nghĩa |
| --- | --- |
| `PLANNED` | Có việc cần làm/spec, chưa có implementation/evidence đủ để nâng trạng thái |
| `IN_PROGRESS` | Đang thực hiện; ghi phần xong, phần còn thiếu và ngày cập nhật |
| `DOC_VERIFIED` | Deliverable là tài liệu/config draft, đã kiểm tra ở mức tài liệu; không chứng minh runtime chạy |
| `IMPLEMENTED` | Có code/deliverable thực; acceptance tests chưa hoàn tất |
| `OFFLINE_VERIFIED` | Checks/fixtures phù hợp đã pass; chưa chứng minh live access/coverage |
| `LIVE_VERIFIED` | Có pilot thật trong scope/window/limits và evidence đối chứng |
| `ACP` | Đã đạt toàn bộ điều kiện của task, có evidence và người review ghi nhận |
| `BLOCKED` | Đã xác định blocker thực tế; ghi lỗi, ảnh hưởng, điều kiện mở khóa và việc vẫn làm được |

Đối với docs/config draft, DOC_VERIFIED là kết quả của deliverable đó; tính năng liên quan vẫn PLANNED. Không cần live gate cho task thuần tài liệu/refactor, nhưng adapter acquisition phải có offline và live evidence trước ACP. Chưa có tài nguyên hoặc dependency chưa xong được ghi ở cột phụ thuộc; không tự coi mọi task là BLOCKED.

Khi nâng trạng thái, điền **ngày, implementation reference, test/report reference, kết quả thực tế và reviewer**. Không chép secret, session, raw DROP content vào TODO/evidence. Role mặc định: Engineering triển khai, QA kiểm tra; Ops xác minh nguồn/pilot; Data/AI phụ trách taxonomy/model/evaluation. Chưa gán cá nhân hoặc ngày hoàn thành giả định.

## 3. Chuẩn bị đã có

Các kết quả dưới đây là evidence hiện có, không phải test runtime mới được chạy bởi lần tạo TODO.

| ID | Công việc / map | Trạng thái | Kết quả / evidence hiện có | Điều kiện ACP của task |
| --- | --- | --- | --- | --- |
| PREP-01 | Tạo venv, cài collection requirements | OFFLINE_VERIFIED | Python 3.13.13; [dependencies](docs/baseline/dependencies.txt), [manifest](docs/baseline/manifest.json); venv vẫn tồn tại | Interpreter/dependencies dùng được; import collector không auto crawl; optional models/media ghi thiếu rõ; reviewer xác nhận |
| PREP-02 | Baseline hành vi legacy | OFFLINE_VERIFIED | [Manifest](docs/baseline/manifest.json): schema/retry selfchecks, demo, compile 11 files, import sáu collectors và Bash syntax pass; [demo synthetic](docs/baseline/demo.json) | Có kết quả/hash tái đối chiếu được; không coi synthetic thành live; dùng baseline này kiểm tra refactor |
| PREP-03 | Audit, gap và kế hoạch refactor | DOC_VERIFIED | [Audit](docs/current-architecture-audit.md), [gap](docs/prd-to-code-gap-analysis.md), [refactor](docs/refactor-plan.md), [roadmap](docs/implementation-plan.md) | Mapping reuse/gap/dependency rõ; preserve CLI/schema cũ; không claim feature đã implement |
| PREP-04 | Seed Registry/Watchlist/Keyword/Exclusion — FR-01/02/06 | DOC_VERIFIED | [Config](config/README.md), [registry contract](specs/contracts/source-registry.md), [rule](specs/contracts/exclusion-rules.md); bảy nguồn vẫn disabled | YAML/reference/type checks pass; tên có provenance; unknown access/context giữ rõ; rule DROP không nhầm keyword thành intent |
| PREP-05 | Specs ba tính năng + shared adapter/queue | DOC_VERIFIED | [Specs index](specs/README.md): 56 local links, bốn JSON/YAML samples và mappings đã kiểm tra; 29 requirements/64 cases được đặc tả | Docs nhất quán, links/examples hợp lệ, requirement có acceptance; runtime vẫn PLANNED; reviewer xác nhận scope |

## 4. Tài nguyên và feasibility sớm

Ưu tiên **P0**, Ops + Engineering. Feasibility có thể thực hiện trước structural refactor; production feature integration phải qua gate BASE-03. Những việc này không tự triển khai adapter production.

| ID | Công việc / spec | Phụ thuộc | Trạng thái | Kết quả hiện tại | Điều kiện ACP |
| --- | --- | --- | --- | --- | --- |
| RES-01 | Chuẩn bị Playwright Chromium, profile riêng và bootstrap login theo [adapter contract](specs/contracts/source-adapter.md) | PREP-01/05 | IN_PROGRESS | 2026-10-08: browser tier installed; hai LOCAL_SMOKE_PASSED; khóa/cleanup offline pass; lệnh login có, manual session/reuse chưa verified. [Runbook](docs/operations/browser-bootstrap.md) | Chromium launch được; Facebook/TikTok profile tách dưới sessions; login thủ công; credentials không vào config/log/fixtures |
| RES-02 | Xác minh metadata/public access bảy group theo [Registry](specs/contracts/source-registry.md) | PREP-04, RES-01 | IN_PROGRESS | All seven public/manual access confirmed; disabled preserved. Project browser now runs: last probe group 1675953926771851 LOGIN_REQUIRED. [Probes](docs/operations/acquisition-live-probes.json) | Ghi từng nguồn public/private/unavailable/auth-required với ngày/method; không suy project/location; chỉ nguồn đạt gate mới được bật |
| RES-03 | Chuẩn bị SerpApi credential local và quota thử theo [Google spec](specs/features/google-social-discovery.md) | PREP-05 | BLOCKED | Key is present but one real SerpApi request returned INVALID_KEY; one attempted request retained in budget ledger. Need a valid local key. [Probes](docs/operations/acquisition-live-probes.json) | Key qua env ref; test request có sanitized response/usage; giới hạn 20/run, 200/tháng được giữ; không auto paid renewal |
| FEAS-01 | Pilot khả năng đọc một group public — FB-001/003/005 | RES-01/02 | BLOCKED | Project Chromium probe executed; latest group 1675953926771851 LOGIN_REQUIRED, no full-item sample/window evidence. [Probes](docs/operations/acquisition-live-probes.json) | Có group public accessible và ít nhất một item đối chứng text/ID/time trong bounded window; blocked source ghi outcome thật |
| FEAS-02 | Pilot riêng keyword và hashtag TikTok — TT-001/002/003 | RES-01 | BLOCKED | Both interfaces actually probed: keyword CAPTCHA; hashtag LISTING_SELECTOR_MISMATCH. Need accessible session then layout/extraction validation. [Probes](docs/operations/acquisition-live-probes.json) | Hai mode UI riêng được thử; sample video/query/order/limits và missing fields có evidence; không dùng Google thay TikTok search |
| FEAS-03 | Pilot Google cho Facebook/TikTok/YouTube — GG-001/002/003 | RES-03 | BLOCKED | One actual API probe attempted, INVALID_KEY. No valid response or three-platform live discovery acceptance. [Probes](docs/operations/acquisition-live-probes.json) | Ba target queries exercised; URL/snippet/position và request count ghi thật; empty có evidence, không claim full social coverage |

Nếu access/credentials không khả thi, cập nhật task feasibility thành BLOCKED hoặc ghi outcome bị hạn chế; vẫn tiếp tục docs, refactor và offline fixtures không phụ thuộc chúng. Không bypass block để đạt ACP.

## 5. Nền tảng refactor và contract

Ưu tiên **P0**, Engineering + QA. BASE deliverables đã có; module paths của CORE tasks vẫn là đích implement.

| ID | Công việc / spec | Phụ thuộc | Trạng thái | Kết quả hiện tại | Điều kiện ACP |
| --- | --- | --- | --- | --- | --- |
| BASE-01 | Internal PRD snapshot + legacy/canonical/evidence/LLM/export contracts; [inventory](specs/README.md) | PREP-03/05 | DOC_VERIFIED | 2026-10-08: [PRD snapshot](specs/product/prd.md) SHA khớp; [scope](specs/product/scope.md), năm data contracts và [17-FR matrix](specs/traceability/requirements-matrix.md) đã có; link/type/null/mapping docs checked, runtime mới PLANNED. [Evidence](docs/baseline/refactor-validation.json) | Snapshot nguyên PRD có provenance/hash; schemas/null/enums/mapping legacy-canonical rõ; requirements matrix đầy đủ 17 FR; không ghi tính năng hoàn tất |
| BASE-02 | Characterization sáu collector; [refactor plan](docs/refactor-plan.md) | PREP-02 | OFFLINE_VERIFIED | 2026-10-08: 13 tests pass trước/sau move; 10 supplemental tests pass trên frozen original và code mới. Outputs/file side effects/rerun/missing text/dedup/retry/partial covered, assertions giữ nguyên. [Before](docs/baseline/characterization-before.json), [suite](tests/characterization/test_collectors.py), [report](docs/refactor-summary.md) | Tests quan sát outputs/side effects, missing-text/dedup/error/rerun paths; không nới assertions để refactor pass |
| BASE-03 | Structural refactor src/engine và package entry points/CI; [refactor plan](docs/refactor-plan.md) | BASE-02 | OFFLINE_VERIFIED | 2026-10-08: six collectors/shared modules/runtime moved; cleanup đã bỏ 11 root wrappers và src/compat theo yêu cầu mới. 31 tests, module selfchecks, demo baseline, compile/import/CLI/Bash/wheel pass local 3.13. CI matrix configured, chưa chạy GitHub. [Summary](docs/refactor-summary.md), [cleanup evidence](docs/baseline/root-cleanup-validation.json); formal reviewer chưa ghi | Legacy JSON/state/data paths giữ nguyên; module CLI mới documented; src không import engine/root facade; six collectors không auto run khi import |
| CORE-01 | Canonical domain/types + SourceAdapter API — FR-04; [contract](specs/contracts/source-adapter.md) | BASE-01/03 | OFFLINE_VERIFIED | Typed candidate/API, UTC window/deadlines; acquisition schema implemented. Business canonical enrichment remains in SC tasks. [Evidence](docs/acquisition-implementation.md) | probe_access/discover/fetch_item có typed inputs/outcomes; candidate version/null/UTC đúng; snippet không giả full text; AD-AC-02/07 |
| CORE-02 | YAML loader, Registry, query builder và validation — FR-01/02; [Registry](specs/contracts/source-registry.md) | CORE-01 | OFFLINE_VERIFIED | Safe YAML loader, version/type/reference gates, nine sources/two watchlists, query builder and explicit verify/enable CLI. [Evidence](docs/acquisition-implementation.md) | References/types/versions/disabled gates pass; query original/effective rõ; aliases không fabricate identity; AD-AC-01 |
| CORE-03 | SQLite canonical records, observations, run/source state — FR-05/16; [adapter](specs/contracts/source-adapter.md) | CORE-01 | OFFLINE_VERIFIED | Separate transactional SQLite records/observations/runs/outcomes/queue; atomic crash rollback and persistent API budget. [Tests](tests/contract/test_acquisition.py) | Storage additive tách DB legacy; unique item + nhiều observations; crash/resume/rerun không duplicate; AD-AC-04/08/10 |
| CORE-04 | Browser manager, profile locks, deadlines và cleanup — FR-16; [adapter](specs/contracts/source-adapter.md) | BASE-03, RES-01, CORE-01 | OFFLINE_VERIFIED | Shared browser job/context cleanup; stable profiles and bootstrap lock, source/window leases, bounded navigation. Local DOM/persistence checks pass; platform session reuse pending. [Browser tests](tests/integration/test_acquisition_browser.py) | Một job/profile; bootstrap cũng khóa; context/lock release mọi exit; 120 giây/job và 1.200 giây/run; AD-AC-09/12 |
| CORE-05 | Prefilter runtime và rejection retention — FR-06; [exclusion](specs/contracts/exclusion-rules.md) | CORE-01/02/03 | OFFLINE_VERIFIED | Conservative intent prefilter; DROP prevents fetch/queue/raw persistence and retains seven audit fields. Complaint/mixed/ambiguous REVIEW. [Tests](tests/contract/test_acquisition.py) | Sales/recruitment/buy-sell/exchange rõ DROP; complaint/mixed giữ; không full-fetch/media/ASR/LLM/queue/raw persist khi DROP; AD-AC-05/06 |
| CORE-06 | URL/native identity + exact/near dedup — FR-05/12; [adapter](specs/contracts/source-adapter.md) | CORE-01/03 | OFFLINE_VERIFIED | Native/URL aliases, bounded allowlisted redirects, exact/near relationships; no empty-text identity merging. Alias/native resolution and rerun verified offline. [Report](docs/acquisition-implementation.md) | Alias/identity params giữ đúng; empty text không merge; nhiều query một item; near là relationship, không tự coi cùng incident; AD-AC-04/11 |
| CORE-07 | Engine manual run, fixed-window/rerun và source isolation — FR-04/16/17; [adapter](specs/contracts/source-adapter.md) | CORE-02/03/04/05/06 | OFFLINE_VERIFIED | Manual run/CLI, fixed-window observations, source isolation, counters/deadlines, JSON export; live pipeline acceptance pending. [Runbook](docs/operations/acquisition-runbook.md) | Window [start,end), end chốt một lần; new run ID giữ lineage; partial source không hủy source khác; true empty khác fail; AD-AC-02/03/07/08/10 |

## 6. Implement ba nguồn và Discovery Queue

Ưu tiên **P0**, Engineering + QA. Đây là trọng tâm acquisition v1 đã chốt; adapter không thay các collector legacy hoặc tự bật seed sources.

| ID | Công việc / requirement map | Phụ thuộc | Trạng thái | Kết quả hiện tại | Điều kiện ACP |
| --- | --- | --- | --- | --- | --- |
| SRC-FB | [Facebook group adapter](specs/features/facebook-adapter.md) — FB-001 đến FB-010 | BASE-03, CORE-01 đến CORE-07; FEAS-01 cho live | OFFLINE_VERIFIED | Public group browser discovery/fetch, scoped text expansion and comments isolation verified on synthetic DOM. Live probe LOGIN_REQUIRED; no full live item yet. [Report](docs/acquisition-implementation.md) | Thực hiện toàn bộ FB-AC-01 đến FB-AC-13: public gates, numeric/slug, text dài, pinned/time, missing media, prefilter, error/isolation; evidence live ở VER-02 |
| SRC-TT-KW | [TikTok KEYWORD_SEARCH](specs/features/tiktok-search.md) — TT-001/002/003/004/005/006/007/008/009 | BASE-03, CORE-01 đến CORE-07; FEAS-02 cho live | OFFLINE_VERIFIED | Independent keyword search implemented; Unicode/caption/metadata/dedup fixtures pass. Live keyword probe CAPTCHA. [Report](docs/acquisition-implementation.md) | Search UI video toàn query scope, không phụ thuộc accounts file; Unicode/window/metadata/quota/exclusion/dedup đúng; giữ old CLI; keyword pilot riêng |
| SRC-TT-TAG | [TikTok HASHTAG_SEARCH](specs/features/tiktok-search.md) — TT-001/002/003/004/005/006/007/009 | SRC-TT-KW, FEAS-02 cho live | OFFLINE_VERIFIED | Independent hashtag feed implemented, original query lineage preserved. Live hashtag probe LISTING_SELECTOR_MISMATCH; requires session/layout pilot. [Report](docs/acquisition-implementation.md) | Hashtag mode khác keyword mode; original # giữ lineage; validation hashtag; cùng video hai modes một canonical; toàn TT-AC-01 đến TT-AC-13 được cover giữa hai task |
| SRC-GG | [Google SerpApi discovery](specs/features/google-social-discovery.md) — GG-001/002/003/004/006/007/008/010 | CORE-01/02/03/05/06/07; RES-03 cho live | OFFLINE_VERIFIED | SerpApi organic discovery, six seed jobs, atomic 20/run and 200/month quota, typed errors. One live attempted request rejected invalid key. [Report](docs/acquisition-implementation.md) | engine=google, gl=vn/hl=vi, organic URL/title/snippet/position; one page; atomic request budget gồm retry qua restart; typed empty/error; GG-AC-01/02/05/06/07/08/09/10/12/13 |
| SRC-DQ | [Discovery Queue + review CLI](specs/contracts/discovery-queue.md) — GG-005/008, FR-01/05/16/17 | CORE-02/03/05/06/07 | OFFLINE_VERIFIED | SQLite queue/history; list/approve/reject/reopen/process CLI. New source draft disabled; explicit register/verify/enable/membership separate. [Runbook](docs/operations/acquisition-runbook.md) | PENDING/APPROVED/REJECTED + history; approve source mới vẫn disabled/unverified; explicit process chỉ sau gate; DQ-AC-01 đến DQ-AC-12 |
| SRC-ROUTE | [Google target routing](specs/features/google-social-discovery.md) — GG-004/005/008 | SRC-FB, SRC-TT-KW, SRC-GG, SRC-DQ, SRC-YT | OFFLINE_VERIFIED | Item/container and ready/pending gates; existing record observation without refetch; no implicit creator approval. [Tests](tests/contract/test_acquisition.py) | Item/container khác nhau; source outside watchlist vào queue; không auto crawl account/group; reused item thêm observation không refetch; GG-AC-03/04/10/14 |
| SRC-YT | [YouTube item bridge](specs/features/google-social-discovery.md) — GG-009 | BASE-03, CORE-01/02/03/05/06/07, SRC-GG/SRC-DQ | OFFLINE_VERIFIED | Bounded single-video yt-dlp metadata subprocess, channel identity check, no implicit transcript/media/ASR; unknown channel remains pending. [Report](docs/acquisition-implementation.md) | Approved known channel fetch đúng video; unknown channel pending; không whole-channel walk/implicit ASR; Google lineage giữ nguyên; GG-AC-11/12 |

Scope giữ nguyên: Facebook public groups; TikTok public keyword/hashtag videos; Google tìm Facebook/TikTok/YouTube links. Web article/News, Facebook Page/private group, followers/social graph và tự động dispatch ticket không thuộc acquisition v1.

## 7. Verification và ACP acquisition

Ưu tiên **P0**, QA + Engineering + Ops. Những task này thu evidence cho task implementation; không coi chúng là cách thay live bằng mock.

| ID | Công việc / map | Phụ thuộc | Trạng thái | Kết quả hiện tại | Điều kiện ACP |
| --- | --- | --- | --- | --- | --- |
| VER-01 | Offline acquisition/queue suites và compatibility | BASE-03, CORE-01 đến CORE-07, SRC-FB/SRC-TT-KW/SRC-TT-TAG/SRC-GG/SRC-DQ/SRC-ROUTE/SRC-YT | IN_PROGRESS | Acquisition behavioral and isolated Chromium DOM suites pass alongside legacy checks. Remaining fixtures/full 64-scenario acceptance mapping and live comparisons documented. [Validation](docs/baseline/acquisition-validation.json) | AD-AC-01 đến AD-AC-12; DQ-AC-01 đến DQ-AC-12; FB-AC-01 đến FB-AC-13; TT-AC-01 đến TT-AC-13; GG-AC-01 đến GG-AC-14 có test/result mapping; legacy gate pass; tests không gọi live trong CI |
| VER-02 | Pilot Facebook + hai TikTok modes + Google three targets | VER-01, FEAS-01/02/03, nguồn/profile/key ready | BLOCKED | Actual resource probes: Facebook LOGIN_REQUIRED; TikTok keyword CAPTCHA, hashtag selector mismatch; SerpApi INVALID_KEY. No full acquisition/window coverage verified live. [Probes](docs/operations/acquisition-live-probes.json) | Evidence thật từng mode/source/query; nonempty sample để xác minh extraction, true empty phân biệt lỗi; đối chứng window/limits/order; source failure isolation verified |
| VER-03 | ACP acquisition v1 / handover | VER-01/02 | PLANNED | Chưa đủ evidence nghiệm thu | Tất cả rows acquisition đạt scope gates, requirement→test→report rõ; missing/blocked nguồn ghi rõ; profile/key handling và quota verified; reviewer/date được ghi; không claim toàn-platform coverage |

**Checklist ACP acquisition:**

- [ ] Facebook lấy được item từ ít nhất một group public đã verified và bật đúng watchlist.
- [ ] TikTok keyword và hashtag có live evidence riêng; account filter/Google không dùng làm chứng minh thay thế.
- [ ] Google tìm đủ ba target types; URL mới vào queue, ready URL routing đúng, unknown channel không bị đoán.
- [ ] Không có full fetch/media/ASR/LLM/raw persistence cho clear prefilter DROP; mixed complaint giữ lại.
- [ ] Rerun/overlap/multi-query chỉ một canonical item, đủ observations; empty text không gộp unrelated items.
- [ ] Timestamp unknown/date-only không giả freshness; parser failure không giả no-new-data.
- [ ] API counters/locks/timeouts/retries và partial-source isolation có evidence pass.
- [ ] Evidence không có secret/session/raw DROP content; không bypass access/CAPTCHA.
- [ ] Reviewer ghi acceptance của đúng phạm vi; các nguồn unavailable giữ outcome riêng.

## 8. SmartCity downstream sau acquisition

Các task dưới đây nằm trong PRD/kế hoạch tổng thể, **không phải implementation đã được tạo bởi bộ specs adapter**. Các decisions ngoài acquisition như provider LLM, lịch chiều, reviewer/SLA và retention còn cần chốt trong task tương ứng.

| ID / ưu tiên | Công việc / map | Phụ thuộc | Trạng thái | Kết quả hiện tại | Điều kiện ACP |
| --- | --- | --- | --- | --- | --- |
| SC-01 / P0 | Dictionaries + operational relevance/taxonomy — FR-02/06/09/10; [gap](docs/prd-to-code-gap-analysis.md) | BASE-01, CORE-02/05, VER-03 | PLANNED | Có seed terms; chưa classifier/taxonomy runtime | Bốn domains + bảy congestion/sáu complaint subcategories đúng; project/location grounded; full negative filtering gồm PRD signals ngoài user rule; cases relevant/irrelevant/mixed pass |
| SC-02 / P0 | Unified MediaResolver — FR-07/11; [roadmap](docs/implementation-plan.md) | BASE-01, VER-03 | PLANNED | Có caption/ASR helpers legacy; models/FFmpeg chưa setup | Caption→ASR→visual khi cần với limits/provenance/vi; unavailable không mất candidate; evidence level đúng processing thật; media fixtures và live sample pass |
| SC-03 / P0 | LLM provider/config/output validation — FR-08/09/10/11; [roadmap](docs/implementation-plan.md) | BASE-01, SC-01/02 | PLANNED | Chưa có operational LLM adapter/model/key evidence | Chốt provider/model/budget; strict enums/JSON/confidence/grounding; retries hữu hạn; invalid/unavailable→REVIEW; không dùng quality_score legacy thay relevance confidence |
| SC-04 / P0 | Excel exporter bốn sheets — FR-13; [PRD](specs/product/prd.md) | BASE-01, CORE-03, SC-03 | PLANNED | Legacy chỉ JSON | Signals/Crawl_Runs/Source_Registry/Review đúng schema; DROP không Signals; zero run có headers; export failure rerun từ DB không recrawl/reenrich |
| SC-05 / P1 | Review/override workflow — FR-14 | SC-04, CORE-03 | PLANNED | Chưa có persisted overrides | Original/reviewed values, reviewer/time/note lưu lịch sử; feedback không chỉ nằm trong Excel; review/import/rerun không mất audit |
| SC-06 / P0 | Peak scheduler, manual rerun và reconciliation option — FR-03/15/17 | CORE-07, VER-03, SC-04 | PLANNED | Có Bash runner cũ; chưa SmartCity schedule | Chốt schedule/timezone/lịch chiều; fixed UTC windows + overlap locks; restart/rerun idempotent; late reconciliation P1 chỉ bật sau quyết định Ops; Windows pilot có cách chạy rõ |
| SC-07 / P0 | Monitoring/runbook end-to-end — FR-16, NFR | CORE-03/07, SC-02/03/04/06 | PLANNED | Có rotating logs legacy, chưa stage metrics | Counters acquisition/filter/media/LLM/export thật; partial/empty/fail riêng; latency/quota/error lineage; credentials redacted; operator recovery có evidence |
| SC-08 / P0 | POC/MVP quality evaluation và ACP sản phẩm — PRD §4/7 | SC-01 đến SC-07, VER-03 | PLANNED | Chưa có labeled evaluation hoặc KPI baseline | Mẫu review tối thiểu 200, denominators/report/reviewer đầy đủ; targets dưới đây được đo; không lấy mock/import success làm product KPI |

Targets **đề xuất của PRD**, chưa đạt/chưa đo:

| Metric | Mục tiêu | Kết quả hiện tại |
| --- | --- | --- |
| KEEP precision trên ≥200 reviewed records | ≥80% | Chưa đo |
| Valid structured LLM output | ≥98% | Chưa đo |
| Duplicate leakage trong Excel | ≤5% | Chưa đo |
| Scheduled-run completion trong hai tuần pilot | ≥95% | Chưa đo |
| Video accessible có usable evidence | ≥80% | Chưa đo |
| Required URL/published time/run/domain/relevance completeness | ≥98% | Chưa đo |
| Excel sau close-window | ≤30 phút | Chưa đo |
| Configured accessible-watchlist coverage | ≥90% đối chứng sample window | Chưa đo; không áp cho toàn Google/TikTok search |

Guardrails ACP: không cố tình bypass access; không auto-accept project/location thiếu grounding; không lộ key/session; source lỗi không hủy toàn pipeline. Theo implementation contract, DROP phải bị loại khỏi Signals; PRD có tolerance metric nhưng không dùng để cho phép cố tình xuất DROP.

## 9. Thứ tự bắt đầu và lưu kết quả

Các việc có thể chạy song song là tài nguyên/feasibility và refactor characterization; production adapter integration phải qua BASE-03. Browser/Google/LLM credentials không cần đưa vào chat hoặc tài liệu.

- [x] PREP-01 đến PREP-05: có deliverables/bằng chứng nền tảng; chưa đồng nghĩa ACP sản phẩm.
- [ ] RES-01/02/03 và FEAS-01/02/03: chuẩn bị và kiểm chứng truy cập sớm.
- [x] BASE-01/02/03: contracts DOC_VERIFIED và compatibility refactor OFFLINE_VERIFIED local 3.13; formal ACP/CI remote còn riêng.
- [ ] CORE-01 đến CORE-07: runtime foundation và prefilter trước persist/deep processing.
- [ ] SRC-FB, SRC-TT-KW, SRC-TT-TAG, SRC-GG, SRC-DQ, SRC-ROUTE, SRC-YT: acquisition/routing.
- [ ] VER-01/02/03: offline → live → ACP acquisition.
- [ ] SC-01 đến SC-08: operational enrichment/reporting/scheduling → ACP POC/MVP.

Khi thực hiện một task, thêm kết quả vào cột tương ứng và ledger dưới đây. Report/evidence runtime có thể lưu dưới `docs/operations/` hoặc run artifacts được ignore; chỉ tạo Markdown link khi file thực sự tồn tại. Test output lớn/ảnh/candidate raw không nhồi vào TODO; links không được chứa credentials.

Mẫu điền cho mỗi task: **ID; date; owner; status trước/sau; output/code reference; command/test case IDs; expected; actual/counters; report/run reference; reviewer; remaining issue/next step**. Với BLOCKED cần thêm lỗi đã quan sát và điều kiện mở khóa, không chỉ ghi “thiếu API”.

| Ngày | Task ID | Trạng thái / kết quả | Evidence | Reviewer / ACP |
| --- | --- | --- | --- | --- |
| 2026-10-08 | PREP-01/02 | OFFLINE_VERIFIED: collection environment + legacy baseline; kết quả lịch sử audit | [Manifest](docs/baseline/manifest.json), [demo](docs/baseline/demo.json) | Chưa ghi reviewer/ACP formal trong tracker |
| 2026-10-08 | PREP-03/04 | DOC_VERIFIED: audit/plan/config draft; source access vẫn chưa verified | [Audit](docs/current-architecture-audit.md), [config](config/README.md) | Chưa ghi reviewer/ACP formal trong tracker |
| 2026-10-08 | PREP-05 | DOC_VERIFIED: năm specs mới + ba specs cập nhật; mappings/examples/links pass | [Specs validation note](specs/README.md) | Feature runtime PLANNED; chưa ACP |
| 2026-10-08 | BASE-01 | PLANNED → DOC_VERIFIED: PRD snapshot/provenance, data contracts, matrix đủ 17 FR | [Specs](specs/README.md), [validation](docs/baseline/refactor-validation.json) | Engineering kiểm tra tài liệu; reviewer ACP chưa ghi |
| 2026-10-08 | BASE-02/03 | PLANNED → OFFLINE_VERIFIED: 23 characterization + 8 architecture/profile cases, legacy selfchecks, exact demo baseline; code ownership src/engine và CLI preserved | [Summary](docs/refactor-summary.md), [validation](docs/baseline/refactor-validation.json) | Engineering tự kiểm tra; formal reviewer/ACP và GitHub matrix chưa ghi |
| 2026-10-08 | RES-01 | PLANNED → IN_PROGRESS: Playwright/Chromium installed, hai profiles local smoke pass; manual login/reuse chưa verified | [Runbook](docs/operations/browser-bootstrap.md) | Chưa live/session ACP; CORE-04 browser manager vẫn PLANNED |
| 2026-10-08 | RES-02/03, FEAS-01/02/03 | PLANNED → BLOCKED tại resources: browser unavailable/list=[], SerpApi key absent; chưa live navigation/API call | [Feasibility](docs/operations/source-feasibility.md) | Mở khóa bằng browser connection/local API key; offline BASE vẫn đã hoàn tất |
| 2026-10-08 | BASE-03 cleanup | OFFLINE_VERIFIED: bỏ root Python wrappers/src/compat, direct imports/module commands; cập nhật runner/CI/package/docs; 31 tests, schema/X retry, demo baseline, compile/Bash/CLI/wheel pass | [Cleanup validation](docs/baseline/root-cleanup-validation.json) | Lệnh/import root cũ đã thay theo yêu cầu người dùng; data contract không đổi; formal ACP chưa ghi |
| 2026-10-08 | RES-01 profile path | IN_PROGRESS: cố định profile/browser binaries theo repository root, in đường dẫn profile và giải thích mỗi lượt mở trang chủ; 4 profile tests pass. Người dùng chưa đăng nhập, chỉ thấy tab group không được khôi phục | [Profile](src/browser/profiles.py), [bootstrap](engine/browser_session.py), [tests](tests/contract/test_profiles.py) | OFFLINE_VERIFIED sửa đường dẫn; chưa kiểm chứng login/session reuse nền tảng |
| 2026-10-08 | RES-02 | BLOCKED → IN_PROGRESS: xác nhận thủ công cả 7 group public/truy cập được; cập nhật metadata, giữ nguồn disabled | [Registry](config/sources.yaml), [xác nhận](docs/operations/facebook-source-verification.md) | DOC_VERIFIED metadata; chưa LIVE_VERIFIED/ACP; còn login/session và adapter probe |
| 2026-10-08 | CORE-01..07 / SRC-* | IMPLEMENTED + OFFLINE_VERIFIED for tested behavior: new acquisition CLI/adapters/storage/queue; full scenario/live ACP still pending | [Implementation](docs/acquisition-implementation.md), [validation](docs/baseline/acquisition-validation.json) | Engineering checks; VER-01 incomplete scenarios, VER-02 resource blocks, no formal ACP |
| 2026-10-08 | FEAS-01/02/03 | Actual Chromium/API probes: Facebook LOGIN_REQUIRED; TikTok CAPTCHA/selector mismatch; SerpApi INVALID_KEY (1 attempt) | [Probes](docs/operations/acquisition-live-probes.json) | No full-item live evidence; source enable flags preserved |

Khi tài liệu cũ có thứ tự Facebook Phase 9 hoặc Web provider chưa chốt, dùng quyết định acquisition mới trong [specs README](specs/README.md): feasibility Facebook/TikTok làm sớm; Google v1 chỉ social discovery; integration sau compatibility refactor. Đừng đổi trạng thái hoàn thành chỉ để khớp tên phase.
# Kho dữ liệu và đánh giá (09/10/2026)

**Yêu cầu mới ưu tiên:** [group tracing v2](specs/features/facebook-group-tracing.md) / [conversation schema](specs/contracts/conversation-record.md). Cần lưu raw bài/comment/reply rồi phân loại, kể cả comment mới trên bài cũ. Các kết quả purge/prefilter bên dưới là lịch sử v1; không đại diện cho chính sách lưu raw mới. Bảng GT-T01–07 cuối file là công việc tiếp theo; chưa triển khai comments.

OCR ảnh bài Facebook đã có runtime ngày 10/10/2026. Xem [runbook và bằng chứng](docs/operations/facebook-image-ocr.md); trạng thái nghiệm thu từng increment tại OCR-T01–07 bên dưới.

- [x] Mở rộng rule bổ sung nhân sự/xin việc; lệnh dọn tuyển dụng đã lưu và chặn identity đã loại khi rediscovery thiếu caption.
  - Kết quả dọn kho thực: xóa 2 bản ghi và 2 queue entries; còn 27 bản ghi, Excel đối chiếu đủ 27 dòng. Dry-run lặp lại không còn tuyển dụng rõ intent; 79 contract tests pass. Còn 15 bản ghi thiếu nội dung chưa thể phân loại tuyển dụng.
- [x] Tách cột Đánh giá / Ghi chú; xuất Excel toàn bộ kết quả theo bộ lọc, gồm trạng thái và ghi chú đã lưu.
- [x] Tab riêng xem nội dung được giữ qua tất cả lượt crawl; phân trang và lọc group/nguồn, nền tảng, ngày thu thập/ngày đăng, lượt crawl, trạng thái đánh giá.
- [x] Đánh giá và ghi chú lưu riêng trong SQLite; giữ khi rediscovery, chuyển identity khi hợp nhất alias; purge khi DROP.
- [x] Kiểm thử lưu qua nhiều run, thiếu timestamp, ngày Việt Nam, pagination, validation và rule DROP; kiểm thử hồi quy dashboard/acquisition.
- [ ] Acceptance nghiệp vụ: người dùng đọc nội dung và thử lưu đánh giá trên dữ liệu thực.

## Mở rộng phản ánh khách hàng theo dự án ngày 09/10/2026

### Increment triển khai VinWonders Vũ Yên

- OFFLINE_VERIFIED: config/projects.yaml; matcher tên/bí danh/hashtag, context nguồn tách khỏi project fact; selector search/crawl/lịch/library; Excel thêm Dự án và match status; rule bán vé và protected refund complaints. [Runbook](docs/operations/project-filter.md), tests `test_projects`, `test_project_dashboard`.
- LIVE_VERIFIED cho **truy cập mẫu nguồn**: cả 7 group người dùng cung cấp hiển thị public và adapter đọc được native item mẫu, [probes](reports/vinwonders-source-probes-20261009.json). Đã bật và gắn nguồn riêng theo dự án; chưa xác nhận full-window coverage hay classifier phản ánh khách hàng.
- Chưa ACP toàn bộ PF-T01–07: project override/history, classifier complaint đầy đủ và pilot đối chứng vẫn theo plan. Không coi project label là kết luận phản ánh đã được xác minh. Lịch dự án chỉ thay đổi khi người dùng lưu selection.

Spec: [Project customer feedback filter](specs/features/project-customer-feedback-filter.md). Trọng tâm phản ánh khách hàng do người dùng xác nhận; tất cả task dưới đây **PLANNED**, chưa có kết quả runtime/ACP. Mục tiêu phản ánh/ngày và ngưỡng chất lượng cần chốt riêng cho pilot nhiều dự án.

| ID | Công việc / requirements | Trạng thái | Kết quả hiện có / phụ thuộc | Điều kiện ACP |
| --- | --- | --- | --- | --- |
| PF-T01 | Chốt danh mục dự án, alias, địa phương — PF-001 | PLANNED | Có plan; chờ dự án pilot từ người dùng | Curator/mentor xác nhận danh mục và cách phân biệt alias trùng |
| PF-T02 | Group khách hàng/cư dân và source mapping — PF-002 | PLANNED | Cần group phù hợp; 7 group công nhân không đại diện mọi khách hàng | Kiểm chứng public/access, duyệt và enable riêng; ghi nguồn chưa truy cập được |
| PF-T03 | Contract/config/migration đa dự án — PF-001/008 | PLANNED | Sau PF-T01; loader hiện chưa nhận project registry mới | Dữ liệu cũ/CLI tương thích, null/unknown và versions đúng; tests phù hợp |
| PF-T04 | Matcher dự án và complaint/exclusion — PF-003/004/005/006 | PLANNED | Sau contract và bộ nhãn đối chứng | PF-AC02–09 pass; evidence-grounded match, không loại protected complaint |
| PF-T05 | Query/run/scheduler theo selection dự án — PF-007/008 | PLANNED | Sau PF-T02/03/04 | PF-AC01/10/12 pass; group chung crawl một lần, không nhân quota hoặc tạo duplicate |
| PF-T06 | Table, review dự án/vấn đề và Excel — PF-009 | PLANNED | Sau schema và matcher | PF-AC11/13 pass; lưu override/history, export khớp UI và một dòng/item |
| PF-T07 | Reprocess kho và pilot đối chứng — PF-001–009 | PLANNED | Sau các task trên và reviewer được xác nhận | Pilot báo coverage/sample/window/quota; đo precision/recall trong mẫu; mentor duyệt ngưỡng/kết quả |



## OCR chữ trong ảnh bài Facebook ngày 09/10/2026

Spec: [Facebook image OCR](specs/features/facebook-image-ocr.md). Phạm vi ảnh đính kèm bài của nguồn đã duyệt; chưa OCR ảnh comments/replies hay khung hình video. Runtime đã triển khai, pilot thật có kết quả; chưa ACP toàn bộ vì chưa có tập đối chứng 30–50 ảnh và reviewer. Chính sách raw v2: DROP là nhãn phân tích, không purge caption/comment/OCR.

| ID | Công việc / requirements | Trạng thái | Kết quả hiện có / phụ thuộc | Điều kiện ACP |
| --- | --- | --- | --- | --- |
| OCR-T01 | Môi trường Tesseract/Python và fixture — OCR-003/004 | IMPLEMENTED / OFFLINE_VERIFIED | Tesseract 5.5.3, vie+eng, pytesseract/Pillow trong venv; test ảnh chữ Việt tự tạo chạy thật | Còn xây dựng tập 30–50 ảnh đối chứng thực tế |
| OCR-T02 | Resolver đúng ảnh bài/album — OCR-001/002 | IMPLEMENTED / LIVE_PARTIAL | Photo hydration đúng Story, loại shared story; pilot lấy 5 ảnh đúng bài, xử lý 3 theo quota | Còn đối chứng nhiều layout/album, ảnh expired/CAPTCHA |
| OCR-T03 | OCR/preprocess/timeout/quality — OCR-003/004 | IMPLEMENTED / LIVE_PARTIAL | OCR thật 3 ảnh Facebook, 1 ACCEPTABLE và 2 NEEDS_REVIEW; lỗi/EMPTY/UNAVAILABLE phân biệt | Chưa đo độ chính xác toàn tập/false drop |
| OCR-T04 | Contract/evidence/cache/raw retention — OCR-006 | IMPLEMENTED / OFFLINE_VERIFIED | Evidence bất biến, hash/config cache, caption/review giữ riêng, failed refresh giữ success, job/context stale khi OCR đổi | Raw v2 không purge theo DROP; nghiệm thu crash recovery rộng còn cần bổ sung |
| OCR-T05 | Nối project/intent filter và budget — OCR-005 | IMPLEMENTED / LIVE_PROVIDER_ERROR | Input có caption + 3 OCR evidence riêng; batching/schema/quote validation pass offline; Gemini pilot trả HTTP 503 | Cần response thật qua validation/storage thành công để LIVE_VERIFIED |
| OCR-T06 | UI, batch reprocess và Excel — OCR-007 | PARTIAL / OFFLINE_VERIFIED | Chi tiết ảnh/text/status, lọc OCR/keyword, Excel sheet evidence không cắt chữ; CLI reprocess từng bài | Chưa có nút/batch reprocess trên UI |
| OCR-T07 | Pilot live và đối chứng — OCR-001–007 | LIVE_PARTIAL / UAT_PENDING | Facebook browser thật đọc caption/comments và OCR; reports/ocr-live-pilot.json, ocr-live-image-post.json, ocr-classification-live-pilot.json | Cần tập mẫu/reviewer và phân loại live thành công; không tuyên bố crawl hết |

Thứ tự: T01 → T03; T02/T04 chuẩn bị độc lập → T05 → T06 → T07. Pilot đề xuất 30–50 ảnh offline, rồi 1–2 group trước khi mở rộng 7 group. Chưa cam kết độ chính xác hay lịch hoàn thành trước khi có baseline.

## Truy vết group đầy đủ bài/comment/reply — quyết định 09/10/2026

Specs: [workflow và UI](specs/features/facebook-group-tracing.md), [schema/storage](specs/contracts/conversation-record.md). **Ưu tiên trước OCR.** Thiết kế tài liệu đã có; tất cả task runtime dưới đây PLANNED, chưa có test pass/live/ACP. Dữ liệu đã purge trước đây cần thu lại, không phục hồi được bằng migration.

| ID | Công việc / requirements | Trạng thái | Kết quả hiện có / phụ thuộc | Điều kiện ACP |
| --- | --- | --- | --- | --- |
| GT-T01 | Contract node/thread/time/coverage + fixtures — GT-001/003/005/006 | PLANNED | Hai specs đã viết, links/IDs kiểm tra; cần fixtures đối chứng | UID tác giả khác content ID; GT-AC01/02/04/07 có expected rõ; reviewer duyệt semantics |
| GT-T02 | Raw storage, revisions/observations, migration và tách purge — GT-002/005/008 | OFFLINE_VERIFIED (P1 increment) | SQLite hiện chỉ post; cần backup/mapping/rollback | GT-AC04/06/09/11/13 pass; DROP không xóa raw v2, notes/CLI cũ còn đúng |
| GT-T03 | Parser full post/comment/reply, native ID, ngày và parent — GT-001/003/005 | PLANNED | Browser/profile Facebook có sẵn; chưa parser comments | GT-AC01/02/03/05/07/09; reply pagination, URL fallback và extraction errors đúng |
| GT-T04 | Inventory/backfill, quét bài cũ, checkpoint/coverage — GT-004/006 | PLANNED | Sau T02/03; không dùng giới hạn tuổi bài làm cutoff | GT-AC05/06/08/10; resume không mất dữ liệu; gap inventory công khai; không success rỗng |
| GT-T05 | Filter từng node/context + reprocess + nối lịch — GT-002/003/004 | PLANNED | Sau T02–04; rule cũ chuyển thành nhãn view | GT-AC01/03/08/11; parent DROP không loại complaint child; lịch không chồng profile; raw giữ khi đổi rule |
| GT-T06 | Tab thu thập/kho gốc/phản ánh, thread detail và Excel — GT-007 | PLANNED | Sau schema/API v2; UI hiện post-only | GT-AC11/12; bảng UID/Tên/Date/Comment/URL, type/group/project/review/notes; filter ngày node, export toàn bộ khớp UI |
| GT-T07 | Offline regression + pilot 1–2 group + ACP — GT-001–008 | PLANNED | Sau các task trên; cần tập permalink đối chứng và reviewer | GT-AC01–14 có kết quả; old post/new comment thật; missed/coverage báo rõ; không tuyên bố 100% Facebook |

Thứ tự: T01 → T02 → T03 → T04 → T05/T06 → T07. Không tự bắt đầu crawl toàn watchlist hoặc thay lịch khi chỉ viết specs. Resources: profile/Chromium hiện có, quyền đọc comments trên group, tập đối chứng; không cần SerpApi/Facebook API cho browser tracing. OCR triển khai sau kho gốc, không thay acceptance comments.

## Kế hoạch tổng thể raw → taxonomy → batched LLM → phản ánh

Checklist triển khai/ACP mới nhất: [Phase P0–P6](docs/phased-delivery-v2.md). SL-T01–07 lần lượt map P0–P6; P2 bao gồm lịch durable, lượt chốt 08:30/18:30 và catch-up khi restart/job bận. Khi thực hiện ghi result/evidence path, reviewer/date và acceptance ID Pn-ACxx; chưa có case mới pass. Ngưỡng quality ở P6 là đề xuất cần mentor chốt, không là kết quả hiện tại.

Tài liệu: [flow/kiến trúc/triển khai v2](docs/implementation-plan-v2.md), [taxonomy](specs/contracts/project-issue-taxonomy.md), [LLM batch](specs/contracts/llm-batch-classification.md). Đây là **epics tổng hợp**, GT tasks bên trên là công việc con, không tính hai lần. Tài liệu/links/IDs đã kiểm tra; runtime mới vẫn PLANNED, chưa API pilot/test/ACP.

| ID | Công việc và requirements | Trạng thái | Kết quả / phụ thuộc | Điều kiện ACP |
| --- | --- | --- | --- | --- |
| SL-T01 | Scope/taxonomy/provider/fixtures — TX-001–005, BC-006 | IN_PROGRESS | [Taxonomy v1](specs/taxonomy/v1/README.md) 1.0.0-draft.1 đã viết và kiểm tra cấu trúc; còn mentor approval, labelled fixtures, provider/model/budget | Catalog approved, mapping/examples rõ, dev/held-out samples tách; không ghi key trong tài liệu |
| SL-T02 | Kho raw và migration — GT-002/005/008 | VERIFIED (unified DB deployed; formal ACP pending) | [DB chung](docs/operations/unified-database-backfill.md), [merge report](reports/database-consolidation.json): raw/history/jobs/reviews preserved; 28 legacy FB records mapped; integrity/FK ok, backups retained | Gate tests kỹ thuật pass; DB riêng cũ bỏ sau backup; mentor ACP và recovery exercise sau promotion chưa ghi |
| SL-T03 | Comments/replies và old-post coverage — GT-001/003/004/006 | IN_PROGRESS (posts/comments/replies live; full coverage unverified) | [Backfill 14 ngày](reports/facebook-backfill-14-days-summary.json), [runbook](docs/operations/unified-database-backfill.md): 14 group dùng browser/profile Facebook; nhiều lượt cùng window, dedup identity, raw trước filter, inventory pending được đọc bổ sung | GT-AC01–10 còn cần tập đối chứng old post/new comment và coverage đầy đủ; đã thử mọi permalink trong inventory không đồng nghĩa đã lấy hết group/comments |
| SL-T04 | Taxonomy loader/project/context builder — TX-001–005, BC-001 | IN_PROGRESS (saved-node context/input offline) | Sau T01/02; reuse project matcher, không keyword gate | TX-AC01–06; target/context có provenance, ambiguous project không silent DROP |
| SL-T05 | Batch queue/provider/validator/reprocess — BC-002–006 | IN_PROGRESS (Gemini worker/API single-item live verified) | Sau T04; API details chờ xác nhận | BC-AC01–07; token/output budgets, IDs/evidence, retry/lease/cache/context-version, raw usable khi API lỗi |
| SL-T06 | UI/thread/table/Excel và nối lịch — GT-007, BC-005 | IN_PROGRESS (dashboard raw v2, schedule route, comment filters/review/Excel verified; tree UI pending) | [Runbook](docs/operations/dashboard-raw-v2.md): 184 contract + 2 Chromium fixture tests; live 6 comments, raw retained and classifier connected | Raw/phản ánh tách; ngày node đúng; pending/stale rõ; notes/export khớp; đầy đủ coverage/thread UI và formal ACP chưa nghiệm thu |
| SL-T07 | Regression + pilot + ACP — GT/TX/BC | PLANNED | GT-T07; sau các service/UI, reviewer và API resources | Báo coverage/missed/precision/recall/cost/latency trên tập đối chứng, mentor ACP; không tuyên bố 100% toàn group |

Thứ tự P0–P6 trong plan; ưu tiên pipeline text trước OCR và gom vụ việc. Chưa cam kết thời gian hoàn thành trước khi đo parser comments/API. Tiêu chí chức năng dựa GT-AC01–14, TX-AC01–06, BC-AC01–08; chưa có kết quả runtime cho bộ này.

## P0 — Bàn giao taxonomy version 1

| Task | Trạng thái | Kết quả | Còn cần để ACP |
| --- | --- | --- | --- |
| P0-TX01 — Definitions và per-project profiles | DOC_VERIFIED (DRAFT) | [README](specs/taxonomy/v1/README.md), common.yaml và hai profiles: 17 shared issues, 16 enabled mỗi scope; [structural validation](reports/p0-taxonomy-v1-validation.json) | Mentor duyệt definitions/priorities/scope, chưa là runtime OFFLINE_VERIFIED |
| P0-TX02 — Xác nhận business scope và project semantics | IN_PROGRESS | Người dùng chấp nhận scope baseline; [progress](docs/operations/p0-taxonomy-progress.md), mở rộng an toàn/lao động còn review | Approved snapshot/registry VinCons và phạm vi bổ sung chốt, không coi VinCons là một site |
| P0-TX03 — Golden/held-out labels | IN_PROGRESS | [26 synthetic golden cases](tests/fixtures/taxonomy_v1/README.md), validator/CLI; 8 taxonomy + 6 architecture tests pass trong venv; [report](reports/p0-taxonomy-fixtures-validation.json). Held-out template rỗng | Reviewer xác nhận labels, human held-out riêng; không coi validation cấu trúc là accuracy |
| P0-API01 — Provider/model/limits/budget | IN_PROGRESS | Người dùng chọn Gemini đang cấu hình; metadata offline/key-present kiểm tra, không in key hoặc gọi API; money budget DEFERRED_BY_USER | Gateway protocol/capability/token limits cần kiểm chứng trước integration; ngân sách không chặn task hiện tại |

### P0 input/output schema — increment đã triển khai

Kế hoạch thực thi mới nhất: [24 đầu việc và 14 live cases](docs/execution-and-live-acceptance-v2.md). V2 IDs là phân rã SL/GT, không cộng trùng khối lượng. P1 đã có offline evidence; P2/P3/P4 có increment code, chưa nghiệm thu đầy đủ. Native Facebook pilot LIVE-01 lỗi parser; các live cases khác NOT_RUN. Xem [trạng thái triển khai và lệnh chạy](docs/operations/v2-implementation-progress.md), [report tổng 164 contract tests](reports/v2-implementation-validation.json). Không coi nút crawl v1 là pilot workflow v2.

- P0-SC01 **OFFLINE_VERIFIED**: [hai JSON schemas + validator](docs/operations/classification-contract-v2.md), taxonomy attachment, item/revision/candidate/evidence references và strict/partial response modes; [examples](examples/classification-v2/request.json).
- 34 tests pass (20 classification contract, 8 taxonomy, 6 architecture), [report](reports/p0-classification-contract-validation.json). Không có LLM live call hoặc classifier accuracy claim.
- Ngân sách API **DEFERRED_BY_USER**: không tiếp tục yêu cầu budget để làm schema. Protocol/token capability và provider worker vẫn ở phase API; money-budget implementation làm sau.
- P0 human held-out/reviewer validation còn pending; raw-storage P1 chưa triển khai trong increment schema này.

Không bật taxonomy draft trong acquisition/LLM, không thay .env/schedule/DB. Structural validation chỉ xác nhận tài liệu/YAML/references, không là kết quả classification quality hoặc acceptance của mentor.
# Increment lịch crawler v2 — 10/10/2026

- **VERIFIED cấu hình/dispatch:** `dashboard-schedule-v2`, raw `conversation-record-v2`, POST/COMMENT/REPLY; migrate lịch v1 giữ cấu hình người dùng. Lượt chốt 08:30 bổ sung để không bỏ phần 08:00–08:30 khi chu kỳ 45 phút. Task scheduled closing ghi final_tick; lịch và crawl thủ công vẫn đi raw trước filter/classify.
- **Kiểm tra:** 30 contract tests và 2 Chromium fixtures pass, API lịch thật v2 đang enabled đúng hai khung, chu kỳ 45 phút. [Bằng chứng](reports/dashboard-schedule-v2-validation.json), [runbook](docs/operations/dashboard-crawl-schedule.md).
- **Live RUNNING, chưa nghiệm thu completion/coverage:** gỡ một lock tồn dư chỉ sau xác minh PID chủ đã chết và không có browser dùng profile; scheduler đã tự resume task chờ. Không coi cấu hình/dispatch pass là đã crawl hết dữ liệu trong khung.


## Triển khai kế hoạch tối ưu UX — 10/10/2026

- **FB-RECOVERY-CLS-01: LIVE_BROWSER_VERIFIED (bounded) / LIVE_API_VERIFIED / CONTINUOUS_WORKER_ACTIVE; COVERAGE + QUALITY_UAT_PENDING** — 11/10: xử lý hết manifest 306 đầu vào trên 13 nguồn, phục hồi 195 cùng identity, filter và phân loại hàng chờ đã được cho phép. Kho 2.969 node: 2.692 DONE (90,67%), 166 FILTER_DROP, 111 MISSING_TEXT, không còn PENDING/RUNNING/FAILED hiện hành. 342 request HTTP 200; giữ analyses/reviews, không trùng ID hoặc thay parent. Cả 67 lỗi cũ đã DONE; 6 lỗi protocol phát sinh được xử lý ở lần thử cuối. Người dùng đã cho phép gửi dữ liệu mới/thay đổi trong tương lai; worker ACTIVE, giữ 2.692 DONE, đối soát không có job mới/API call. Coverage đầy đủ và accuracy chưa nghiệm thu. [Biên bản](docs/operations/facebook-recovery-classification-20261011.md), [bằng chứng worker](reports/classifier-continuous-enabled-20261011.json).

- **FB-PARSER-CAPTION-02: IMPLEMENTED / OFFLINE_VERIFIED + LIVE_BROWSER_VERIFIED (bounded)** — 11/10: xác nhận caption thật nằm ngoài role=article trong dialog; sửa chọn vùng bài và permalink comment tránh hidden reply anchor của cha. 21 kiểm thử parser đạt; 264/264 hồi quy đạt; live đọc caption 41 ký tự, reply 84 ký tự và đúng thời gian. Sau đó thu lại 306 đầu vào, phục hồi 195; OCR comment/reply và coverage đầy đủ còn chưa nghiệm thu. [Biên bản parser](docs/operations/facebook-parser-diagnosis-20261011.md), [thu lại/phân loại](docs/operations/facebook-recovery-classification-20261011.md).

- **CLS-OCR-REVIEW-01: IMPLEMENTED / OFFLINE_VERIFIED + SYNTHETIC_API_VERIFIED + LIVE_READ_VERIFIED + LIVE_API_VERIFIED; QUALITY_UAT_PENDING** — Truy vết 66 lỗi OCR dù HTTP 200; làm rõ điều kiện review target/bài cha, giữ strict validator và DONE hợp lệ. Health đếm node hiện hành, tách nhãn chờ/lỗi/thiếu/UNKNOWN, intent filter đồng bộ UI. 261/261 hồi quy đạt; giả lập 2/2 và hai mẫu thật 2/2. Sau quyền toàn hàng chờ, cả 66 lỗi OCR đã DONE; completion hiện tại hoàn tất, quality/UAT còn pending. Worker nền đã ACTIVE sau quyền chạy liên tục cho dữ liệu tương lai, không gọi lại API cho DONE còn hợp lệ. [Chẩn đoán](docs/operations/classification-diagnosis-20261011.md), [kết quả backlog](docs/operations/facebook-recovery-classification-20261011.md), [bằng chứng worker](reports/classifier-continuous-enabled-20261011.json).

- **CLS-MODEL-02: DEPLOYED / OFFLINE_VERIFIED + LIVE_VERIFIED (bounded)** — 11/10/2026: chuyển sang `ag/gemini-3.8-flash-low`, giữ DONE còn khớp đầu vào/binding qua đổi model; đối soát tạo 1.539 job và giữ 961 kết quả. 258/258 kiểm thử đạt, một lượt thật 10/10 nội dung được chấp nhận với 2 request HTTP 200. Dashboard đã nạp cấu hình mới, worker nền bật; completion toàn hàng chờ và chất lượng held-out chưa nghiệm thu. [Runbook](docs/operations/classification-worker.md#chuyển-model-và-giữ-kết-quả--11102026).

- **UXR-FILTER-RESET-01: IMPLEMENTED / OFFLINE_VERIFIED + LIVE_READ_VERIFIED**: sửa Xóa bộ lọc chỉ reset form nhưng không tải bảng; nay tự đọc phiên mới, về trang 1, cập nhật URL, báo đang tải/thành công/lỗi và giữ nháp. 13 kiểm thử contract/browser đạt; xác nhận trên dashboard thật desktop/mobile. [Luồng và bằng chứng](docs/operations/reflections-workspace.md#xóa-bộ-lọc).

- **UXR-REFL-01: IMPLEMENTED / OFFLINE_VERIFIED + LIVE_READ_VERIFIED**: tổ chức lại tab Phản ánh theo tác vụ duyệt, bộ lọc nghiệp vụ chính, taxonomy/ý định/kết quả/trạng thái riêng; chuyển lọc kỹ thuật về Kho dữ liệu, danh mục/validation từ backend. Sửa scope dự án theo nguồn, số đếm OCR và race khi khôi phục/xóa bộ lọc. 255/255 hồi quy đạt, desktop/mobile/Excel đã kiểm chứng. [Runbook và ánh xạ bộ lọc](docs/operations/reflections-workspace.md).

- **UXR-SOURCE-01: IMPLEMENTED / LIVE_READ_VERIFIED**: tách cột Nguồn và Nội dung ở Phản ánh/Kho dữ liệu, nhãn riêng trên mobile; link group và link bài không bị trộn.
- **CLS-RECON-01: IMPLEMENTED / OFFLINE_VERIFIED + LIVE_LOCAL_VERIFIED**: phân biệt thiếu đầu vào, kết quả cũ, chưa có job, đang chờ và lỗi; `--prepare-only` đối soát không gọi API. Đã bổ sung 1.147 job hiện tại, 298 nội dung thiếu văn bản được giữ riêng. 252/252 kiểm thử đạt.
- **CLS-RECON-02: LIVE_PROVIDER_ERROR / UAT_PENDING**: model vẫn HTTP 503 với câu thử tối thiểu; chưa nghiệm thu độ chính xác hoặc completion hàng chờ. [Kiểm tra và hướng dẫn](docs/operations/classification-miss-audit-20261010.md).

- **UXR-01…22: IMPLEMENTED / OFFLINE_VERIFIED**, triển khai dashboard, giữ database/profile/lịch. Chi tiết contract, lựa chọn localStorage cho nháp và rollback: [runbook](docs/operations/dashboard-workspace.md).
- **UXR-23: OFFLINE_VERIFIED + LIVE_READ_VERIFIED**; 238 test được thu thập (222 pass, 16 opt-in skip), 5 browser fixture đã chạy riêng; lượt targeted cuối 11 tests gồm 6 contract + 5 browser. Không cộng các lượt lặp thành số test riêng.
- **UXR-24: DEPLOYED / UAT_PENDING**. Live-read kiểm tra bảng/detail/Excel trên 2.241 nội dung, lịch giữ 05:00–08:30 và 17:00–18:30, 45 phút. Phản hồi thao tác/mentor, screen reader và zoom 200% đầy đủ chưa được tự nghiệm thu.
- [Validation](reports/workspace-validation.json), [live-read](reports/workspace-live-read-validation.json), [hiệu năng](reports/workspace-performance-final.json), [ảnh desktop](reports/workspace-desktop.png), [mobile](reports/workspace-mobile.png).
- Không tuyên bố coverage Facebook đầy đủ, model accuracy hoặc điểm UX mới từ kiểm thử này.
- **CA2-READ-01: IMPLEMENTED / OFFLINE_VERIFIED + LIVE_LOCAL_VERIFIED**: sửa reconciliation giữ khóa ghi SQLite dài, giữ outbox đồng thời và idempotency; giới hạn chờ request giao diện 30 giây. Bảng 3.070 nội dung đã đọc lại; worker và lịch giữ hoạt động. [Bằng chứng và giới hạn](docs/operations/ca2-dashboard-recovery-20261011.md).
- **UXR-PLATFORMS-02: IMPLEMENTED / OFFLINE_VERIFIED + LIVE_LOCAL_VERIFIED** — Đồng bộ nguồn/nền tảng, health mọi tab, lịch sử/query coverage, bộ lọc và chi tiết. Lịch Threads nhiều dự án chạy tuần tự; đã lưu VinCons + Vũ Yên, hai ca/45 phút. Contract 255 (254 pass, 1 skip), Chromium desktop/mobile đã kiểm chứng. Chất lượng VinCons, full coverage và lịch nhiều ngày còn pending. [Kết quả](docs/operations/workspace-platforms-20261012.md).
