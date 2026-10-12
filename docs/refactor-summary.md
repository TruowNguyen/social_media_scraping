# Kết quả structural refactor — 2026-10-08

> **Snapshot lịch sử theo ngày trong tài liệu.** Các trạng thái “chưa triển khai”, disabled hoặc lỗi probe chỉ áp dụng cho lượt kiểm tra đó. Đối chiếu code/config hiện hành ngày 11/10/2026 tại [trạng thái dự án](current-state.md); không dùng snapshot này để kết luận runtime hiện tại.

BASE-02/03 **OFFLINE_VERIFIED**, BASE-01 **DOC_VERIFIED**. Theo yêu cầu cleanup tiếp theo, đã bỏ 11 root Python files và `src/compat`; imports gọi trực tiếp owner modules, runner/CI gọi package entry points. Sáu collector, legacy schema và CWD data paths được bảo toàn; chưa có live crawl hoặc SmartCity runtime mới. [TODO](../TODO.MD) là tracker hiện hành; audit và plans cũ là snapshot trước implementation. [Cleanup validation](baseline/root-cleanup-validation.json) ghi kết quả mới; [refactor validation trước cleanup](baseline/refactor-validation.json) là lịch sử.

| Trước | Owner implementation hiện tại | Cách gọi hiện tại |
| --- | --- | --- |
| twtr-scraper.py | src/collectors/x/collector.py + engine/legacy/x.py | `python -m engine.runtime --platform x` |
| yt-scraper.py | src/collectors/youtube/collector.py + engine/legacy/youtube.py | `python -m engine.runtime --platform youtube` |
| tel-scraper.py | src/collectors/telegram/collector.py + engine/legacy/telegram.py | `python -m engine.runtime --platform telegram` |
| reddit-scraper.py | src/collectors/reddit/collector.py + engine/legacy/reddit.py | `python -m engine.runtime --platform reddit` |
| tiktok-scraper.py | src/collectors/tiktok/collector.py + engine/legacy/tiktok.py | `python -m engine.runtime --platform tiktok` |
| truth-scraper.py | src/collectors/truthsocial/collector.py + engine/legacy/truthsocial.py | `python -m engine.runtime --platform truthsocial` |
| pipeline_utils.py | config/env, config/paths, observability/logging, resilience/retry/rate_limit, domain/language/legacy_schema/sentiment_labels, storage/record_file, discovery/keyword_matching, analysis/legacy_text, media/transcription | Import trực tiếp component, không có facade |
| dedup_utils.py | src/filtering/dedup.py | `from src.filtering import dedup` |
| demo.py | engine/legacy/demo.py | `python -m engine.legacy.demo` |
| selfcheck_schema.py | tests/contract/legacy_schema.py | `python -m tests.contract.legacy_schema` |
| selfcheck_twtr_retry.py | tests/integration/legacy_x_retry.py | `python -m tests.integration.legacy_x_retry` |

`engine.runtime --platform ...` và installed `social-scrape` dispatch collector legacy được chọn. Imports deferred ở dispatcher. `src` không import engine/root facades; pagination/parser/one-source acquisition ở src, whole-watchlist loops/main ở engine. X cooldown được đọc trực tiếp từ collector owner, không copy mutable state. Private model monkeypatch trong selfcheck đã trỏ đến owner mới, giữ nguyên assertions.

Shared algorithms/function bodies giữ nguyên AST trừ setup_logging đăng ký tên logger owner để INFO tiếp tục tới root handlers. Đợt đầu đã so AST 54 shared definitions, 88 collector definitions; runtime functions sau bỏ qualification source.* bằng original. Dedup implementation nguyên byte. Cleanup tiếp theo chỉ thay imports/entry points và bỏ tên logger root cũ; patch [analysis owner](../src/analysis/legacy_text.py) hoặc [transcription owner](../src/media/transcription.py). Không duy trì hai bản caches/models/locks.

Kiểm chứng:

- 13 collector characterization pass trước/sau migration; thêm 10 resilience cases pass trên frozen original và code mới. Quan sát JSON/rerun/sort/duplicate/textless/edit/pinned/repost/caption fallback, API retry/partial data/deadline và SQLite reload.
- 6 architecture/compatibility tests và 2 profile lock tests pass; tổng **31 unittest cases**. Hai legacy selfchecks giữ six-platform assertions và tám X retry cases.
- JSON demo parsed bằng baseline, canonical SHA256 `bd6f88176669c0468419d5782542fe97776fd9be0649bf99df3294ff08002c53`.
- Recursive compile, fresh-process imports sáu nguồn, Bash syntax, CLI help và wheel package validation. Wheel sau cleanup chỉ gồm src/engine + metadata, không root facades/config/docs/tests/credentials/profile data.
- Playwright 1.63.0 / Chromium 153.0.8010.12 smoke trên trang local pass hai profiles. Không navigation/sign-in/live acceptance.

Máy local chạy Python **3.13.13**. CI được cập nhật recursive compile, unittest, dispatcher help; matrix 3.12/3.13 chưa chạy ở GitHub trong lượt này. Windows test file/SQLite tạm cần chạy ngoài sandbox sau WinError 5; không phải collector failure. Demo dùng `-X utf8` trên Windows để in Persian. Browser tier thêm riêng, collection/model pins giữ nguyên. pyproject metadata core-only; collector dependencies cần requirements.txt.

Evidence machine-readable: [pre-move characterization](baseline/characterization-before.json), [validation report](baseline/refactor-validation.json). PRD snapshot và năm data contracts mới là tài liệu; [requirements matrix](../specs/traceability/requirements-matrix.md) giữ 17 FR runtime PLANNED.

Debt còn lại: legacy dedup/JSON không transactional, empty-text collision, duplicate policy khác nhau giữa nguồn, en/fa defaults và Whisper translate, metadata-only mất ở một số collector, legacy model/retry budget. Đây là feature changes riêng ở CORE/SC; không sửa âm thầm trong migration. Canonical storage, YAML runtime loader, exclusion enforcement, Facebook browser adapter, TikTok global search, Google queue/routing, LLM, Excel và scheduler chưa implement. Bootstrap profile lock chưa phải browser job manager có run deadline/source isolation. Formal ACP cần reviewer/date trong TODO.
