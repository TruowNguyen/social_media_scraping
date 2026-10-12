# Kế hoạch triển khai SmartCity Operational Social Listening

> **Kế hoạch baseline ngày 08/10/2026.** Các trạng thái chưa refactor/implement trong tài liệu là lịch sử thiết kế; [trạng thái hiện hành](current-state.md) và [requirements matrix](../specs/traceability/requirements-matrix.md) ghi code/config đã có cùng acceptance còn thiếu. Phase v1 không tự ánh xạ hoàn tất sang increment v2.

Ngày: **08/10/2026**. Product source: PRD v0.1; strategy `reuse > extend > refactor > replace`. Đây là kế hoạch, không phải trạng thái tính năng đã có.

## 1. Trạng thái và nguyên tắc sequencing

Phase 0 audit/baseline hoàn tất ở lượt này: PRD được đọc đầy đủ, architecture/gap/migration map có bằng chứng, existing offline checks/demo pass trên Windows Python 3.13.13. Chưa di chuyển code hoặc implement feature. Product quality/live-source KPIs chưa có baseline.

Phase 1 phải giữ legacy behavior và hoàn tất gate trước canonical/registry/filter/media/LLM/Excel feature work. Các acceptance tests mới bắt đầu bằng fixtures và authorized access. Feasibility Facebook/Web/TikTok cần được khảo sát **sớm trước đầu tư production**, dù implementation Facebook nằm Phase 9; không đợi làm hết LLM/export mới phát hiện nguồn không khả thi.

Không đưa Prefect/Airflow/Celery/PostgreSQL/dashboard/incident lifecycle vào MVP chỉ để đổi kiến trúc. CLI + cron/Linux hoặc Task Scheduler/Windows đủ khi đáp ứng run isolation và persisted status.

## 2. Phases, deliverables và exit criteria

| Phase | Nội dung/output | Reuse/boundary | Exit criteria |
| --- | --- | --- | --- |
| 0 — Audit/baseline | Bốn tài liệu docs, specs ownership, baseline demo/manifest/dependencies | Read-only code review + existing checks | Đã đạt lượt này; unresolved live/product questions ghi rõ |
| 1 — Structural refactor | `specs/docs/src/engine`, imports/wrappers, ownership, characterization, CI recursive checks, refactor summary | Giữ six collectors/financial analysis/dedup/media/legacy JSON và process isolation | Same observable legacy outputs, all checks/imports/contract tests pass; src không import engine; không feature behavior change |
| 2 — Domain/config/registry/run | Canonical models/enums, Source config, YAML validation, query/entity dictionary, SourceRegistry composition, CrawlRun/SourceRun và additive SQLite schema | Typed models trong src; registry/lifecycle engine; SQLite POC | Valid/invalid/disabled/duplicate source ID/type/platform config tested; UTC timestamps/source lineage; empty/success/failure run stored |
| 3 — Adapter integration | SourceAdapter, YouTube/TikTok adapters reuse primitives, Web provider adapter, watchlist/search lineage, fixed-window CLI/rerun | Legacy CLI giữ nguyên; SmartCity acquisition có behavior deltas documented | Raw candidates persisted trước enrichment; explicit window/quota/status; overlap/retry idempotent; partial failure source khác vẫn chạy; Web provider feasibility ghi thật |
| 4 — Filtering/taxonomy/dedup | Config exclusions/keywords/taxonomy; cheap cascade; four domains/subcategories; exact item/URL/content và near relation | Reuse MinHash nhưng tách type/policy; không biến similarity thành incident | Cases A–E + mixed-negative complaint/vi accent/noaccent pass; DROP reason stored; no auto congestion from emoji-only; exact duplicate không là case mới |
| 5 — MediaResolver | Caption/metadata → ASR → sampled frames/OCR/vision, statuses/provenance/evidence level | Reuse yt-dlp/FFmpeg/faster-whisper qua approved access backend; không LLM fetch URL | Video unavailable không mất record; no-text candidate vẫn REVIEW; duration/quota/cost bounds; evidence level phản ánh đúng ASR/visual đã có |
| 6 — LLM enrichment | Provider adapter, versioned prompt/schema, strict JSON/enums/grounding, bounded retry, confidence/review gate | Evidence-only input; prompts/validation trong src.enrichment | Invalid JSON/domain/schema/NaN/confidence/evidence → bounded retry rồi REVIEW; unknown project/location null; no silent accept; lineage/model/prompt metadata stored |
| 7 — Export/basic review | Workbook bốn sheets, DB-derived signals/run/source/review; review import/CLI + original/reviewed history | Excel chỉ delivery; SQL storage; UI nhẹ để v1 | Workbook schema/zero-run headers/duplicate/DROP exclusion tested; override persists reviewer/time and originals; quality review sample chuẩn bị |
| 8 — Peak schedule/monitoring | Configurable morning/afternoon/close-window, optional reconciliation, manual rerun, source/window locks, metrics/runbook | Keep Linux cron wrapper; Windows orchestration path; one pipeline | Fixed lookback overlap, midnight/local-time conversion, scheduler restart/idempotency và partial/no-new statuses tested; pilot export latency measured |
| 9 — Facebook watchlist pilot | Authorized group/page adapter từ feasibility sớm; health checks/source runbook/feasibility matrix | Không hard-code URL/session; không bypass; platform parsing trong src | Ít nhất một cơ chế watchlist live khả thi với nguồn được phép trước tuyên bố ingestion MVP đạt; coverage đối chứng, access failure isolated |

Phase 3 Web và Phase 9 Facebook phụ thuộc provider/source access chưa chốt. Mock adapters giúp kiểm tra plumbing nhưng không thỏa acceptance live-source coverage. TikTok search/hashtag chỉ cam kết sau feasibility; không quảng cáo account-filter mode là search toàn nền tảng.

## 3. Contracts cần chốt trước feature implementation

Các contracts nằm trong `specs/contracts/`; validators/test fixtures enforce cùng version. [specs ownership](../specs/README.md) định nghĩa quy trình thay đổi.

### SourceAdapter / SourceRegistry

Source config tối thiểu: `source_id`, `platform`, `source_type`, `name`, `url/query`, `project`, `location`, `priority`, `enabled`, `monitoring_scope`, `access_type`, `requires_login`; secret reference nếu cần, không secret value. Support domain types: FACEBOOK_GROUP, FACEBOOK_PAGE, TIKTOK_ACCOUNT, TIKTOK_HASHTAG, YOUTUBE_QUERY, YOUTUBE_CHANNEL, WEB_QUERY, NEWS_SOURCE. Config phải reject incompatible type/platform và duplicate IDs; disabled source không gọi collector.

Adapter nhận source + fixed `lookback_start/end` + query context/quota, trả candidate batch và typed source outcome/counters/error. Candidate có platform/item URL-or-ID, collected time, publication nếu có, raw caption/text/metadata/media refs và source/query/run lineage. Kết quả rỗng hợp lệ khác fail/auth/rate limit.

### CanonicalRecord / storage

Canonical giữ tối thiểu fields của yêu cầu đính kèm §19: record/source/run IDs, platform/source type/source URL/item ID, timestamps/author cần thiết, caption/transcript/OCR/visual summary, matched keywords/query ID, media/evidence, relevance/domain/subcategory/project/location/description/confidence, duplicate group/drop reason/processing status. Bổ sung raw payload/provenance, schema/model/prompt/config version và observation lineage khi cần trace, không nhồi vào export.

Kế hoạch SQLite additive: `sources`/health, `crawl_runs`, `source_runs`, `records`/evidence/enrichment, `observations`, `duplicate_relations`, `review_overrides`, migrations/version. Dedup DB legacy giữ nguyên; SmartCity DB riêng dưới data giúp rollback và không làm hỏng legacy index. Không migrate legacy JSON thành operational labels tự động.

Identity canonical theo platform + native item ID, fallback canonical URL có contract rõ. Một item được tìm bởi nhiều source/query/run có một canonical record và nhiều observations; không mất source_id/query_id vì overwrite. Persist raw và state trước media/LLM; retry enrichment/review không cần crawl lại. Publication thiếu giữ null/precision và flag, không dùng collected time giả publication.

### UnifiedEvidence / MediaResolver

Tách caption, description, hashtags, transcript, OCR text, visual summary và metadata; mỗi artifact có extraction method/status/language/provenance. Level: CAPTION_ONLY, CAPTION_TRANSCRIPT, CAPTION_VISUAL, FULL_MEDIA. Case chỉ metadata/no caption cần flag thiếu evidence, không dùng level để khẳng định text đã tồn tại; resolver/schema phải document tình huống này.

Video URL dùng cho approved media backend, không phải evidence model tự fetch. ASR giữ tiếng Việt khi config transcribe; no hallucinated OCR/visual summary nếu bước đó không chạy. Media UNAVAILABLE vẫn giữ caption/metadata, giảm confidence hoặc REVIEW tùy evidence.

### LLMOutput

Ưu tiên PRD §11.4: `schema_version`, `relevance=KEEP|DROP|REVIEW`, domain thuộc đúng bốn enums, nullable subcategory/project/location, description, confidence [0,1], evidence_used, nullable drop_reason. DROP phải có lý do; subcategory phải thuộc domain; evidence_used chỉ nêu loại có trong input; project/location phải grounded; description mô tả **nội dung phản ánh**, không kết luận trách nhiệm/fact.

Không đủ/mâu thuẫn evidence → REVIEW. Fail hết retry → processing status INVALID_LLM_OUTPUT/LLM_FAILED + REVIEW/UNCLASSIFIED; domain nullable khi chưa phân loại, không thêm domain tùy tiện. JSON schema validation cần kiểm tra business cross-field rules; enum/schema riêng chưa đủ chống bịa location. Provider có timeout/token/cost limit configurable, attempts hữu hạn; numeric NaN/infinite không hợp lệ.

### Excel / review

Giữ đầy đủ PRD §6.7: Signals gồm content_id/run/source identifiers, URL/time/type, caption/raw_text và media evidence, domain/subcategory/description/project/location, relevance/confidence/analysis evidence/status/duplicate group/review status. Crawl_Runs lưu window/source/status và mọi counters; Source_Registry gồm health/auth/enabled; Review gồm original/reviewed domain/subcategory/description/reviewer/time/note.

Mapping `content_id ← record_id` và naming differences được document trong spec. Routing đề xuất: Signals chứa KEEP; các record REVIEW có hàng trong sheet Review với original values và reviewed fields nullable khi chưa xử lý, để reviewer không mất case low-confidence; không đưa DROP vào Signals. Chốt routing này trong export contract trước Phase 7. Export empty run có header và run row. Override cập nhật view cuối nhưng giữ nguyên original model output cùng audit trail; không chỉ sửa Excel rồi mất feedback.

## 4. Error/status policy

| Outcome | Hành vi source/record/run |
| --- | --- |
| SUCCESS / NO_NEW_DATA | Record counters thật; run vẫn success, no-new không là lỗi |
| SOURCE_UNAVAILABLE / AUTH_REQUIRED / ACCESS_DENIED | Không retry vô hạn/bypass; lưu source error, source khác tiếp tục |
| RATE_LIMITED | Bounded backoff/Retry-After khi có; deferred hoặc source fail/partial sau budget |
| EXTRACTION_FAILED | Giữ raw metadata và reason; không ghi là empty success |
| MEDIA_UNAVAILABLE | Giữ candidate/evidence còn usable; review nếu không đủ |
| LLM_FAILED / INVALID_LLM_OUTPUT | Hết bounded retries → REVIEW/unclassified + error lineage |
| Export failure | Enriched data vẫn trong DB, export status failed; rerun export không re-crawl/re-enrich |

Phân biệt lifecycle run (RUNNING/SUCCESS/PARTIAL/FAILED), source outcome và record processing status. Một source fail có thể làm run PARTIAL; không làm source thành công mất dữ liệu. Overlap lock và export count phải lấy từ storage metrics, không suy từ file tồn tại.

## 5. Test/acceptance roadmap

CI offline, fixtures synthetic hoặc redacted/được phép; không live Facebook/TikTok. Structure giữ `tests/unit`, `integration`, `contract`, `fixtures`, cùng root compatibility checks.

| Suite | Cases tối thiểu | Phase gate |
| --- | --- | --- |
| Legacy characterization/import | Audit baseline, old/new entrypoints, public facades, state/paths, six collector behavior | 1 |
| Config/registry | Valid YAML, malformed YAML/types/ranges, unknown platform/type, duplicate IDs, disabled source, missing credential reference, vi aliases | 2 |
| Acquisition/storage | Same item rerun, multi-query observations, cutoff boundaries/fixed window, partial source failure, zero-new run, persist-then-crash/retry | 3 |
| Filtering | Case A congestion; B complaint trong watchlist/context phù hợp; C sales; D recruitment; E ambiguous; complaint có từ bán hàng; irrelevant ngoài scope | 4 |
| Dedup | Same item/normalized URL/hash; near group; empty/emoji text không auto merge unrelated; repeated incidents tương tự không auto same incident | 3/4 |
| Media | Caption usable, ASR unavailable, no-text inaccessible video, visual unavailable, extraction timeout/duration cap, language/provenance/level | 5 |
| LLM contract | Invalid JSON/domain/schema; bool relevance rejected; confidence bounds/NaN; missing/null project/location; unsupported evidence/project invention; retries exhaust | 6 |
| Export/review | Sheet/columns/types, UTF-8 Vietnamese, UTC-to-display dates, zero rows, DROP/exact duplicate exclusion, original/reviewed values persist | 7 |
| Runtime/scheduler | Manual/source rerun, overlap, midnight, local timezone mapping, disabled windows, failed export retry, restart scheduling | 8 |
| Authorized live pilot | Watchlist comparison, source health, media/model quality, financial source defaults absent | 9/pilot |

Không claim product success dựa trên offline assertions. POC review ≥200 records để đo KEEP precision; đo valid schema before/after retry riêng; duplicate leakage/export latency/coverage theo configured accessible sample. Logs/metrics liên kết `crawl_run_id`, source, stage; không dùng `quality_score` làm KPI confidence.

## 6. Source feasibility spike và trình tự phụ thuộc

Trước live development, lập `docs/operations/source-feasibility-matrix.md`: source type, permitted access, auth owner, discovery path, accessible content/media, publication fidelity, pagination/quota, failure behavior, sampled yield và quyết định proceed/defer. Lượt audit chưa thực hiện live spike vì thiếu source/access/provider, không gán trạng thái khả thi giả.

Thứ tự quyết định: Ops cung cấp watchlist/project/location aliases → xác nhận access hợp lệ và provider search/media → adapter sample → benchmark evidence → chọn LLM provider/evaluate → pilot schedule/coverage. Có thể thiết kế contracts offline trong lúc các quyết định còn mở; không cần dựng crawler toàn Internet hoặc bypass để giải bài toán dữ liệu thiếu.

## 7. Risks, mitigation và owner role

| Risk dựa trên audit/PRD | Impact | Mitigation/gate | Owner |
| --- | --- | --- | --- |
| Facebook/TikTok access chưa proven | Không có signal dù pipeline mock pass | Feasibility sớm, nguồn được phép, status riêng; không cam kết coverage toàn platform | Engineering + Ops/IT |
| en/fa gate/English captions | Mất tiếng Việt trước LLM | SmartCity config/adapters delta riêng, original evidence language fixtures | Data + Engineering |
| Legacy near skip và empty hashes | Bỏ/gộp nhầm case độc lập | Freeze Phase 1; separate exact/near và empty-evidence policy ở feature phases | Data |
| Dedup DB update trước JSON write | Crash mất record, rerun khó phục hồi | Raw-first transactional SmartCity storage, recovery tests; legacy debt ghi rõ | Engineering |
| Split globals/facades/import logging | Tests pass một path nhưng state diverges | Actual owner imports, alias dedup module, process isolation, facade/state tests | Engineering |
| Financial NLP nhầm operational classifier | Wrong domain/confidence | Giữ legacy_text; classifier/schema SmartCity độc lập | Data/AI |
| LLM prompt injection/ungrounded outputs từ nội dung | Model gán sai/suy diễn project/location | Evidence là data, prompt boundaries, strict schema + grounding + REVIEW/human sample | Data/AI |
| Mức độ media/LLM cost không biết | Không đạt run SLA/budget | Cheap filter trước media; progressive evidence; quota/timeout/model budgets; benchmark | Engineering/Data |
| File/paths/Windows/Linux runtime khác | Break developer/cron workflow | Root wrappers, unchanged paths, supported Python baseline, Windows runtime tests riêng | Engineering |
| Credentials/session/author information | Privacy/secret exposure | References/minimization, no bypass, redaction test, retention trước production | IT/Legal + Engineering |
| Model output chỉ là claim | Quyết định vận hành sai nếu coi là fact | Description reported signal; reviewer/source/evidence retained; no auto operational action | Product/Ops |
| Timeline PRD chỉ đề xuất | Commit ngày không có cơ sở dependency/access | Gates theo evidence; giữ lịch PRD làm planning input, không hứa production milestone | Product/Engineering |

## 8. Assumptions và open decisions

1. Tiếp tục dùng Git root hiện tại; không rename/reclone/rewrite repository. User chưa yêu cầu deploy, publish, commit hoặc migration production.
2. Structural baseline Python 3.12/3.13 của repo được giữ; audit verified 3.13.13. PRD 3.11+ là mục tiêu mở compatibility, cần validate riêng; 3.14 mặc định máy không phải baseline đã supported.
3. Morning 05:30–08:00 và closes 08:15 theo PRD; afternoon vẫn provisional. Config chứa timezone explicit, DB UTC. PRD Asia/Bangkok giữ nguyên; client-facing dates theo Asia/Saigon, cần chốt naming khi scheduler rollout.
4. SQLite POC additive đủ scope hiện tại; chưa có multi-user/concurrency requirement để chuyển PostgreSQL.
5. Case complaint ngắn không nhắc project có thể relevant trong configured community/watchlist; không dùng một keyword complaint để tự coi toàn Internet là VinCons-related.
6. Source/watchlist/authorized sessions, Web/LLM provider, API keys, review threshold/SLA/retention/author fields/comments scope chưa chốt; không invent project IDs/source URLs hoặc credentials.
7. Review import/CLI đủ vòng feedback MVP; lightweight UI/alerts/lifecycle/clustering/GIS/ticket integration chỉ làm theo phase/scope PRD sau này.

Các open decisions này không chặn structural planning; source/provider cụ thể phải có trước phần implementation/live test phụ thuộc. User request giới hạn lượt đầu ở audit nên lượt này kết thúc tại Phase 0, không tự tiếp tục Phase 1.

## 9. Delivery/rollback sau các phase

Mỗi phase giao code/test/spec/docs đồng bộ, validation evidence và material limitations. Khi Phase 1 hoàn tất tạo `docs/refactor-summary.md` theo [refactor gate](refactor-plan.md#9-rollback-và-definition-of-done).

Pilot rollout giới hạn configured sources. Disable source/scheduler để rollback live; giữ raw/evidence/lineage, không tự xóa data khi chưa retention policy. Export/model/source failures phải visible và replayable. Bắt đầu production/pilot sau khi đạt quality/access/run gates thực tế, không vì đã có đủ folder hoặc file Excel synthetic.
