# TikTok keyword và hashtag browser search v1

Ngày: **08/10/2026**. Spec: `tiktok-search-feature-v1`. Đã có browser keyword/hashtag search độc lập và kiểm chứng offline/DOM giả lập. Probe keyword bị CAPTCHA, hashtag selector mismatch; chưa live acquisition acceptance/ACP. Legacy account mode giữ nguyên. [Implementation/evidence](../../docs/acquisition-implementation.md).

Đối tượng: Engineering/Ops/QA. References: [PRD](../product/prd.md), [Source Adapter](../contracts/source-adapter.md), [Source Registry](../contracts/source-registry.md), [Exclusion](../contracts/exclusion-rules.md). Phương án đã chốt là Playwright Chromium; Google discovery là feature độc lập và không thay live TikTok search acceptance.

## 1. Scope và requirement IDs

| ID | Requirement | PRD |
| --- | --- | --- |
| TT-001 | Tạo hai chế độ KEYWORD_SEARCH và HASHTAG_SEARCH trên UI TikTok; không giới hạn trusted accounts | FR-01/02/04 |
| TT-002 | Query original/normalized, stable query ID và type được giữ; Unicode/hashtag không mất provenance | FR-02/04 |
| TT-003 | Enumerate video results theo quota/window; sort latest chỉ khi UI hỗ trợ; không break vì item cũ xen mới | FR-04/17 |
| TT-004 | Discovery caption/hashtag/metadata → prefilter trước full fetch/media/transcript | FR-06 |
| TT-005 | Video ID/URL, caption, creator, time/metrics/media refs theo candidate schema; missing evidence giữ REVIEW | FR-04, FR-07 downstream |
| TT-006 | Một video nhiều query/run có một canonical và nhiều observations | FR-05/12/17 |
| TT-007 | Profile browser riêng, auth thủ công, locks/budgets và typed failures; source khác tiếp tục | FR-16 |
| TT-008 | Giữ legacy account-mode/keyword-account-mode, CLI/output và baseline behavior | Compatibility |
| TT-009 | Query result không là proof VinCons/project/location/relevance; ASR/LLM không chạy trong discovery | FR-02/06, FR-08/11 downstream |

Scope v1 là video public được UI search/hashtag trả về. Không search creators/users/LIVE/sounds, thu followers/social graph/comments, tải video hàng loạt hoặc reverse-engineer mobile/private endpoints. Không hứa tất cả video có keyword/hashtag được trả về.

## 2. Query và source semantics

- Registry source type mới dự kiến `TIKTOK_SEARCH`, platform=tiktok, capabilities discover/fetch_item; source/query job phải ready và được bật riêng. Query set hiện có `vincons_ecosystem` là seed, không là runtime hiện đang đọc YAML.
- KEYWORD_SEARCH gửi original UTF-8 term đã trim outer whitespace; không bỏ dấu tiếng Việt hoặc tự thêm từ operational để thu hẹp seed broad query. Query mở rộng chỉ từ terms được cấu hình.
- HASHTAG_SEARCH nhận `#VinCons` hoặc `VinCons`, bỏ một leading `#` khi mở hashtag target và giữ original trong search_keyword. Empty/whitespace-containing hashtag bị config validation từ chối, không âm thầm biến thành keyword query.
- Stable query ID do config xác định, tách type và original term; thay keyword semantics tạo query version/ID mới. Matching case/accent normalization chỉ là signals downstream, không đổi provenance query.
- Video từ một approved search query có thể thu dù creator chưa có account watchlist. Creator chỉ là origin metadata; không auto-register/enable theo dõi account đó.
- Với Google-discovered URL, creator chưa được duyệt vẫn đi [Discovery Queue](../contracts/discovery-queue.md). Không lấy quyền của TikTok search source để tự fetch bất kỳ Google video URL.

Ví dụ YAML **đề xuất**, chưa có loader/registry implementation:

```yaml
schema_version: "acquisition-config-v1"
acquisition_profiles:
  - profile_id: "tiktok_search_browser_v1"
    adapter_key: "tiktok.search.browser"
    browser_profile_ref: "sessions/browser/tiktok"
    headless: true
    lookback_minutes: 180
    max_items_per_query: 50
    source_timeout_seconds: 120
    max_attempts: 2
    include_comments: false
    download_media: false
    prefilter_rule_ids: ["NO_SALES_RECRUITMENT_BUY_SELL_EXCHANGE"]
query_examples:
  - query_id: "tt_vincons_keyword_v1"
    query_set_id: "vincons_ecosystem"
    mode: "KEYWORD_SEARCH"
    query_type: "KEYWORD"
    search_keyword: "VinCons"
    enabled: false
  - query_id: "tt_vincons_hashtag_v1"
    query_set_id: "vincons_ecosystem"
    mode: "HASHTAG_SEARCH"
    query_type: "HASHTAG"
    search_keyword: "#VinCons"
    enabled: false
```

## 3. Workflow và reuse

1. Engine chốt run/window/quota và resolve source/query/exclusion. Không đọc accounts list làm search space cho hai mode mới.
2. Lock profile `sessions/browser/tiktok`; Chromium headless, session đã bootstrap khi cần. Probe search/hashtag page đúng mode trước enumeration.
3. KEYWORD_SEARCH dùng UI video search; HASHTAG_SEARCH dùng hashtag target/feed. Ghi effective query và observed order. Sort latest chỉ khi thao tác UI thực sự thành công; nếu không thì RELEVANCE/MIXED/UNKNOWN.
4. Read video cards/caption/hashtags/metadata tối thiểu, tạo candidate và apply prefilter. Không thu comments/transcript hoặc mở profile creator.
5. DROP clear intent chỉ audit. PASS/REVIEW được identity dedup; fetch video page public để bổ sung caption/time/metrics khi còn cần và còn budget.
6. Persist eligible canonical/observations và source outcome; release lock/context. Video thiếu caption/time giữ REVIEW, không silently skip như một số legacy path.

Reusable legacy primitives gồm video ID/metadata fetch, caption parsing và media helpers sau refactor. Không gọi `extract_video_text` nguyên khối trong discovery vì có thể chạy ASR/fallback trước exclusion. Approved fetch/backend phải giữ thiếu dữ liệu rõ ràng và không thêm bypass behavior. Media references chưa là transcript hoặc visual evidence.

Hai mode mới thuộc SmartCity entrypoint với mode explicit. TikTok legacy chạy qua `python -m engine.runtime --platform tiktok`, giữ account-only output và first-matched-keyword bucketing theo baseline; không đổi SCRAPE_MODE cũ thành global search âm thầm. Root script đã được bỏ theo yêu cầu cleanup.

## 4. Output, time và failure

Output `acquisition-candidate-v1`: platform=tiktok, candidate_kind=CONTENT_ITEM, native video ID string, canonical video URL, query lineage bắt buộc; discovered_via lần lượt TIKTOK_KEYWORD_BROWSER/TIKTOK_HASHTAG_BROWSER. Creator reference không được thay registry source_id của search job.

Caption/hashtags giữ original text; matched keyword chỉ là evidence match khi content thực có, không fabricated từ query hit. Timestamp exact trong window mới IN_WINDOW; date-only/relative label/unknown theo SourceAdapter. Metrics absent hoặc không parse chắc chắn để null.

| Scenario | Expected |
| --- | --- |
| Query page parse thành công, zero video results | NO_NEW_DATA, query/type/window rõ |
| “No results” UI thật so với cards không parse được | NO_NEW_DATA khác EXTRACTION_FAILED |
| Login expired/CAPTCHA/access restriction | Typed AUTH_REQUIRED/ACCESS_DENIED; stop job |
| Rate limit/network timeout | Bounded retry, tối đa hai attempts trong 120 giây/query; hết budget ghi failure/partial |
| Relevance listing có video cũ trước mới | Không chronological break; tiếp tục tới cap/end/no-more-results/deadline |
| Cap 50 trước khi biết hết kết quả | coverage_limited=true, stop_reason=ITEM_LIMIT; không claim global coverage |
| Video removed/private sau discovery | Item unavailable/denied; giữ permitted discovery metadata/reason, không invent full text |
| Text trống/không có phụ đề | METADATA_ONLY/REVIEW, ASR không auto chạy trong discovery |

Search window không được giả là platform-side time filter khi UI không hỗ trợ. Lọc freshness dựa time từng item có evidence; việc video không xuất hiện vì ranking/indexing được ghi như giới hạn acquisition.

## 5. Acceptance scenarios

| Case ID | Requirement IDs | Input/scenario | Expected |
| --- | --- | --- | --- |
| TT-AC-01 | TT-001/008 | VinCons keyword, không có trusted accounts | UI global video search vẫn được gọi; legacy account mode giữ baseline |
| TT-AC-02 | TT-001/002 | `#VinCons` hashtag | Hashtag target khác keyword mode; original/effective values lưu riêng |
| TT-AC-03 | TT-002 | “VinCons kẹt xe”, hashtag rỗng hoặc chứa whitespace | Unicode giữ nguyên; invalid hashtag bị reject trước browser |
| TT-AC-04 | TT-003 | Latest UI có/không có; old item xen new item | Observed order phản ánh thực tế; không bỏ video mới sau video cũ |
| TT-AC-05 | TT-004 | Caption sales/recruitment/đổi hàng rõ | DROP audit only; zero fetch/media/ASR/LLM/raw persistence |
| TT-AC-06 | TT-004/009 | Complaint có từ bán hàng, trao đổi ca làm | Không auto-DROP; PASS/REVIEW theo intent |
| TT-AC-07 | TT-005 | Video thiếu caption/metrics/exact time | Nulls/missing reasons/REVIEW, không skip hoặc bịa timestamp |
| TT-AC-08 | TT-006 | Cùng native ID từ keyword+hashtag+rerun | Một canonical, đủ observations và lineage |
| TT-AC-09 | TT-007 | Source auth/429/parser failure, source khác healthy | Typed failures, bounded retries, source isolation |
| TT-AC-10 | TT-003/007 | Cap/deadline hết sau vài video | Kết quả giữ, stop reason/coverage flags rõ |
| TT-AC-11 | TT-001/007 | Empty UI thật vs mất selectors | NO_NEW_DATA khác EXTRACTION_FAILED |
| TT-AC-12 | TT-007/008 | Profile conflict, exception cleanup, old CLI demo | Lock/cleanup pass; legacy characterization unchanged |
| TT-AC-13 | TT-009 | Query hit nhưng caption không nói project/location | Không tự gán entity/project/location/domain/relevance |

Tất cả cases PLANNED. Offline parsing/routing tests dùng fixtures synthetic hoặc redacted; CI không gọi TikTok live. Live gate cần riêng một keyword và một hashtag truy cập được, có sample video metadata đối chứng UI cùng profile/thời điểm/limit. Account-filter hoặc Google URL không đạt gate này. Empty đã đối chứng hợp lệ được report nhưng cần nonempty sample riêng để xác nhận extraction.

## 6. Dependencies và rollout

Tài nguyên: Playwright Chromium, profile TikTok bootstrap khi required, source/search verification và query set. Pilot mặc định VinCons/#VinCons, cap 50/query, 180 phút lookback, 120 giây/query và 1.200 giây/run. Media/comments tắt. Pilot search feasibility sớm; feature integration sau baseline refactor, registry/session/prefilter/storage contracts. [Specs README](../README.md) định nghĩa thứ tự và evidence states.
