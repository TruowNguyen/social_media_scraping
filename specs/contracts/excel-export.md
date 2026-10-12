# Excel export contract — PLANNED

FR-13/14/16; SC-04/05. Contract này là target exporter PRD v1, chưa hoàn tất exact bốn sheets bên dưới. [Workspace Excel](../../docs/operations/dashboard-workspace.md) đã implement raw/classification export theo phiên bảng, reviews/notes và OCR evidence; không đồng nghĩa full PRD v1 acceptance. Storage là source of truth; export rerun không recrawl/LLM. V1 target có tối thiểu bốn sheets/tên/thứ tự columns, header-only khi zero records; owner/action/retention vẫn cần chốt.

| Sheet | Ordered columns |
| --- | --- |
| Signals | content_id, crawl_run_id, source_id, source, source_url, published_at, collected_at, content_type, caption/raw_text, transcript, ocr_text, visual_summary, project, location, domain, subcategory, description, relevance, confidence, analysis_evidence, media_processing_status, duplicate_group_id, review_status |
| Crawl_Runs | crawl_run_id, window, started_at, ended_at, source, status, candidate_count, keep_count, drop_count, review_count, duplicate_count, media_fail_count, llm_fail_count |
| Source_Registry | source_id, source_type, name, url/query, priority, enabled, auth_required, last_success_at, last_error |
| Review | content_id, original_domain, reviewed_domain, original_subcategory, reviewed_subcategory, original_description, reviewed_description, reviewer, reviewed_at, note |

Mapping: content_id←canonical record_id; source←platform; caption/raw_text←caption nếu có, fallback raw_text; transcript/ocr/visual_summary←successful evidence items; analysis_evidence←evidence_used (JSON array serialized); media_processing_status←media_status; auth_required←Registry requires_login; ended_at←run completed_at; window serialized `[start,end)` UTC. Source URL và lineages acquisition giữ nguyên dù Google route; target source có thể bổ sung ở schema version sau. Unknown time/metric/project/location là blank cell, không `0`, `N/A` hay fake timestamp. Timestamps export UTC ISO string. Booleans/numbers dùng native cell types; confidence numeric finite. Text/URLs untrusted ghi literal cell text, không công thức Excel.

Signals gồm KEEP và REVIEW đã qua schema validation; DROP tuyệt đối không xuất ở đây. Review chứa cần review/override; original value bất biến, reviewed value/human history từ DB, không tự ghi đè canonical original. Exact native/URL duplicate một row/content_id; query/run observations không nhân row. Near duplicate_group_id không imply cùng incident, không tự bỏ distinct claims. Source-level counts dựa observations thực, không suy từ số rows sau dedup.

Limits/truncation cell dài phải explicit và dẫn lại evidence record; không silently mất evidence hoặc vượt Excel limits. File hoàn thành ghi tạm rồi replace atomic, failure lưu export status, giữ DB và bản export cũ. Không có credential/token/profile path trong cells hoặc lỗi được export.

Acceptance XLS-01: bốn sheets và header thứ tự đúng cả zero run. XLS-02: DROP không Signals, exact duplicates không lặp, REVIEW có Review row. XLS-03: UTF-8 Việt, nulls, formula-like strings literal, UTC và numeric types. XLS-04: retry export từ DB không acquisition/enrichment. XLS-05: override lưu reviewer/time/note/history rồi export phản ánh đúng. XLS-06: source failed riêng + truthful counts và sanitized errors. Runtime tests/live output vẫn PLANNED.
