# P1 — raw conversation store và raw-first acquisition

> **Snapshot lịch sử theo ngày trong tài liệu.** Các trạng thái “chưa triển khai”, disabled hoặc lỗi probe chỉ áp dụng cho lượt kiểm tra đó. Đối chiếu code/config hiện hành ngày 11/10/2026 tại [trạng thái dự án](../current-state.md); không dùng snapshot này để kết luận runtime hiện tại.

Ngày 09/10/2026. **IMPLEMENTED + OFFLINE_VERIFIED** cho models/storage/migration và raw-first post orchestration. Chưa claim comments live, full-window coverage, classifier worker hoặc dashboard v2. Evidence: [validation](../../reports/p1-raw-storage-validation.json).

## Input / mục tiêu / output nghiệm thu

Input: conversation-record-v2, candidate v1, SQLite records/observations/reviews đang có; acquisition v1 filter-before-fetch.

Mục tiêu: raw post/comment/reply có identity và thread, revisions/observations/outbox; lưu trước filter, ads không bị purge; legacy dữ liệu/CLI/schema giữ compatibility.

Output: `src.domain.conversation`, `src.storage.conversations`, `conversation_migration`, opt-in raw-first acquisition và `engine.conversation_cli`; 15 tests P1 và regression toàn contract suite; migration/restore trên bản sao dữ liệu thực. Không nối chế độ mới vào dashboard mặc định trong P1.

## Hành vi đã có

- Native ID hoặc verified node URL làm identity; fallback parent URL không định danh comment; provisional node riêng khi chưa rõ. Empty text/cùng tác giả không gộp node.
- COMMENT/REPLY root/parent được kiểm tra thread, own timestamp/precision; stub REFERENCE_ONLY có thể fill với explicit node ID, không invent caption.
- Rerun thêm observations, raw không đổi không thêm revision. Changed raw/extraction tạo revision/outbox; parent edit tạo context invalidation cho children.
- Upsert + observations + checkpoint trong transaction; nested failures có savepoint. Crash không tiến checkpoint qua dữ liệu chưa commit.
- V2 tables riêng khỏi `records`/legacy reviews/rejections. `reject`/purge v1 không đụng raw v2. `filter_saved` chỉ ghi decision/rule/revision sau raw; review riêng và không reset khi rerun.
- CLI raw-first Facebook discovery được lưu trước fetch, fetch thành công lưu bản đầy đủ rồi filter; ad vẫn fetch/store. Fetch lỗi giữ discovery và typed error. Parent ngoài window có thể lưu context; không là bằng chứng đã scan comments.
- Outbox hiện là PENDING events, chưa có classifier consumer. `list_nodes(window=...)` chỉ return INSTANT đã xác nhận trong window; unknown/date-only giữ trong raw khi không filter window, UI riêng triển khai P5.

## Migration và commands

DB production mặc định vẫn `sessions/acquisition/acquisition.sqlite3`. Bàn giao này dùng **bản sao nhất quán** dưới `sessions/pilot/v2/p1-<timestamp>/`, chưa sửa DB production. SQLite backup API bảo đảm snapshot gồm dữ liệu committed trong WAL.

```powershell
# Chạy trên bản sao đã chuẩn bị; backup phải là đường dẫn file mới.
.\.venv\audit\Scripts\python.exe -m engine.conversation_cli --db sessions/pilot/v2/pilot.sqlite3 migrate --backup sessions/pilot/v2/before-migration.sqlite3
.\.venv\audit\Scripts\python.exe -m engine.conversation_cli --db sessions/pilot/v2/pilot.sqlite3 list
# Restore rehearsal vào file mới, không overwrite DB đang chạy.
.\.venv\audit\Scripts\python.exe -m engine.conversation_cli --db sessions/pilot/v2/restored.sqlite3 restore-copy --backup sessions/pilot/v2/before-migration.sqlite3
```

Pilot path đã tạo thực tế nằm trong validation JSON; ví dụ paths trên cần chuẩn bị copy trước. Migration additive maps Facebook records thành POST; platforms khác giữ nguyên legacy. Notes/history/observations/aliases giữ provenance; observations cũ gắn revision import, không claim đã biết text lịch sử trước migration. Rerun mapping idempotent; native/URL conflicts fail thay vì silently merge. Backup/restore không recovery raw đã purge trước đây.

Raw-first post crawl có thể chạy explicit trên DB pilot:

```powershell
.\.venv\audit\Scripts\python.exe -m engine.conversation_cli --db sessions/pilot/v2/pilot.sqlite3 crawl-posts --source-id fb_group_139108668844789 --start 2026-10-07T22:00:00Z --end 2026-10-08T01:30:00Z --max-candidates 10
```

Đây là lệnh **posts-only P1**, cần browser/profile không bị job khác giữ; output ghi `comments_supported=false` và `full_window_coverage_verified=false`. Không dùng lệnh này làm test đủ comment/reply hoặc scheduled v2 acceptance. Facebook live chưa chạy trong report P1.

## Nghiệm thu offline và dữ liệu thực copy

- Test dedup, same-text distinct IDs, edits/context invalidation, unknown time, old-post/new-comment fixture, URL/comment fallback, thread conflict, transaction crash, nested rollback, raw DROP retention và legacy purge isolation.
- Engine test chứng minh discovery commit trước fetch và full raw trước filter; lỗi fetch giữ raw, không gọi `reject` v1.
- Bản sao thực migration: 24 Facebook records, 48 aliases, 289 observations, 2 reviews và 2 review-history entries tại snapshot; legacy payload hashes trước/sau khớp, restore copy khớp; counts là snapshot, không tổng bất biến của production.
- Regression toàn `tests/contract/test_*.py` pass; record số tests mới nhất trong validation JSON. Không có accuracy/coverage live claim.

P1 còn limitation: bảo toàn dữ liệu lịch sử đã tồn tại, chưa recover dữ liệu purge; unresolved provisional nodes cần explicit reconciliation thay vì fuzzy merge; pagination/index efficiency lớn sẽ tối ưu khi volume thật có evidence. P2 tiếp tục parser comments/inventory/scheduler; P3/P4 consume outbox và classifier; P5 mới đọc raw v2 trên dashboard.
