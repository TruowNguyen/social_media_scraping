# PRD → code gap analysis

> **Snapshot lịch sử theo ngày trong tài liệu.** Các trạng thái “chưa triển khai”, disabled hoặc lỗi probe chỉ áp dụng cho lượt kiểm tra đó. Đối chiếu code/config hiện hành ngày 11/10/2026 tại [trạng thái dự án](current-state.md); không dùng snapshot này để kết luận runtime hiện tại.

Ngày: **08/10/2026**. Baseline: Git `c876bbf86419c30046585baf808e0411b345ccd7`. Nguồn yêu cầu: [PRD v0.1](../specs/product/prd.md), đặc biệt §6–7 và §11.4.

Đây là mapping kế hoạch, **chưa phải danh sách tính năng đã triển khai**. `Có một phần` nghĩa là hạ tầng có thể reuse nhưng chưa đạt acceptance của PRD. Priority FR giữ nguyên PRD; ưu tiên nghiệp vụ domain congestion P0/complaint P1 không thay đổi priority P0 của yêu cầu taxonomy FR-09/10.

## 1. Mapping yêu cầu chức năng

| Requirement | Existing capability/evidence | Gap | Proposed change | Priority | Target module/phase |
| --- | --- | --- | --- | --- | --- |
| FR-01 Source Registry | `sources/*.txt`, `load_trusted_*` ở collectors | Chưa có source ID/type/status/priority/enabled/project/location/access metadata; chưa có Facebook/Web | YAML + strict validation; registry đọc sources; runtime health lưu DB, không ghi credentials vào YAML | P0 | `src/config/{loader,validation}.py`, `src/domain/models.py`, `engine/source_registry.py`; Phase 2 |
| FR-02 Project/entity dictionary | Financial `load_asset_registry`, `keyword_matches`; `keywords/*.txt` | Asset symbol schema không phù hợp project; aliases/locations/operational terms thiếu; vi không mặc định allowed | `keywords.yaml` chứa entities/projects/aliases/locations/query seeds; `exclusions.yaml`/`taxonomy.yaml` riêng; builder giữ broad retrieval và lineage | P0 | `src/discovery/{query_builder,keyword_search,watchlist}.py`; Phase 2/4 |
| FR-03 Multi-window scheduler | Bash runner + cron example; window env | Không có peak windows/timezone/run ID/storage; Windows runner thiếu | Giữ cron trên Linux; engine hỗ trợ scheduled/manual run và persisted run/window lock; pilot sáng 05:30–08:00, close crawl 08:15; chiều configurable/provisional | P0 | `engine/{scheduler,runtime,crawl_run}.py`, `config/schedule.yaml`; Phase 2/8 |
| FR-04 Freshness acquisition | Các collector có cutoff/IDs/URLs/collected time | Không có SourceAdapter contract; `now()` nội bộ không hỗ trợ fixed rerun window; YouTube làm mất video không text; không có Facebook/Web | Adapter trả raw candidate và typed source outcome với explicit window/quota; normalize riêng; additive adapter cho YouTube/TikTok; Web provider chưa chốt, Facebook feasibility | P0 | `src/collectors/base.py`, platform adapters, `src/domain/models.py`; Phase 3/9 |
| FR-05 Overlap/incremental | Existing IDs/JSON append; persisted dedup; Telegram edit refresh | Chưa bảo đảm idempotency toàn pipeline hoặc crash recovery; dedup không transactional với JSON | Canonical item unique constraint; observation lineage cho nhiều queries/runs; overlap explicit; persist raw trước enrichment; reprocess pending mà không tạo case mới | P0 | `src/storage/{database,repositories}.py`, `engine/pipeline.py`; Phase 2/3 |
| FR-06 Negative filtering | Language gate, keyword matching, X credibility; financial NLI | Không có sales/recruitment/PR intent/drop reason; gate legacy có thể bỏ tiếng Việt | Cheap filter tạo signals về entity/source/quality/negative intents; chỉ drop intent rõ, complaint có negative keyword vẫn chuyển classifier; lưu rule/reason | P0 | `src/filtering/{exclusion,relevance}.py`, `config/exclusions.yaml`; Phase 4 |
| FR-07 Media Resolver | YouTube captions/ASR; TikTok caption → ASR → description; shared Whisper | Không unified evidence/status; chưa OCR/frames/image; English bias; metadata-only mất ở YouTube/TikTok | Progressive caption/metadata → ASR → sampled frames/OCR/vision khi cần; unavailable giữ candidate; evidence provenance + cost/duration limits; no raw-URL-only LLM | P0 | `src/media/{resolver,audio,transcription,frames,vision}.py`; Phase 5 |
| FR-08 LLM fixed schema | Financial sentiment/NLI/local models, retry decorator | Chưa LLM provider/schema version/prompt/JSON validation | Provider adapter nhận structured evidence; bounded timeout/retry; strict enum/required fields/grounding; invalid output → REVIEW/UNCLASSIFIED processing state | P0 | `src/enrichment/{llm,prompts,validation}.py`, `specs/contracts/llm-output.md`; Phase 6 |
| FR-09 Four-domain taxonomy | Legacy schema nhận sáu platform, financial asset classes | Chưa operational domain/relevance | `SITE_ACCESS_CONGESTION`, `CUSTOMER_COMPLAINT`, `OTHER_RELEVANT`, `IRRELEVANT`; KEEP/DROP/REVIEW separate enum; domain nullable nếu unclassified | P0 | `src/domain/{enums,schemas}.py`, `config/taxonomy.yaml`; Phase 2/4/6 |
| FR-10 Subcategories | Không có | Thiếu bảy congestion/sáu complaint subcategories | Config + validated domain/subcategory relationship; description claim-based; no arbitrary labels | P0 | `src/enrichment/{tagging,validation}.py`, `specs/taxonomy/`; Phase 4/6 |
| FR-11 Confidence/evidence | `quality_score`, asset/sentiment confidence | Các score cũ không đo relevance; raw_text không tách caption/transcript; chưa review gate | Evidence types/levels + confidence + review reason; null project/location khi không grounded; ngưỡng review configurable, hiệu chỉnh trên sample | P0 | `src/domain/models.py`, `src/media/resolver.py`, `src/enrichment/validation.py`; Phase 5/6 |
| FR-12 Exact/near dedup | MD5 normalized text + MinHash/LSH + SQLite; cross-platform group | Không duplicate_type/URL normalization/exact item key; near không recheck; empty collisions; inconsistent skip/tag | Giữ algorithm baseline trong Phase 1; feature phase thêm explicit exact identity/type, tránh empty hash merge, verify near candidates; export chỉ collapse exact; near group không tự kết luận cùng incident | P0 | `src/filtering/dedup.py`, `src/domain/normalization.py`, `src/storage/repositories.py`; Phase 3/4 |
| FR-13 Excel | JSON output duy nhất | Không workbook/schema/signals/review/run/source sheets | Export từ DB, đủ `Signals`, `Crawl_Runs`, `Source_Registry`, `Review`; không đưa DROP vào Signals; empty run vẫn workbook có header/run status; Excel không là source of truth | P0 | `src/export/excel.py`, `scripts/export_excel.py`; Phase 7 |
| FR-14 Review/override | Không có | Không lưu original/reviewed values/reviewer/time | Review import/CLI trước; immutable override history có record ID, reviewer/time/note; UI nhẹ ở v1 | P1 | `src/storage/repositories.py`, review contract/CLI; Phase 7, UI ngoài MVP core |
| FR-15 Late reconciliation | Có thể dùng cron cadence/window chung | Không separate optional window/history | Config optional 22:00/12–18h lookback theo đề xuất PRD; mặc định chưa bật trước quyết định Ops; reuse same pipeline/dedup | P1 | `engine/scheduler.py`, `config/schedule.yaml`; Phase 8 |
| FR-16 Run/source monitoring | Rotating logs, timestamp run text; counters cục bộ | Không persisted run/source status, failure reasons hoặc media/LLM/export metrics | Run + source_runs + structured events; partial failure aggregation; counts ở mỗi stage; NO_NEW_DATA khác source failure | P0 | `engine/{crawl_run,pipeline}.py`, `src/observability/`, `src/storage/`; Phase 2/3/6/7 |
| FR-17 Manual rerun | Có thể chạy script riêng, env window từ hiện tại | Không fixed historical range/source ID/selective retry/idempotent run context | CLI source ID + start/end hoặc run reference; run ID mới, preserve lineage và retry pending records; source/window overlap lock | P1 | `scripts/{run_pipeline,run_collector}.py`, `engine/runtime.py`; Phase 3/8 |

## 2. Mapping phi chức năng và operational contract

| Requirement PRD §7/guardrails | Existing capability | Gap → proposed change | Priority/target |
| --- | --- | --- | --- |
| Source failure isolation | Per-source try/except; Bash process continuation | Return `None`/`[]`/normal exit không đủ status; typed `SourceResult` + source_runs; một fail không chặn source tiếp theo, toàn run PARTIAL khi phù hợp | P0; adapters/storage/engine |
| Idempotency, rerun | JSON ID sets; SQLite PK | DB + export + observation semantics chưa thống nhất; unique platform/item + transactional canonical persistence; crash-recovery fixture | P0; storage/pipeline |
| API/session security | `.env`/session ignored | Chưa explicit redaction/access references; config chỉ chứa reference; không log/export secrets; validate từ test synthetic secret | P0; config/logging |
| Public/authorized access | Platform-specific methods | Chưa xác minh watchlist/access; xem access-method debt YouTube trong audit; disabled/unverified source không chạy; auth/CAPTCHA → stop source, no bypass | P0; adapter contract/feasibility |
| Vietnamese/UTF-8/local time | Unicode-aware dedup/JSON; language detector; UTC text | Defaults en/fa và English media; additive SmartCity vi config/transcribe; accent/nonaccent fixtures; timezone configurable theo PRD | P0; config/domain/media |
| Python 3.11+/Windows/Linux | CI 3.12/3.13; Bash Linux | Audit verified Windows 3.13.13; không hứa 3.11/3.14 tương thích; chọn baseline 3.13, mở matrix sau dependency validation; Windows scheduler path riêng | P0 compatibility; pyproject/CI/engine |
| Adapter/provider replacement | Functions/optional imports | Chưa contract typed/injection; adapter, resolver, LLM provider boundaries; không thêm framework orchestration nếu CLI/cron đủ | P0; collectors/enrichment/engine |
| Schema validation trước persist/export | Legacy `build_quality` báo missing checks | Chỉ score, chưa hard gate hoặc schema SmartCity; strict canonical/LLM validation; quarantine invalid record cùng lineage | P0; domain/enrichment/storage |
| Throughput/run/export ≤30 phút | Caps, limiters, threadpool, time budget Truth | Chưa số liệu pilot/cost; config quotas/model budget, duration counters; benchmark media/LLM trên nguồn được phép | P0 measure; pipeline/telemetry |
| Monitoring PRD §7.1 | Human-readable logs | Thiếu event correlation và metric denominators; event payload run/source/step + DB counters từ acquisition/filter/media/LLM/export | P0; observability/storage |

## 3. Phân biệt contract để tránh migration sai

| Legacy field/behavior | Canonical hướng tới | Migration rule |
| --- | --- | --- |
| `Source.Source_id` | `platform_item_id` | Không map sang registry `source_id` |
| `Source.url` | `source_url` và derived `canonical_url` | Giữ URL nguồn; identity URL được normalize có test riêng |
| `Content.raw_text` | `raw_text` + caption/transcript riêng khi biết provenance | Không tự giả định mọi YouTube raw_text là transcript gốc hoặc mọi TikTok text là caption |
| `time_stamps.*` | UTC aware timestamps; nullable publication | Parse format cũ; không invent publication từ collected time; date-only giữ precision/unknown |
| `asset_mention`/`sentiment` | Legacy optional payload | Không đổi tên thành domain/relevance hoặc confidence operational |
| `quality.quality_score` | structural quality riêng | Không dùng thay LLM confidence |
| `is_duplicate` | exact/near relationship + group | Không suy ra type từ flag cũ nếu không đủ bằng chứng |
| Filename keyword/account | `source_id`, `query_id`, `search_keyword`, observations | Context phải được adapter/run gắn lúc acquisition; không fabricate run IDs cho lịch sử |

PRD dùng `KEEP|DROP|REVIEW` cho relevance ở §6.3/§11.4; ví dụ boolean trong prompt đính kèm được coi là minh họa cũ, không override PRD. `UNCLASSIFIED` là trạng thái xử lý, không phải domain thứ năm. `content_id` ở Excel là mapping được document từ canonical `record_id`.

`analysis_evidence`/`evidence_used`, `media_processing_status`/`media_status`, `auth_required`/`requires_login`, `ended_at`/`completed_at` cần mapping explicit trong contracts; không dùng hai bản field không đồng bộ.

## 4. Feasibility hiện tại

| Nguồn ưu tiên | Có code? | Đã kiểm chứng lượt này? | Việc còn cần |
| --- | --- | --- | --- |
| YouTube query/channel | Có yt-dlp + transcript pipeline | Import offline; không live | Nguồn target, lawful access/provider decision, vi captions, metadata-only preservation |
| TikTok account | Có | Import offline; không live | Verified watchlist/access, caption language; benchmark quota/reliability |
| TikTok hashtag/search | Chưa có | Chưa | Feasibility/provider, không mô tả keyword timeline filter thành global search |
| Facebook group/page watchlist | Chưa có | Chưa | Source URLs/quyền truy cập/session method + evidence public/authorized; bounded pilot; không bypass |
| Web/Google query/news | Chưa adapter riêng; X có DDGS search | Chưa | Provider/search API decision; dated result/text extraction; lineage/freshness tests |

Không thay Facebook bằng Telegram/Reddit để tuyên bố đạt MVP. X, Telegram, Reddit, Truth vẫn được giữ compatibility nhưng không tự trở thành scope ưu tiên sản phẩm.

## 5. Acceptance/evaluation cần đo sau audit

Giữ nguyên target đề xuất PRD: KEEP precision ≥80% với ít nhất 200 reviewed samples; valid LLM output ≥98%; duplicate leakage ≤5%; scheduled run completion ≥95%; usable evidence trên video accessible ≥80%; đầy đủ lineage/domain/relevance ≥98%; Excel ≤30 phút sau close-window; configured-watchlist coverage ≥90% trên accessible comparison sample.

Baseline hiện chỉ là engineering/offline behavior, **chưa có product baseline** cho các chỉ số trên. Mẫu đánh giá cần source/window stratification, DROP/REVIEW audit, unavailable denominator riêng và review override trace. Grounding project/location không evidence không được auto-accept; không có DROP trong Signals; source failure không được ngụy trang thành zero candidates.

## 6. Phụ thuộc và quyết định chưa chốt

- Source/watchlist ban đầu, Facebook authorization/session, TikTok access method, Web Search provider, LLM provider/model/credentials và YouTube API decision chưa được cung cấp.
- Afternoon 16:30–19:00/19:15 và reconciliation 22:00 chỉ là đề xuất; chưa coi là lịch production đã chốt.
- PRD ghi timezone `Asia/Bangkok`; client đang `Asia/Saigon`. Hướng kế hoạch: persisted timestamps UTC; scheduler timezone explicit theo PRD, thời gian trình bày theo client; không âm thầm sửa PRD.
- Confidence threshold, reviewer/SLA, retention, author minimization, comment scope và bổ sung owner/action columns còn mở.
- Phase 1 không phụ thuộc các quyết định provider/watchlist này; live acquisition/enrichment không được tuyên bố đã hoàn thành bằng mock.

Thứ tự triển khai và exit criteria ở [implementation plan](implementation-plan.md). Traceability ổn định sẽ chuyển sang `specs/traceability/requirements-matrix.md` khi tạo contracts; bảng này giữ vai trò gap assessment.
