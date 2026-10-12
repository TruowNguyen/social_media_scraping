# Acquisition implementation — 08/10/2026

> **Snapshot lịch sử theo ngày trong tài liệu.** Các trạng thái “chưa triển khai”, disabled hoặc lỗi probe chỉ áp dụng cho lượt kiểm tra đó. Đối chiếu code/config hiện hành ngày 11/10/2026 tại [trạng thái dự án](current-state.md); không dùng snapshot này để kết luận runtime hiện tại.

Đã triển khai acquisition runtime riêng cho Facebook public group, TikTok keyword/hashtag và Google social discovery. Có Registry loader, prefilter, SQLite records/observations, queue/review và CLI. Legacy collectors tiếp tục dùng engine.runtime, output/schema cũ; acquisition dùng engine.acquisition_cli và schema acquisition-candidate-v1. **Chưa ACP hoặc LIVE_VERIFIED toàn luồng.**

## Code và kết quả

| Phần | Implementation | Kiểm chứng |
| --- | --- | --- |
| Contract/types/window | src/acquisition/models.py | UTC, `[start,end)`, quota và null/0; candidate không có taxonomy/relevance suy đoán |
| Registry/query scope | engine/registry.py, engine/acquisition.py, config/acquisition.yaml | Safe YAML, version/type/reference gates, source disabled/unverified không dispatch; 9 sources gồm 7 group và 2 search scopes, 2 watchlists |
| Session/browser | src/acquisition/browser.py, src/browser/profiles.py | Profile theo repo root, lock chung với bootstrap, source/window lease; context cleanup; Chromium local profile giữ dữ liệu qua hai lượt |
| Exclusion | src/acquisition/prefilter.py | Clear intent DROP, complaint/mixed/negation/truncated REVIEW; zero full-fetch call và chỉ 7 audit fields cho prefilter DROP |
| Identity/storage | src/acquisition/identity.py, src/storage/acquisition.py | Atomic upsert + observations, native/fallback aliases, rollback khi crash, no empty-text merge; exact/near text là relationship, không cùng incident |
| Facebook | src/acquisition/browser_adapters.py:FacebookGroupAdapter | Group ref/slug, caption/permalink/time, text expansion sau prefilter; DOM fixture không lấy text hoặc mở rộng comment |
| TikTok | src/acquisition/browser_adapters.py:TikTokSearchAdapter | Keyword URL và hashtag URL độc lập; Unicode, caption/creator, public hydration metadata khi fetch, một identity nhiều query |
| Google | src/acquisition/google.py | Google engine/gl/hl, một trang, organic title/snippet/position; typed auth/quota/parser errors; retry reserve trước request, 20/run và 200/tháng UTC |
| Queue/routing | src/storage/acquisition.py, engine/acquisition.py, engine/acquisition_cli.py | PENDING/APPROVED/REJECTED/history, draft disabled, explicit process có source/watchlist gate; container không là content record |
| YouTube bridge | src/acquisition/youtube.py | yt-dlp metadata đúng video, channel phải match approved ref; subprocess bounded, không media/transcript/ASR hoặc walk channel |

JSON export chứa acquisition records và observations, chưa phải canonical enrichment/Excel. Provider/browser deps đã cài trong `.venv/audit`; console `social-acquire` và module CLI đã có. Browser và legacy entry points vẫn riêng.

## Bằng chứng kiểm thử

[Acquisition suite](../tests/contract/test_acquisition.py) và [Chromium suite](../tests/integration/test_acquisition_browser.py) là fixture synthetic. [Báo cáo kiểm tra](baseline/acquisition-validation.json) ghi tổng số/checks thực tế của lần kiểm tra cuối; CI chỉ cấu hình, chưa có kết quả GitHub.

| Acceptance liên quan | Evidence offline chính |
| --- | --- |
| AD-AC-01/02/03/04/05/06/07/08/09/10/11/12 | Disabled gate, window/old pinned, rerun observations, intent cases/no raw DROP, typed empty/error, partial/isolation, profile/job locks, crash rollback, empty text, provider error redaction |
| FB-AC-01/02/03/04/05/06/07/08/10/12/13 | Group/slug metadata và fixtures, cutoff/pinned/intent, real Chromium synthetic long text/missing data/comments isolation, locks; runtime auth probe dưới đây không chứng minh full live extraction |
| TT-AC-01/02/03/05/06/07/08/09/11/12/13 | Distinct mode URLs và DOM, Unicode/invalid hashtag, intent/missing fields, native dedup, sanitized failures/profile ownership; không có live search sample |
| GG-AC-01/02/03/04/05/06/07/08/09/10/11/12/13/14 | Six query jobs, allowlist/tracking/redirects, container/snippet separation, ready/pending gates, durable quota concurrent/restart, typed errors, YouTube source check và existing TikTok observation |
| DQ-AC-01/02/03/04/05/06/07/08/09/10/11/12 | Queue/native fallback/history, draft disabled, explicit process ready/disabled, unknown YouTube, container, rejection retention và transaction rollback |

Bảng là đối chiếu **các hành vi đã được kiểm tra**, không tuyên bố mỗi kịch bản lớn đã được cover toàn bộ. VER-01 vẫn IN_PROGRESS: còn bổ sung fixtures để đối chiếu đầy đủ 64 scenarios, đặc biệt latest-sort thực trên UI, quota/time partial trên platform, private/removed item và session hết hạn. Native/fallback reconciliation đã kiểm tra với cùng URL; các alias permalink khác cần pilot/fixture bổ sung. Không nâng ACP dựa trên số tests hoặc số files.

Prefilter là heuristic bảo thủ; dictionaries trong exclusion config là signals, không chuyển từng keyword thành DROP rule. Intent patterns hiện có trong code, version theo contract; phản ánh mơ hồ vẫn REVIEW. Relationship matching giới hạn 200 record comparisons/lượt, không là incident clustering. Unknown timestamp giữ metadata REVIEW; không thêm thời gian giả từ search snippet. Native/URL reconciliation có fixture cho hai entry được tạo riêng trước khi short URL được resolve; observations và quyết định REJECTED được giữ, không tạo pending copy mới.

## Probe live và việc còn chờ

[Probe report](operations/acquisition-live-probes.json) ghi **resource probes thật**, không crawl acceptance:

- Facebook group 1675953926771851: probe cuối AUTH_REQUIRED/LOGIN_REQUIRED. Một lượt trước có listing nhưng chưa validate identity, không dùng làm bằng chứng full extraction.
- TikTok keyword VinCons: ACCESS_DENIED/CAPTCHA; hashtag #VinCons: EXTRACTION_FAILED/LISTING_SELECTOR_MISMATCH. Cần phiên truy cập được rồi kiểm tra lại layout, không kết luận hashtag không có kết quả.
- SerpApi: một attempted request, AUTH_REQUIRED/SERPAPI_INVALID_KEY. Key hiện có không dùng được; chưa thử cả ba target query live.
- Bảy seed group và hai search scopes vẫn disabled. Public/access manual confirmation của người dùng được giữ; không tự nâng thành source ready hoặc thay metadata login từ một probe.

Tiếp theo: chuẩn bị phiên Facebook/TikTok và key hợp lệ theo [runbook](operations/acquisition-runbook.md), verify từng scope, enable nguồn/watchlist riêng, rồi pilot giới hạn để kiểm tra caption/native ID/time/media refs và exclusion trong cùng window. LLM/media processing/Excel/scheduler theo các task SC, chưa triển khai trong acquisition này.
