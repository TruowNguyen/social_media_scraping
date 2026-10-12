# Facebook public-group browser adapter v1

Spec `facebook-adapter-feature-v1`, khởi tạo 08/10/2026; đồng bộ 11/10/2026. Browser adapter có offline fixtures và pilot xác minh mẫu nguồn; config hiện bật 14 groups. LOGIN_REQUIRED là probe ban đầu, không phải trạng thái hiện hành toàn watchlist. Full-window/ACP chưa đạt. Dashboard đã dùng [raw conversation v2](../../docs/operations/dashboard-raw-v2.md); v1 contract dưới đây vẫn mô tả post acquisition và prefilter riêng.

Đối tượng: Engineering xây collector và Ops/QA đánh giá acquisition. Nguồn yêu cầu: [PRD](../product/prd.md), [Source Registry](../contracts/source-registry.md), [Source Adapter](../contracts/source-adapter.md), [Exclusion](../contracts/exclusion-rules.md). Trong lựa chọn đã chốt, Facebook dùng browser; không dùng Apify/Groups Graph API làm provider v1.

## 1. Scope và requirement IDs

Bảy group VinCons seed ban đầu là `139108668844789`, `880263084346112`, `2249052912495339`, `669205626514948`, `suanhathuduc`, `144732306144575`, `1675953926771851`. [sources.yaml](../../config/sources.yaml) hiện thêm 7 Vũ Yên groups, tổng 14 VERIFIED/enabled. Metadata/provenance lấy từ Registry; source gate luôn cần kiểm tra khi chạy, không suy full coverage từ enable flags.

| ID | Requirement | PRD |
| --- | --- | --- |
| FB-001 | Chỉ dispatch FACEBOOK_GROUP public, ready, enabled và thuộc enabled watchlist; explicit access probe không tự enable | FR-01/04 |
| FB-002 | Playwright Chromium profile riêng; login thủ công khi cần, một job/profile và không dùng profile Chrome cá nhân | FR-16, NFR security |
| FB-003 | Discover recent posts/videos với fixed window/quota, ghi observed order; không bỏ item mới sau old pinned post | FR-04/17 |
| FB-004 | Prefilter caption/metadata trước full permalink fetch; loại clear commerce/recruitment/exchange, giữ complaint/mixed intent | FR-06 |
| FB-005 | Fetch text mở rộng, native post ID/permalink, time/provenance, author/engagement/media refs khi hiển thị | FR-04 |
| FB-006 | Missing caption/time/media giữ metadata/review; giá trị unknown không suy đoán | FR-04, FR-07 downstream |
| FB-007 | Numeric group ID và slug giữ stable registry identity; aliases chỉ được dùng sau verification | FR-01/05/12 |
| FB-008 | Source outcome phân biệt empty/auth/denied/unavailable/parser failure; giữ partial items và source isolation | FR-16 |
| FB-009 | Rerun/window overlap không tạo canonical duplicate; observations giữ nguồn/run | FR-05/12/17 |
| FB-010 | Không tự bắt keyword trong group watchlist; không drop cả group dựa tên; comments/media download ngoài acquisition v1 | FR-02/06 |

Không thu Facebook Page/profile/private group/comments ở bản này. Source xuất hiện trong Google chỉ được full-fetch khi gate nguồn đích đã đạt; xem [Discovery Queue](../contracts/discovery-queue.md). Các nguồn mới ngoài bảy seed có thể đăng ký sau cùng gate, không có auto-discovery toàn Facebook.

## 2. Workflow và access/session

1. Engine resolve source/watchlist/exclusion, chốt UTC window và job budget; disabled/unverified source bị skip trước browser crawl.
2. Acquire lock profile Facebook, mở Chromium headless với profile riêng; kiểm tra group visibility/login/access. Public cần login có thể dùng session đã bootstrap; private vẫn ACCESS_DENIED.
3. Đọc listing gần đây; dùng sort mới nhất nếu UI có tùy chọn. Ghi thứ tự thực tế LATEST/RELEVANCE/MIXED/UNKNOWN, không giả định listing là chronological.
4. Tạo candidate CONTENT_ITEM từ ID/permalink + caption/time/metadata nhìn thấy. Đọc text tối thiểu vào bộ nhớ để prefilter; không dump HTML/response/screenshot.
5. DROP rõ intent: rejection audit only, không mở permalink. PASS/REVIEW: dedup identity, kiểm tra window, rồi fetch item trong budget nếu còn cần dữ liệu.
6. Mở permalink đúng group, mở rộng text sau filter; lấy metadata còn thiếu. Không đi theo profile author để thu thông tin khác hoặc mở comments.
7. Persist eligible content/observations, source counters/outcome; đóng context/release lock mọi exit path. Media/LLM/export xử lý ở các phase sau.

Browser không tự join group, không solve CAPTCHA/stealth/proxy rotation để vượt block. Auth expired báo AUTH_REQUIRED; operator chạy bootstrap interactive riêng. Secret/profile content không nằm trong YAML hoặc test fixtures.

Hợp đồng profile: `sessions/browser/facebook` là mặc định dự kiến, được bao phủ bởi ignore `sessions/` hiện có. Directory lock bao trùm cả bootstrap và crawl. Playwright không hỗ trợ đồng thời nhiều instance cùng user-data directory; profile riêng theo [Playwright BrowserType](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context).

## 3. Input/config và output

Ví dụ YAML **đề xuất**, không phải config mới đã được tạo hoặc loader hiện đã đọc:

```yaml
schema_version: "acquisition-config-v1"
acquisition_profiles:
  - profile_id: "facebook_public_groups_v1"
    adapter_key: "facebook.group.browser"
    browser_profile_ref: "sessions/browser/facebook"
    headless: true
    lookback_minutes: 180
    max_items_per_source: 100
    source_timeout_seconds: 120
    max_attempts: 2
    include_comments: false
    download_media: false
    prefilter_rule_ids: ["NO_SALES_RECRUITMENT_BUY_SELL_EXCHANGE"]
source_config_example:
  source_id: "fb_group_139108668844789"
  platform: "facebook"
  source_type: "FACEBOOK_GROUP"
  name: "Hội Nhóm Công Nhân Vincons Xây Dựng Nam Bắc"
  platform_group_ref: "139108668844789"
  url: "https://www.facebook.com/groups/139108668844789"
  enabled: false
  access_type: "UNKNOWN"
  access_verified: false
  verification_status: "PENDING_VERIFICATION"
  requires_login: null
```

Source example chỉ trích fields liên quan, không thay schema đầy đủ ở Registry. Source ready phải có `access_type=PUBLIC`; enum AUTHORIZED trong registry chung không cấp phạm vi private cho adapter này. Watchlist hiện giữ `retrieval.mode=RECENT_SOURCE_ITEMS`, `require_keyword_match=false`, include_comments=false. Default time budget 120 giây/group bao gồm listing/full-fetch/retry; toàn run tối đa 1.200 giây.

Output theo `acquisition-candidate-v1`; `source_id` là group registry, `query_id/query_type/search_keyword=null`, `discovered_via=FACEBOOK_GROUP_BROWSER`. Source URL là bài, `origin_source_ref` là group đã resolve. `target_source_id` bằng group registry với direct group acquisition, hoặc được bind riêng khi fetch Google candidate.

| Dữ liệu | Extraction requirement |
| --- | --- |
| Item identity | Native ID từ permalink/metadata có provenance; nếu không resolve được dùng canonical URL, không dùng text/title làm ID |
| Text | Caption listing và `raw_text` full sau fetch giữ riêng; UTF-8 nguyên bản, không ép English |
| Timestamp | Absolute time khi xác định được → UTC INSTANT; relative/date-only/missing → provenance + UNKNOWN window nếu chưa resolve |
| Engagement | Lấy khi hiển thị và parse chắc chắn; ký hiệu rút gọn không xác định giữ null thay vì đoán số chính xác |
| Media | Chỉ references/type từ item; URL unavailable không làm mất item |
| Evidence | Browser caption/full text có method; không claim transcript/OCR/visual khi chưa xử lý |

## 4. Failure và coverage

| Scenario | Expected outcome |
| --- | --- |
| Listing parse thành công, không có bài mới | NO_NEW_DATA với counters thật; group có clear DROP vẫn SUCCESS + drop count |
| Login hết hạn/CAPTCHA | AUTH_REQUIRED hoặc ACCESS_DENIED với reason; không retry vô hạn |
| Group private/không đủ quyền | ACCESS_DENIED; không coi session là public verification |
| Group removed/not found | SOURCE_UNAVAILABLE |
| Listing đổi cấu trúc, không parse được | EXTRACTION_FAILED, không empty success |
| Timeout sau vài items | PARTIAL; giữ items/observations đã persist, source sau tiếp tục |
| Đạt cap 100 trước khi biết hết window | SUCCESS trong quota với coverage_limited=true, stop_reason=ITEM_LIMIT |
| Thời gian bài chỉ “2 giờ trước” | Không bịa exact published_at; giữ label/APPROXIMATE + UNKNOWN hoặc resolve qua permitted fetch |

Không break chỉ vì old pinned item. Bài unknown-time không tính confirmed freshness và cần REVIEW nếu vẫn thiếu time sau fetch. Media browser tự hiển thị có thể phát sinh asset requests ban đầu; rule cấm tác vụ tải/lưu media/deep processing sau DROP, không tuyên bố không có request ban đầu.

## 5. Acceptance scenarios

Tất cả case **PLANNED**; offline fixtures và live evidence chưa được chạy trong bước viết specs.

| Case ID | Requirement IDs | Input/scenario | Expected |
| --- | --- | --- | --- |
| FB-AC-01 | FB-001/007 | Numeric group ID và slug `suanhathuduc` | Resolve source ổn định; slug không giả numeric ID; alias chỉ sau verification |
| FB-AC-02 | FB-001 | Disabled hoặc tên đã xác nhận nhưng access chưa verified | Không crawl, SKIPPED; không auto enable |
| FB-AC-03 | FB-003/009 | Timestamp đúng start/end; rerun fixed window | Start included/end excluded; không duplicate canonical |
| FB-AC-04 | FB-003 | Old pinned post trước post mới | Post mới vẫn được xét; observed order được ghi |
| FB-AC-05 | FB-004 | Caption “Tuyển công nhân, nhận hồ sơ” | DROP/RECRUITMENT; zero full fetch/media/LLM/raw persistence |
| FB-AC-06 | FB-004/010 | “Cổng ùn, chờ vào trong buổi tuyển dụng” ở group tên tuyển dụng | Không auto-DROP; giữ PASS/REVIEW để classify |
| FB-AC-07 | FB-005 | Bài dài có See more | Expand sau prefilter, lưu full text và caption provenance riêng |
| FB-AC-08 | FB-006 | Video không caption, media URL không truy cập được | Metadata retained/REVIEW; không invent text/evidence |
| FB-AC-09 | FB-002/008 | Login expired/private group/CAPTCHA | Typed auth/denied outcome; stop source, release context/lock |
| FB-AC-10 | FB-008 | Empty listing thật so với selector mismatch | NO_NEW_DATA khác EXTRACTION_FAILED |
| FB-AC-11 | FB-008/009 | Một group lỗi sau item đã persist, group khác healthy | Partial data giữ; source sau chạy; rerun idempotent |
| FB-AC-12 | FB-005/010 | Metrics absent, comments link có sẵn | Metrics null; không mở comments hoặc author profile |
| FB-AC-13 | FB-002 | Hai jobs/profile và secret-like error | Lock ngăn concurrency; không log session/secret/raw DOM |

Live gate: ít nhất một seed group được xác minh public, source probe thành công và có bounded acquisition đối chứng UI cùng window. Ghi group/source/run, privacy evidence, limit/order, counts, fields thiếu và kết quả exclusion. Empty run đối chứng được ghi đúng nhưng không đủ chứng minh full-post extraction; cần một accessible item sample. Coverage là configured accessible watchlist, không toàn Facebook. Chưa có live evidence ở spec v1.

## 6. Dependencies và sequencing

Feasibility public access thực hiện sớm trước đầu tư media/LLM. Production integration phụ thuộc structural refactor compatibility gate, registry loader, browser profile locking, exclusion runtime, canonical storage/observations và SourceAdapter. SDK/browser installation thuộc implementation sau; lượt specs không sửa requirements, config source hoặc bật crawl. Gate và rollout chung ở [specs README](../README.md).
