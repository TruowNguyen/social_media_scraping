# Trạng thái mã nguồn và cấu hình hiện hành

**UI đa nền tảng · 12/10/2026:** nguồn/nền tảng, bộ lọc, chi tiết, health và lịch sử đồng bộ backend. Lịch Threads hỗ trợ nhiều dự án, đã lưu VinCons + VinWonders Vũ Yên; giữ hai ca/45 phút. Snapshot mới có dữ liệu qua truy vấn VinCons; chất lượng/coverage chưa nghiệm thu. [Kết quả và giới hạn](operations/workspace-platforms-20261012.md).

**Threads: IMPLEMENTED_SUBSET / LIVE_PARTIAL · 12/10/2026.** Browser Playwright + Chrome dùng profile riêng đã search `VinWonders Vũ Yên`, lưu 43 nội dung thật (4 bài viết, 39 trả lời) vào DB chung trước filter/classify. Reader mixed v2/v3, registry/query versions, durable pages/ACK, Gemini batch, lịch Threads và UI/filter/export đã nối. [Runbook và limits](operations/threads-acquisition.md), [snapshot](../reports/threads-deployment-final.json), [TODO](../TODO.MD). Chưa chứng minh thu hết window/nested replies; API/OCR Threads/monitoring ba ngày chưa nghiệm thu. `RAW_V2_THREADS` là chế độ hội thoại Facebook, còn `/api/threads/` dùng đọc hội thoại đã lưu.

[Luồng adapter](design/threads-adapter-flow.md) và [UX/UI](design/threads-workspace-ux.md) đã triển khai phần browser + workspace. Facebook vẫn ghi repository trực tiếp, Threads qua spool; chưa daemon storage chung. Raw/reviews Facebook được đối soát với backup, không đổi identity của dữ liệu cũ.

Đối chiếu ngày **11/10/2026** tại repository `social_media_scraping`. Trang này mô tả code/config đã có; kết quả live được dẫn từ các báo cáo có ngày, không xác nhận lại trạng thái Facebook, API hoặc tiến trình đang chạy. [Biên bản đồng bộ tài liệu](documentation-drift-audit-2026-10-11.md) ghi các sai lệch đã sửa.

## Luồng đang được dashboard sử dụng

`Thu thập / lịch → inventory bài → quét thread đã biết → lưu POST/COMMENT/REPLY → OCR ảnh bài → filter từng node → hàng chờ Gemini → validate → analysis → Phản ánh / Kho dữ liệu / Excel`.

Code điều phối ở [dashboard.py](../engine/dashboard.py), [dashboard_conversations.py](../engine/dashboard_conversations.py), [conversation_worker.py](../engine/conversation_worker.py) và [group_tracing.py](../engine/group_tracing.py). Dashboard dùng `RAW_V2_THREADS`, `conversation-record-v2`, lưu raw trước filter/classify. `DROP` không xóa raw v2; intent của bài cha không loại bình luận/phản hồi của nó. Ngày đăng và tình trạng thiếu thời gian được xét riêng cho từng node.

Google/SerpApi là luồng discovery riêng. CLI acquisition v1 vẫn có prefilter trước fetch/persist và rejection audit bảy trường; policy đó không đại diện cho kho raw v2. Sáu collector legacy giữ schema và cấu hình riêng.

## Cấu hình và giới hạn

| Hạng mục | Trạng thái đối chiếu | Nguồn trong repository |
| --- | --- | --- |
| Facebook | 14 group `enabled=true`, `VERIFIED`, `access_verified=true`, `requires_login=true`; 7 VinCons + 7 Vũ Yên. Đây là cách vận hành bằng profile đã lưu, không chứng minh anonymous access | [sources.yaml](../config/sources.yaml), [projects.yaml](../config/projects.yaml) |
| Watchlist hoạt động | `vincons_acquisition_v1` ACTIVE/enabled, chứa 16 nguồn gồm 14 Facebook + Google bật + TikTok tắt. Watchlist seed trong `watchlists.yaml` vẫn DRAFT/disabled | [acquisition.yaml](../config/acquisition.yaml), [watchlists.yaml](../config/watchlists.yaml) |
| Phạm vi dự án | `vincons` là `ORGANIZATION_PORTFOLIO`, `vinwonders_vu_yen` là công viên; cả hai bật. Group chỉ cung cấp context | [Project Registry](../config/README.md), [lọc dự án](operations/project-filter.md) |
| Lịch dashboard | `dashboard-schedule-v2`; UI dùng DAILY_SLOTS, giờ Việt Nam UTC+7. Chu kỳ 45 phút có lượt chốt 08:30 và 18:30 | [runbook lịch](operations/dashboard-crawl-schedule.md), [scheduler](../engine/dashboard.py) |
| Crawl dashboard | Budget 1.200 giây/run; mỗi nguồn tối đa 120 giây và được chia theo budget còn lại; inventory tối đa 100 candidates, tối đa 20 threads/nguồn | [bridge](../engine/dashboard_conversations.py), [worker](../engine/conversation_worker.py) |
| Database mặc định | `sessions/acquisition/acquisition.sqlite3` dùng chung acquisition/Google, raw v2, reviews, jobs/analyses và workspace views | [DB migration/backfill](operations/unified-database-backfill.md) |
| Taxonomy runtime | `config/taxonomy/v1`: 1.0.0, APPROVED, runtime_enabled; provenance là người dùng chấp nhận baseline để triển khai | [runtime catalog](../config/taxonomy/v1/common.yaml), [worker](operations/classification-worker.md) |
| Taxonomy review | `specs/taxonomy/v1`: 1.0.0-draft.1, DRAFT/disabled; snapshot này vẫn dùng cho CLI/fixtures review | [draft taxonomy](../specs/taxonomy/v1/README.md) |
| Phân loại | Jobs/leases/retry/batching và gateway `/v1/chat/completions` đã implement. Model/base URL/key lấy từ GEMINI_MODEL/GEMINI_API_BASE_URL/GEMINI_API_KEY; worker `--serve` mặc định poll 15 giây | [worker](operations/classification-worker.md), [gateway](../src/analysis/gemini_gateway.py) |
| OCR | Tesseract vie/eng cho ảnh đính kèm POST; evidence/cache/provenance vào classifier, UI và Excel. Chưa OCR ảnh COMMENT/REPLY hoặc video | [runbook OCR](operations/facebook-image-ocr.md), [input/output contract](operations/classification-contract-v2.md) |
| Workspace | Bốn tab Phản ánh / Kho dữ liệu / Thu thập / Tìm link Google; phiên kết quả cố định, hội thoại, nháp local, versioned reviews, bulk review, Excel theo phiên | [workspace](operations/dashboard-workspace.md), [bộ lọc Phản ánh](operations/reflections-workspace.md) |

Cấu hình lịch đã lưu trên workspace tại lần đọc 11/10/2026: enabled, DAILY_SLOTS, 05:00–08:30 / 17:00–18:30, min=max=45, project_id trống. Đây là snapshot file local, không phải cấu hình mặc định của checkout mới hoặc bằng chứng scheduler/worker đang chạy. Server mới chưa có file lịch khởi tạo lịch tắt; ROLLING/FIXED còn được API hỗ trợ. Dashboard không tự khởi động cùng Windows và không đánh thức máy sleep.

`--conversation-db` của dashboard mặc định dùng cùng `--db`; nếu override thì worker phải trỏ đúng DB raw. Không chạy đồng thời nhiều backend cùng database/profile. Source tasks có lease/resume; CLI `enqueue-days`/`serve` có catch-up theo ngày chỉ định, còn dashboard ngoài khung không replay mọi tick đã lỡ.

Worker reconciliation giữ DONE result đã validated khi target/context/OCR/taxonomy/prompt/rule còn khớp dù model mặc định đổi; giữ model cũ trong provenance. Input/binding thay đổi tạo job mới; input chưa có result hợp lệ dùng model mới. `enqueue` trực tiếp vẫn có binding theo model để thử so sánh; [model switch ngày 11/10](operations/classification-worker.md) có evidence riêng.

## Bằng chứng và phần chưa nghiệm thu

- Acquisition/Registry/exclusion/queue có suites offline và báo cáo [implementation ngày 08/10](acquisition-implementation.md). Probe login wall/invalid key trong báo cáo đó là lịch sử.
- Facebook raw v2 có pilot comments và [backfill 14 ngày](operations/unified-database-backfill.md); coverage vẫn PARTIAL, không đủ bằng chứng mọi bài/comment/reply của mọi group đã được thu thập.
- Gemini có accepted-output pilots theo [runbook worker](operations/classification-worker.md). Ngày 11/10 có một lượt 10 nội dung thật chia 2 request (6 + 4), HTTP 200 và 10 accepted results trong [live-cycle report](../reports/model-switch-20261011-live-cycle.json). Chưa có held-out để xác nhận precision/recall hoặc full BC acceptance. HTTP 503 của pilot OCR cũ không tính là thành công.
- UI, reviews và Excel có kiểm thử, live-read và báo cáo [workspace](operations/dashboard-workspace.md). Export workspace không đồng nghĩa exporter `Signals/Crawl_Runs/Source_Registry/Review` của PRD v1 đã hoàn tất; canonical/unified-evidence/social-signal v1 vẫn là target contracts riêng.
- UAT người vận hành/mentor, screen reader thực tế, benchmark OCR, TikTok live acceptance, scheduling nhiều ngày và ACP sản phẩm còn pending. Money budget vẫn DEFERRED_BY_USER.

Report trong `reports/`, DB và profile trong `sessions/` là artifact local được ignore, có thể không tồn tại trong checkout mới. [TODO](../TODO.MD) giữ lịch sử increment và acceptance chưa đạt; [requirements matrix](../specs/traceability/requirements-matrix.md) phân biệt implementation subset với yêu cầu PRD đầy đủ.

## Kiểm tra lặp lại không gọi nền tảng/model

Chạy tại repository root bằng venv đã cài dependencies:

```powershell
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.acquisition_cli validate
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.taxonomy_cli
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.dashboard --help
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.conversation_cli --help
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.classification_worker --help
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.image_ocr_cli --help
.\.venv\audit\Scripts\python.exe -X utf8 -m unittest discover -s tests -q
```

Các browser fixtures opt-in bằng `ACQUISITION_BROWSER_TESTS=1`; mặc định bị skip. `classification_worker --prepare-only` không gọi model nhưng **ghi jobs vào DB**, nên không phải lệnh chỉ đọc để kiểm tra tài liệu.
