# Specs ownership và quy trình thay đổi contract

Đồng bộ ngày **11/10/2026**. `specs/` mô tả yêu cầu và contracts; trạng thái implementation hiện hành ở [code/config](../docs/current-state.md), [requirements matrix](traceability/requirements-matrix.md) và [TODO](../TODO.MD). Các acceptance cases là yêu cầu, không tự là case đã pass.

## 1. Trạng thái triển khai

| Phạm vi | Đã có | Phần chưa nghiệm thu |
| --- | --- | --- |
| Acquisition v1 / Registry / queue | Loader/gates, Facebook/TikTok/Google adapters, identity/observations, durable quota, review/dispatch CLI; [report offline](../docs/acquisition-implementation.md) | TikTok keyword/hashtag live acceptance, full acquisition ACP |
| Facebook conversation v2 | Raw-first POST/COMMENT/REPLY, revisions/context, inventory bài cũ, tasks/leases/resume, [dashboard bridge](../docs/operations/dashboard-raw-v2.md), DB chung | Coverage mọi group/comment/reply; pilot/backfill vẫn PARTIAL |
| Taxonomy | Review draft 1.0.0-draft.1 trong specs; runtime 1.0.0 APPROVED/enabled trong config, 17 shared issues và hai profiles | Mentor/held-out labels, scope lao động/an toàn và accuracy |
| Classification v2 | Schemas/validator, jobs/batching/Gemini, intent/analyses, giữ DONE hợp lệ khi đổi model; [worker](../docs/operations/classification-worker.md) có pilot 10 native targets ngày 11/10 | Full BC live acceptance, precision/recall, product ACP; money budget deferred |
| OCR ảnh POST | Tesseract vie/eng, resolver/evidence/cache, classifier input, UI và Excel; [pilot](../docs/operations/facebook-image-ocr.md) có OCR thật | OCR ảnh COMMENT/REPLY/video, benchmark/reviewer, batch reprocess UI; Gemini OCR pilot HTTP 503 |
| Dự án | Registry VinCons (tổ chức) + VinWonders Vũ Yên; 14 group enabled, project selection/query/filter | Full PF acceptance, project override/history chuyên biệt và pilot quality |
| Dashboard UXR | Bốn tab, phiên bảng/Excel, hội thoại, nháp local, versioned/bulk reviews, health; [workspace](../docs/operations/dashboard-workspace.md) | UAT người dùng/mentor, screen reader thực tế và mọi tổ hợp zoom |
| Lịch | Dashboard raw v2 DAILY_SLOTS, closing tick; CLI v2 catch-up theo ngày; [runbook](../docs/operations/dashboard-crawl-schedule.md) | Windows service/wake, vận hành nhiều ngày và full scheduling ACP |
| Contracts PRD v1 downstream | Canonical/unified-evidence/social-signal và exporter bốn sheets là target specs riêng | Chưa hoàn tất exact schemas/projection/export/quality gates của toàn PRD |

Không ghi “chưa có comments/classifier/OCR/Excel” cho hệ thống hiện tại chỉ vì contracts PRD v1 còn PLANNED. Ngược lại, feature v2 có implementation không chứng minh toàn bộ yêu cầu PRD v1 hoặc live quality đã đạt.

## 2. Nguồn yêu cầu và ownership

[PRD SmartCity v0.1](product/prd.md) là snapshot nguyên byte do người dùng cung cấp, SHA256 `92a23ae94549cd4b94c7d5b2b215121a3e760ed7c03f4c0285fb539e4219efb7`. [Scope/provenance](product/scope.md) ghi đường dẫn bản gốc và quyết định sau PRD. Giữ snapshot nguyên vẹn; dùng link nội bộ để checkout độc lập đọc được.

- Product/Ops sở hữu scope/domain priorities và acceptance nghiệp vụ.
- Data/AI sở hữu taxonomy, evidence, grounding và review rules.
- Engineering sở hữu interfaces, schema compatibility và migrations.
- QA sở hữu requirement → test → evidence/acceptance.

`docs/` giải thích implementation, quyết định và runbooks; `src/` implement components; `engine/` compose runtime. Dependency engine → src; src không import engine. Ownership trên là theo role, chưa tự gán cá nhân.

## 3. Contract và feature inventory

| Spec | Phạm vi / trạng thái |
| --- | --- |
| [PRD](product/prd.md), [Scope](product/scope.md) | Product snapshot, provenance, priorities và quyết định scope |
| [Legacy record](contracts/legacy-record.md) | Schema sáu collectors, được characterization/self-check bảo vệ |
| [Source Registry](contracts/source-registry.md) | YAML versions/references, readiness; runtime trong engine.registry |
| [Source Adapter](contracts/source-adapter.md), [Discovery Queue](contracts/discovery-queue.md) | Acquisition candidate v1, windows/identity/lineage/quota, review và dispatch; runtime đã có |
| [Exclusion rules](contracts/exclusion-rules.md) | Acquisition v1 prefilter audit-only; raw v2 lưu trước filter, không purge DROP |
| [Facebook adapter v1](features/facebook-adapter.md) | Browser post acquisition; không dùng thay bằng chứng conversation v2 |
| [TikTok search](features/tiktok-search.md), [Google discovery](features/google-social-discovery.md) | Browser keyword/hashtag và SerpApi Facebook/TikTok/YouTube discovery |
| [Threads adapter](features/threads-adapter.md), [conversation đa nền tảng](contracts/multi-platform-conversations.md) | **IMPLEMENTED_SUBSET / LIVE_PARTIAL**: browser, queries, raw v3, Gemini batch, DB chung và lịch riêng; [runbook/evidence](../docs/operations/threads-acquisition.md). Nested mapping/API/OCR/full ACP còn mở |
| [Luồng Threads](../docs/design/threads-adapter-flow.md), [workspace UX](../docs/design/threads-workspace-ux.md) | **OFFLINE_VERIFIED / LIVE_UI_VERIFIED** phần đã triển khai: chọn nền tảng, query/run/schedule riêng, platform/source filters và export; [task/gates](../TODO.MD) |
| [Group tracing](features/facebook-group-tracing.md), [Conversation record](contracts/conversation-record.md) | Raw v2 nodes/revisions/observations, relationships/time/coverage/tasks; core increment đã có, full acceptance pending |
| [Project feedback](features/project-customer-feedback-filter.md) | Project registry/matching/routing/UI có increment; full PF scope còn acceptance riêng |
| [Project taxonomy](contracts/project-issue-taxonomy.md), [review snapshot](taxonomy/v1/README.md) | Definitions/profiles/mapping; [runtime snapshot](../config/taxonomy/v1/common.yaml) được worker sử dụng |
| [Batch classification](contracts/llm-batch-classification.md) | Executable schema/validator là nguồn fields hiện hành; snippets proposal rút gọn không phải valid requests |
| [Facebook image OCR](features/facebook-image-ocr.md) | POST image evidence đã nối raw/classifier/UI/export, live partial |
| [Canonical record](contracts/canonical-record.md), [Unified evidence v1](contracts/unified-evidence.md) | Target contracts PRD v1; không rename raw conversation/image-evidence thành v1 |
| [LLM output v1](contracts/llm-output.md), [Excel export v1](contracts/excel-export.md) | Target social-signal và Signals/Crawl_Runs/Source_Registry/Review; không coi workspace export là đủ acceptance |
| [Requirements matrix](traceability/requirements-matrix.md) | 17 FR/NFR → contracts/tasks/implementation subset/acceptance còn lại |

Runtime config ở [config index](../config/README.md). Watchlist ACTIVE khác watchlist seed DRAFT; taxonomy config APPROVED khác specs snapshot DRAFT. Thời gian UTC, ngày hiển thị Việt Nam; identity nội dung, tác giả và registry source ID tách riêng.

## 4. Quy trình cập nhật

1. Xác định requirement/acceptance và contract nào thay đổi; kiểm tra code/config cùng [trạng thái hiện hành](../docs/current-state.md).
2. Chốt fields/types/nulls/enums/identity và cross-field rules trước feature work; breaking changes có schema version, migration và rollback.
3. Cập nhật executable schemas, fixtures và tests về observable behavior; không sửa semantics của v1 để lách validator.
4. Cập nhật docs, TODO và traceability trong cùng increment; phân biệt PLANNED, IMPLEMENTED, OFFLINE_VERIFIED, LIVE_PARTIAL/LIVE_VERIFIED và ACCEPTED.
5. Giữ audit/baseline/plan theo ngày là lịch sử, gắn link đến implementation mới. Không lấy mock/schema pass để xác nhận live coverage hoặc quality.
6. Report local trong `reports/` có thể thiếu trong checkout mới; mọi đường dẫn contract/code/config cần nằm trong repository.

Các plans [P0–P6](../docs/phased-delivery-v2.md), [WBS/live acceptance](../docs/execution-and-live-acceptance-v2.md), [architecture v2](../docs/implementation-plan-v2.md) và [UXR](../docs/dashboard-ux-implementation-plan.md) giữ thiết kế/acceptance gốc. Phần đã triển khai đối chiếu qua runbooks; plans không tự nâng trạng thái sản phẩm.
