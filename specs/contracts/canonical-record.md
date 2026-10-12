# Canonical record v1 — PLANNED

**Đồng bộ 11/10/2026:** post/comment/reply đã dùng [conversation-record-v2](conversation-record.md) và [group tracing](../features/facebook-group-tracing.md). Contract canonical v1 dưới đây là target post-only riêng; không lưu raw DROP của v1 không áp cho tracing v2. Không flatten child text/ngày vào bài cha.

Đặc tả target CORE-01/03/06 và SC-01–07; full canonical-v1 schema/projection chưa hoàn tất. Acquisition storage/raw conversation đã có runtime theo [trạng thái hiện hành](../../docs/current-state.md), không được tự coi là exact canonical-v1. [Candidate](source-adapter.md) là input acquisition; schema breaking cần version/migration, không thay JSON legacy âm thầm.

| Field | Type / rule |
| --- | --- |
| schema_version | literal `canonical-record-v1` |
| record_id | nonempty string immutable; canonical content ID |
| platform | `facebook|tiktok|youtube`; future platform thêm có version policy |
| platform_item_id | string/null; ID native, không registry ID |
| source_url, canonical_url | absolute HTTPS URL; original URL giữ provenance; normalized URL giữ identity params |
| source_id | registry ID acquisition; không overwrite bằng target source khi Google route |
| target_source_id | registry ID đích/null; chỉ điền sau xác minh membership |
| crawl_run_id | ID observation đầu; quan hệ observations là lineage đầy đủ |
| observations | array các observation IDs; tối thiểu một với item acquisition mới |
| content_type | `text|image|video|mixed|unknown` |
| title, raw_text, caption | string/null; unavailable null, available-empty `""` |
| hashtags | array string, giá trị thực đọc được; Google hashtag query không là evidence hashtag |
| author | object/null `{platform_author_id, display_name, profile_url}`; từng field string/null |
| engagement | object `{views, likes, comments, shares}`, từng value nonnegative integer/null; unknown khác zero |
| published_at, collected_at, discovered_at, updated_at | RFC3339 UTC `...Z`; publication/edit nullable; collected/discovered bắt buộc |
| publication_precision | `INSTANT|APPROXIMATE|DATE_ONLY|UNKNOWN`; unknown time null |
| window_status | `IN_WINDOW|OUT_OF_WINDOW|UNKNOWN`; chỉ INSTANT kiểm chứng nằm [start,end) là IN_WINDOW |
| media_refs | array structured refs từ candidate; không imply download đã chạy |
| evidence | [unified-evidence-v1](unified-evidence.md)/null trước resolver |
| media_status | `NOT_REQUESTED|PENDING|PROCESSING|AVAILABLE|PARTIAL|UNAVAILABLE|FAILED|SKIPPED` |
| prefilter_decision | `PASS|REVIEW`; clear DROP chỉ minimal rejection audit, không canonical raw record |
| relevance | `KEEP|DROP|REVIEW|null`; null trước classification, không suy từ PASS |
| domain | bốn domains PRD/null khi unclassified |
| subcategory, project, location, description | string/null; subcategory phụ thuộc domain, project/location grounded |
| confidence | finite number [0,1]/null trước classification |
| evidence_used | array evidence types đã dùng, không toàn bộ evidence sẵn có |
| drop_reason, review_reason | reason string/null; DROP cần drop_reason, REVIEW cần review_reason |
| processing_state | `ACQUIRED|ENRICHMENT_PENDING|ENRICHED|REVIEW_REQUIRED|FAILED` |
| classification_state | `PENDING|CLASSIFIED|UNCLASSIFIED`; UNCLASSIFIED là trạng thái xử lý nhãn chưa xác định, không domain |
| duplicate_group_id | string/null; exact identity không tạo record mới, near là relationship |
| duplicate_relationships | array `{record_id, type: EXACT_CONTENT|NEAR_CONTENT, confidence}`; không tự merge incidents |
| legacy_payload | object/null để giữ financial/quality fields từ migration, không phục vụ nghiệp vụ mới |

Identity unique theo platform + native ID; fallback canonical URL. Identity và observation là hai bảng/khái niệm riêng. Observation gồm observation_id, candidate_id, record_id, crawl_run_id, source_id, target_source_id nullable, query_id/type/search_keyword/effective_query nullable, discovered_via, window start/end UTC, discovery/extraction timestamps/status/precision. Cùng video hai query/run có một item nhưng thêm observation; retry observation cùng candidate không nhân bản. Các query đã tìm thấy giữ đầy đủ. Không dùng hash text rỗng để gộp.

Clear prefilter DROP chỉ lưu bảy metadata fields theo [exclusion contract](exclusion-rules.md). Downstream DROP sau classification có thể có evidence của record đã PASS/REVIEW nhưng không vào Signals. Retention raw downstream cần quyết định riêng; không lấy rule metadata-only cho clear commercial DROP làm quyền lưu raw trước filter.

| Legacy → canonical | Rule |
| --- | --- |
| record_id | legacy ID giữ ở legacy_payload; identity mới giải bằng native ID, không xóa file cũ |
| Source.Source_id → platform_item_id | string; không map thành source_id |
| Source.platform → platform | explicit mapping YouTube→youtube, TikTok→tiktok; ngoài scope cần adapter/version riêng |
| Source.url → source_url | canonical_url derived, có fixture alias/params |
| Content.raw_text → raw_text | Không suy loại evidence khi provenance thiếu |
| time_stamps → timestamps | Parse UTC; N/A → null/UNKNOWN, không gán collected làm publication |
| Engagement → engagement | Legacy zero không thể biết observed hay missing; migration đánh dấu uncertain provenance |
| asset_mention/sentiment/quality | Giữ legacy_payload, không đổi thành operational confidence |
| filename → query/source/run | Không fabricate lineage lịch sử từ filename; migration cần context explicit và ghi provenance |

Acceptance CAN-01: null/zero và publication precision validation. CAN-02: native identity + nhiều observations/rerun/crash không thêm item. CAN-03: missing timestamp không được xác nhận fresh. CAN-04: old payload preserved, missing provenance không bị invented. CAN-05: clear DROP không tạo canonical raw row. Mapped FR-04/05/11/12/16/17; acceptance runtime còn PLANNED.
