# Requirements matrix — đồng bộ 11/10/2026

Đủ 17 FR theo [PRD snapshot](../product/prd.md). Bảng ghi implementation subset hiện có và acceptance còn thiếu; **IN_PROGRESS không phải ACP toàn FR**. [Trạng thái code/config](../../docs/current-state.md), [TODO](../../TODO.MD), [kế hoạch v2](../../docs/implementation-plan-v2.md).

## Conversation, taxonomy và batching v2

SL-T01–07 là epics; GT-T01–07 là acquisition tasks liên quan, không cộng trùng khối lượng.

| Scope / requirements | Tasks | Implementation/evidence | Acceptance còn lại |
| --- | --- | --- | --- |
| Raw conversation, comments bài cũ — GT-001–008 | SL-T02/03/06/07; GT-T01–07 | Nodes/revisions/observations, tasks/leases/resume, thread inventory và [raw dashboard](../../docs/operations/dashboard-raw-v2.md); [backfill](../../docs/operations/unified-database-backfill.md) PARTIAL | GT-AC01–14 đầy đủ, full source/window/comment coverage |
| Taxonomy per-project — TX-001–005 | SL-T01/04/07 | Runtime 1.0.0 trong config; draft review trong specs; taxonomy contract tests | TX-AC01–06 nghiệp vụ, mentor/held-out và scope bổ sung |
| Batch LLM/evidence/jobs — BC-001–006 | SL-T04/05/07 | Schemas/validator, jobs/batching, [Gemini worker](../../docs/operations/classification-worker.md) với pilot 10 native targets ngày 11/10, [OCR POST](../../docs/operations/facebook-image-ocr.md) | BC-AC01–08 toàn scope và held-out accuracy |

## PRD requirements

Mở rộng người dùng **Threads — THR-001–018 / THR-T01–20 / THR-AC01–13: PLANNED** ở [feature](../features/threads-adapter.md), [contract đa nền tảng](../contracts/multi-platform-conversations.md), [plan](../../docs/implementation-plan-threads.md). Đối chiếu FR-01/02/03/04/05/06/07/08/09/10/11/12/13/14/15/16/17 theo từng requirement trong spec; không thay PRD snapshot hoặc nâng trạng thái runtime/ACP của các FR bên dưới. Live cases NOT_RUN.

**THR-DESIGN-01 / THR-UX01–09: DESIGNED**, ở [luồng adapter](../../docs/design/threads-adapter-flow.md) và [workspace UX](../../docs/design/threads-workspace-ux.md). UX cases ánh xạ THR-AC01–11/13 và công việc THR-T18/19; bộ lọc/query/lượt chạy/lịch chỉ khả dụng khi backend tương ứng được triển khai. UI/runtime/live tests **NOT_RUN**.

| PRD / priority | Tasks | Contract / runtime hiện có | Acceptance còn thiếu | FR status |
| --- | --- | --- | --- | --- |
| FR-01 P0 Registry | CORE-02, SRC-DQ, RES-02; PF-T01/02/03 | [Registry](../contracts/source-registry.md), [queue](../contracts/discovery-queue.md), 14 group và hai project scopes | Full product/source approval/live ACP | IN_PROGRESS |
| FR-02 P0 Dictionary | CORE-02, SC-01; SL-T01 | Query/project dictionaries, review/runtime taxonomy | Dictionary curation và full quality gate | IN_PROGRESS |
| FR-03 P0 Windows | SC-06; SL-T06 | [Lịch raw v2](../../docs/operations/dashboard-crawl-schedule.md), fixed UTC windows, closing tick, persistence/overlap tests | Scheduled completion nhiều ngày, product ACP | IN_PROGRESS |
| FR-04 P0 Acquisition | CORE-01/07, SRC-FB/TT-KW/TT-TAG/GG/YT; GT-T02/03 | [Adapter](../contracts/source-adapter.md), raw Facebook threads, Google discovery | TikTok live; đối chứng coverage/full FB/TT/GG acceptance | IN_PROGRESS |
| FR-05 P0 Incremental | CORE-03/06/07; GT-T02/03/06 | Identity, observations, raw revisions, inventory, durable/resumable tasks/jobs | Full rerun/catch-up/live acceptance | IN_PROGRESS |
| FR-06 P0 Negative filter | CORE-05, SC-01; SL-T04 | [Exclusion](../contracts/exclusion-rules.md), v2 per-node intents/raw retention | Full business scope/false-positive evaluation | IN_PROGRESS |
| FR-07 P0 Media | SC-02; OCR-T01–07 | POST image resolver/OCR/evidence implemented; legacy ASR riêng | Full [unified-evidence-v1](../contracts/unified-evidence.md), video/ASR/visual scope và quality | IN_PROGRESS |
| FR-08 P0 LLM schema | SC-03; SL-T04/05 | [Batch v2](../contracts/llm-batch-classification.md) validator/Gemini pilot | Exact [social-signal-v1](../contracts/llm-output.md)/projection và full provider acceptance | IN_PROGRESS |
| FR-09 P0 Domains | SC-01/03; SL-T01/04 | Per-project multi-issue taxonomy/runtime | PRD v1 domain projection và held-out quality | IN_PROGRESS |
| FR-10 P0 Subcategories | SC-01/03; SL-T01/04 | Shared definitions/profiles, legacy mapping validation | Full v1 subcategory/projection/business acceptance | IN_PROGRESS |
| FR-11 P0 Confidence | SC-02/03; SL-T04/05 | Evidence origin/quote validation, OCR quality/review, confidence fields | [V1 evidence](../contracts/unified-evidence.md) toàn scope, calibrated quality/reviewer | IN_PROGRESS |
| FR-12 P0 Dedup | CORE-06, SC-04; GT-T02/06 | Acquisition/raw identity, observations và idempotent jobs | Full [canonical-v1](../contracts/canonical-record.md), near-dedup/Excel leakage KPI | IN_PROGRESS |
| FR-13 P0 Excel | SC-04; UXR-22 | Workspace raw/classification Excel theo cùng phiên bảng | Exact [Signals/Crawl_Runs/Source_Registry/Review](../contracts/excel-export.md) PRD v1 | IN_PROGRESS |
| FR-14 P1 Review | SC-05; UXR-11/20 | Persisted versioned review/notes, conflict checks, history/bulk | Full override workflow, reviewer/product acceptance | IN_PROGRESS |
| FR-15 P1 Reconcile | SC-06; GT-T03/06 | Có inventory rescan/CLI date catch-up; không tự đồng nhất với late reconciliation PRD | Chốt/bật configurable late-window reconciliation và nghiệm thu | PLANNED |
| FR-16 P0 Monitoring | CORE-03/07, SC-07; UXR-13/14/15 | Source outcomes, jobs/heartbeat, health, API usage/errors | Full stage/SLA metrics và end-to-end product ACP | IN_PROGRESS |
| FR-17 P1 Rerun | CORE-07, SC-06; GT-T06 | Fixed-window CLI, tasks/leases/resume và classification rerun | Full live rerun/recovery/PRD acceptance | IN_PROGRESS |

## NFR và evidence gates

| NFR | Tests/evidence / giới hạn |
| --- | --- |
| Isolation/idempotency/validation | Architecture/acquisition/conversation/classification/jobs contract suites; coverage/live quality không suy từ mock |
| Security/access/privacy | Profile locks, source gates, bounded retries, redacted errors; raw v2 giữ DROP theo policy riêng, v1 audit-only |
| Vietnamese/UTC/local schedule | Per-node timestamp precision, UTC windows, VN daily slots, OCR vie/eng, Vietnamese display labels |
| Windows/Linux compatibility | Local Python 3.13; CI matrix 3.12/3.13 cấu hình, không coi lần chạy local là GitHub CI pass |
| Replaceable adapters/providers | engine → src, architecture tests; provider config không thay schema |
| Performance/quality/KPI | Workspace có live-read/performance sample local; chưa có held-out hoặc full PRD KPI/ACP |

PRD snapshot/hash, links và schema examples được kiểm tra riêng với behavioral suites. [Audit đồng bộ](../../docs/documentation-drift-audit-2026-10-11.md) ghi kết quả lần kiểm tra mới; các con số test trong report 08–10/10 là số của từng increment. Formal reviewer/date, full coverage và quality acceptance vẫn theo TODO.
