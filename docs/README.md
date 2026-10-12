# Chỉ mục tài liệu dự án

Đồng bộ ngày **12/10/2026**. Bắt đầu bằng [README dự án](../README.md), [trạng thái code/config](current-state.md), [bản bàn giao branch dev](development-handoff-20261012.md) và [UI đa nền tảng mới nhất](operations/workspace-platforms-20261012.md). [Audit 11/10](documentation-drift-audit-2026-10-11.md) là snapshot lịch sử.

## Tài liệu vận hành hiện hành

| Tác vụ | Tài liệu |
| --- | --- |
| Xem/đánh giá/xuất báo cáo | [Dashboard workspace](operations/dashboard-workspace.md), [bộ lọc Phản ánh](operations/reflections-workspace.md) |
| Crawl Facebook POST/COMMENT/REPLY | [Raw v2](operations/dashboard-raw-v2.md), [lịch hằng ngày](operations/dashboard-crawl-schedule.md) |
| Crawl Threads theo dự án / lịch nhiều dự án | [Threads runbook](operations/threads-acquisition.md), [luồng adapter](design/threads-adapter-flow.md) |
| Nguồn/nền tảng, lịch, ngày đăng/ngày thu | [UI và kiểm chứng 12/10](operations/workspace-platforms-20261012.md) |
| Chuẩn bị profile Facebook/TikTok | [Browser bootstrap](operations/browser-bootstrap.md) |
| Google discovery / CLI acquisition v1 | [Acquisition runbook](operations/acquisition-runbook.md) |
| Dự án/nguồn/query/taxonomy | [Config index](../config/README.md), [lọc dự án](operations/project-filter.md) |
| Gemini worker/model switch | [Worker](operations/classification-worker.md), [input/output v2](operations/classification-contract-v2.md) |
| Đọc chữ trong ảnh POST | [OCR runbook](operations/facebook-image-ocr.md) |
| DB chung / backfill đã chạy | [Migration và backfill](operations/unified-database-backfill.md) |
| Sáu collector legacy | [Legacy collectors](legacy-collectors.md) |
| Requirement/contract/acceptance | [Specs index](../specs/README.md), [requirements matrix](../specs/traceability/requirements-matrix.md), [TODO](../TODO.MD) |

## Plans và snapshots lịch sử

[Kế hoạch adapter Threads](implementation-plan-threads.md) là kế hoạch phase/acceptance; browser adapter, DB chung, query, lịch và workspace đã triển khai subset. Trạng thái hiện tại **IMPLEMENTED_SUBSET / LIVE_PARTIAL**; các gate chưa đạt giữ pending. Xem [runbook](operations/threads-acquisition.md), [feature spec](../specs/features/threads-adapter.md), [contract](../specs/contracts/multi-platform-conversations.md) và TODO.

[Thiết kế luồng Threads](design/threads-adapter-flow.md) và [thiết kế UX/UI](design/threads-workspace-ux.md) có implementation subset: chọn Facebook/Threads trong tab Thu thập, lịch/lượt riêng, DB chung, lọc/chi tiết/export theo nền tảng. Lịch Threads đã hỗ trợ nhiều dự án. Runtime có kiểm thử offline và pilot browser thật; full live/business acceptance chưa hoàn tất.

[Architecture/gap/refactor ngày 08/10](current-architecture-audit.md), [gap analysis](prd-to-code-gap-analysis.md), [refactor plan](refactor-plan.md), [refactor summary](refactor-summary.md), [acquisition increment ngày 08/10](acquisition-implementation.md) mô tả baseline theo ngày; những câu “chưa có runtime” không mô tả hệ thống hiện tại.

[Architecture v2](implementation-plan-v2.md), [phase gates](phased-delivery-v2.md), [WBS/live acceptance](execution-and-live-acceptance-v2.md) và [UXR plan](dashboard-ux-implementation-plan.md) giữ requirements/target gates. Raw/classifier/OCR/workspace đã có implementation subset; full live/business acceptance còn riêng.

[P0 taxonomy](operations/p0-taxonomy-progress.md), [P1 raw storage](operations/p1-raw-storage.md), [increment P2/P3](operations/v2-implementation-progress.md), resource/access/parser/UX audits là snapshot của lần kiểm tra ghi trong tài liệu. Đọc report có ngày cùng nguồn/window/limits; không suy test count, số dữ liệu, key validity hoặc tiến trình hiện tại từ số liệu cũ.

PRD snapshot trong `specs/product/prd.md` giữ nguyên byte/hash. Report/ảnh trong `reports/`, database/profile trong `sessions/` và artifacts `.impeccable/` là tài nguyên local, có thể thiếu khi clone; links code/config/contracts luôn trỏ vào repository.
