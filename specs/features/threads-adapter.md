# Threads adapter — project search và conversations

**IMPLEMENTED_SUBSET / LIVE_PARTIAL · 12/10/2026**. Nền tảng Threads của Meta, khác “thread hội thoại” trong Facebook. [Runbook + evidence](../../docs/operations/threads-acquisition.md), [task status](../../TODO.MD), [plan/gates](../../docs/implementation-plan-threads.md), [contract](../contracts/multi-platform-conversations.md). Browser/raw/classifier/UI/lịch đã triển khai; API, nested mapping, OCR và full coverage chưa nghiệm thu. Không dùng prefilter-before-persist acquisition v1 cho tính năng raw này.

**Bổ sung 13/10/2026 — IMPLEMENTED / LIVE_PARTIAL:** kiểm tra scope VinCons sau persist, parser v5 và query theo vấn đề. [Runbook/acceptance](../../docs/operations/threads-vincons-scope-20261013.md) phân biệt raw, alias evidence và phản ánh. Hai hội thoại thiếu evidence/query là mặc định; việc hoãn làm coverage partial, không xóa raw hoặc suy DROP.

Thiết kế: [adapter flow](../../docs/design/threads-adapter-flow.md), [workspace UX](../../docs/design/threads-workspace-ux.md). Tab Thu thập đã chọn Facebook/Threads; THR-UX01–09 đối chiếu backend/THR-AC, kết quả thực thi ở runbook.

## Phạm vi v1

Theo dõi query đã duyệt của VinCons và VinWonders Vũ Yên; search recent, lấy bài và replies public truy cập được, rescan hội thoại đã biết để tìm replies mới trên bài cũ. Raw lưu trước filter/classify; dùng chung DB/reviews/Gemini và lịch riêng. Profiles rộng, trending topic chung, DMs/private, write/publish/moderation, tải video/ASR và tự động phát hiện mọi hội thoại chưa biết ngoài phạm vi.

API là provider ưu tiên **pilot**, browser Playwright/Chromium là phương án nếu cần và được kiểm chứng. Hybrid hợp lệ nhưng phải ghi API/browser provenance, không gọi kết quả API/Google là browser live verification. P0 capability gate bắt buộc cho replies của bài người khác.

## Requirements và traceability

Các yêu cầu dưới đây là mở rộng theo yêu cầu người dùng, không sửa snapshot PRD. Mapping PRD chỉ là đối chiếu mục tiêu chung.

| ID | Requirement | PRD |
| --- | --- | --- |
| THR-001 | Source `THREADS_SEARCH`, query version/enable/readiness; không có group Threads | FR-01 |
| THR-002 | Target tên/alias dự án; query ambiguous optional; hashtag/topic semantics xác minh riêng | FR-02 |
| THR-003 | Chọn provider theo access/capability pilot; public replies chưa đạt không claim full | FR-04 |
| THR-004 | Search RECENT/Latest, pagination và timestamp; giữ observed order, bounds, limits | FR-03/04 |
| THR-005 | Post và direct/nested replies là nodes riêng có root/parent evidence | FR-04 |
| THR-006 | Window theo từng node, parent ngoài window vẫn context, unknown không giả timestamp | FR-03/04 |
| THR-007 | Inventory/rescan parent cũ, fairness, checkpoints, late reconciliation/catch-up | FR-05/15/17 |
| THR-008 | Platform-scoped identity, URL/shortcode/native alias có evidence, nhiều observations | FR-12 |
| THR-009 | Versioned additive migration/rollback; giữ Facebook IDs/revisions/reviews/analyses | FR-05/12/17 |
| THR-010 | Durable ingest queue, commit ack, bounded retry/backpressure và giao dịch ngắn | FR-05/16/17 |
| THR-011 | Lưu raw trước lọc; lọc node độc lập; parent quảng cáo không loại child complaint | FR-06 |
| THR-012 | Scope evidence/taxonomy, batch Gemini, reuse kết quả hợp lệ và lý do tiếng Việt | FR-02/08/09/10 |
| THR-013 | Lịch Threads riêng 2 ca/45 phút/closing ticks, lease và overlap với Facebook | FR-03/05/17 |
| THR-014 | Outcome phân biệt auth/permissions/rate limit/parser/no results; secret redaction | FR-16 |
| THR-015 | Coverage nhiều stage, partial khi budget/cursor/hidden replies/missing parent | FR-04/16 |
| THR-016 | Backend/UI/Excel filter platform/project/query/time/type, nguồn search khác group | FR-13/14/16 |
| THR-017 | Media refs/alt text, optional POST OCR, quote/repost relation riêng | FR-07/11 |
| THR-018 | Offline regression + live đối chứng + 3 ngày vận hành; evidence trước ACP | FR-04/16/17 |
| THR-019 | Browser xác minh URL/ô query, chỉ nhận card hiển thị trong vùng search; mismatch/selector drift không báo thành công rỗng | FR-04/16 |
| THR-020 | Scope alias từ project registry sau commit raw; query không chứng minh entity. Hoãn hội thoại không có evidence; quota riêng cho thiếu caption/media | FR-02/06/16 |
| THR-021 | Rescan bài cũ đúng dự án hoặc có child evidence; không bắt issue keyword trong root. Chỉ fetch thành công một lần/run, giữ observations từng query | FR-04/05/12 |

THR-019–021 đã kiểm thử trong `tests/integration/test_threads_parser.py` và `tests/contract/test_threads_scope.py`; bộ hồi quy 109 tests đạt. Scope observation bổ sung `entity_scope={version,project_id,status,matched_aliases,conversation_eligible}`; run/job bổ sung query verification/parser và scope counters. Các trường này phục vụ acquisition, không thay taxonomy/schema kết quả model. Pilot scheduler dùng provider browser và vẫn PARTIAL; source/project identity, nested parent và toàn bộ phản ánh chưa được suy từ counters.

## Interface đề xuất

Runtime đã có `probe_access(source)`, `discover(request)`, `fetch_item(candidate,context)`; detail browser đọc replies theo budget và báo parent/coverage UNVERIFIED. `fetch_replies` độc lập/page continuation chuẩn là phần thiết kế chưa hoàn tất, không coi fetch DOM hữu hạn là toàn bộ replies.

- `request`: platform/provider, query source snapshot, project scope hint, query ID/version/original/effective, run/task ID, fixed UTC window, budgets và cursor checkpoint.
- `probe`: scope capabilities thực tế; không tự enable source hoặc xin thêm quyền.
- Candidate: native ID nếu có, permalink/shortcode, caption/text/timestamp precision, author/media refs, query lineage. Không ghi project KEEP/confidence nghiệp vụ ở acquisition.
- `fetch_replies`: native reply ID, verified root/replied-to, text/time/media khi lấy được; children là replies khác media carousel children. Parser phải phân biệt hai loại.
- Engine dispatch fetch/storage/rescan; adapter không gọi Gemini, không giữ raw DB transaction.
- API response chỉ persist các content fields đã allowlist. Không lưu Authorization header, token, cookie hoặc nguyên URL pagination có access token vào raw/observations/checkpoints/logs; cursor và next-page metadata được tách/lọc. Bảo toàn content evidence không đồng nghĩa lưu nguyên response chứa credential.

## Cấu hình mẫu — proposal, chưa chạy được

```yaml
schema_version: threads-watchlist-v1
enabled: false
provider: UNRESOLVED  # P0 chọn THREADS_API / THREADS_BROWSER / THREADS_HYBRID
project_scopes:
  - project_id: vincons
    queries:
      - {query_id: threads_vincons_name, version: 1, type: KEYWORD, value: VinCons, enabled: true}
  - project_id: vinwonders_vu_yen
    queries:
      - {query_id: threads_vwy_name, version: 1, type: KEYWORD, value: "VinWonders Vũ Yên", enabled: true}
      - {query_id: threads_vwy_alias, version: 1, type: KEYWORD, value: "VinWonder Vũ Yên", enabled: true}
      - {query_id: threads_vwy_spaced, version: 1, type: KEYWORD, value: "Vin Wonders Vũ Yên", enabled: true}
      - {query_id: threads_vwy_tag, version: 1, type: TAG_TEXT, value: "#VinWondersVuYen", enabled: false}
      - {query_id: threads_vwy_discovery, version: 1, type: KEYWORD, value: "Vũ Yên", enabled: false}
schedule:
  enabled: false
  timezone: Asia/Ho_Chi_Minh
  interval_minutes: 45
  slots: [{start: "05:00", end: "08:30"}, {start: "17:00", end: "18:30"}]
storage: {mode: DURABLE_QUEUE, database: sessions/acquisition/acquisition.sqlite3}
```

`enabled` platform, query và schedule là ba gates riêng. Runtime `config/threads.yaml` đã có versions/queries/readiness/budgets. `TAG_TEXT` chỉ tìm chuỗi, chưa pilot exact topic-tag. Budget/rescan ở plan mục 6; trạng thái lịch thực đọc qua catalog/dashboard.

## Output, lỗi và coverage

Raw node versioned gồm platform `THREADS`, node type `POST|COMMENT|REPLY`, native ID/shortcode/URL riêng, text/time/author/media, availability/extraction/missing fields và relationships. API text ánh xạ `raw_text`; null khác empty/unavailable; metrics không có là null, không phải 0. Observation lưu query/project scope/provider/method/run/window; query match không chứng minh relevance.

Outcomes thiết kế: `SUCCESS`, `PARTIAL`, `EMPTY_VERIFIED`, `SKIPPED`, `AUTH_REQUIRED`, `ACCESS_DENIED`, `RATE_LIMITED`, `EXTRACTION_FAILED`, `TEMPORARY_ERROR`. Error codes thêm `TOKEN_EXPIRED`, `PERMISSION_MISSING`, `CAPTCHA_REQUIRED`, `SEARCH_SELECTOR_MISMATCH`, `REPLIES_NOT_ACCESSIBLE`, `CURSOR_EXPIRED`, `STORAGE_RETRY_EXHAUSTED`, `QUEUE_BACKPRESSURE`, `TIME_BUDGET_REACHED`, `UNRESOLVED_PARENT`, `UNRESOLVED_TIMESTAMP`. HTTP 403/429 cần đối chiếu body/redacted provider code trước mapping, không suy mọi 403 là token hết hạn.

Coverage stage tách search, detail, replies, rescan, storage. Báo observed/stored/in-window/out-of-window/unknown, pages, deferred, unresolved, request/time/stop reason. `SUCCESS` là task hoàn tất trong scope đã chọn, không tự là toàn nền tảng đầy đủ. `EMPTY_VERIFIED` chỉ khi response/search UI hợp lệ được parse và thật sự không có kết quả; parse lỗi không thành empty success.

## Acceptance

THR-AC01–13 trong [plan mục 8](../../docs/implementation-plan-threads.md#8-acceptance-và-kiểm-thử-hệ-thống-thật) là bộ cases chuẩn. Kết quả hiện hành đối chiếu [TODO](../../TODO.MD): browser/query/raw/Gemini/UI đã chạy thật; old-parent/new-reply đối chứng và nested parent/full coverage còn mở. Không thay acceptance bằng mocks, endpoint hội thoại `/api/threads/` hoặc Google results.
