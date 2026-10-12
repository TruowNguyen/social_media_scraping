# Google social-link discovery qua SerpApi v1

Spec `google-social-discovery-feature-v1`, khởi tạo 08/10/2026; đồng bộ 11/10/2026. SerpApi adapter/quota/queue/routing có code và tests; config Google enabled/VERIFIED. Probe invalid key ngày 08/10 là lịch sử, các lượt sau đã có Account/Search pilot thành công theo [runbook](../../docs/operations/acquisition-runbook.md). Không kiểm tra lại key/quota live trong lượt đồng bộ docs; full acquisition/ACP vẫn pending.

Scope đã chốt: Google chỉ tìm link **Facebook + TikTok + YouTube**; nguồn mới vào hàng chờ. Không có Web article/News collector hoặc auto full-fetch nguồn ngoài watchlist. References: [Source Adapter](../contracts/source-adapter.md), [Discovery Queue](../contracts/discovery-queue.md), [Source Registry](../contracts/source-registry.md), [Exclusion](../contracts/exclusion-rules.md), [PRD](../product/prd.md).

## 1. Requirement IDs và provider

| ID | Requirement | PRD |
| --- | --- | --- |
| GG-001 | SerpApi Google Search provider; API key env reference, gl=vn/hl=vi; lỗi auth không empty success | FR-01/04/16 |
| GG-002 | Sinh keyword/hashtag queries theo query set và ba platform domains; giữ query original/effective/version | FR-02/04 |
| GG-003 | Parse organic links/title/snippet/position; evidence SEARCH_SNIPPET tách khỏi platform text/publication | FR-04 |
| GG-004 | Canonical URL/native identity, URL alias/redirect safe, phân biệt CONTENT_ITEM và SOURCE_CONTAINER | FR-05/12 |
| GG-005 | Nguồn ready/in-watchlist dispatch đúng adapter; nguồn mới/unknown/unsupported vào queue; không auto enable | FR-01/04 |
| GG-006 | Prefilter clear post intent trước queue/full fetch; complaints giữ; container name không đủ DROP | FR-06 |
| GG-007 | Request counters/quota bền qua rerun; max 20/run, 200/month, một trang/query; không tự mua quota | FR-16/17 |
| GG-008 | Một item nhiều queries/runs có observations đầy đủ; không tạo canonical record nền tảng google | FR-05/12 |
| GG-009 | YouTube bridge reuse metadata/caption primitives sau source gate; unknown channel giữ pending | FR-04/16 |
| GG-010 | Empty API results khác auth/rate-limit/invalid JSON/timeout; partial jobs không hủy nguồn khác | FR-16 |

Provider v1 là SerpApi `engine=google`, endpoint HTTPS `/search.json`; `SERPAPI_API_KEY` đọc từ `.env`/process environment. Chỉ lấy `organic_results`; không crawl Google HTML hoặc tự fallback DDGS/News/Apify khi lỗi. Provider API capability theo [tài liệu SerpApi](https://serpapi.com/search-api), được kiểm tra khi lập kế hoạch ngày 08/10/2026; live availability cho tài khoản này chưa được xác minh.

## 2. Query/config và ngân sách

Ví dụ YAML **đề xuất**, chưa là config runtime được tạo:

```yaml
schema_version: "acquisition-config-v1"
acquisition_profiles:
  - profile_id: "google_social_v1"
    adapter_key: "google.serpapi.social"
    credential_ref: "env:SERPAPI_API_KEY"
    mode: "SOCIAL_LINK_DISCOVERY"
    query_set_ids: ["vincons_ecosystem"]
    target_platforms: ["facebook", "tiktok", "youtube"]
    gl: "vn"
    hl: "vi"
    max_pages_per_query: 1
    max_requests_per_run: 20
    max_requests_per_month: 200
    source_timeout_seconds: 120
    max_attempts: 2
    discovered_source_policy: "QUEUE_FOR_REVIEW"
    include_comments: false
    download_media: false
    prefilter_rule_ids: ["NO_SALES_RECRUITMENT_BUY_SELL_EXCHANGE"]
```

Query builder dùng `discovery_terms` và `hashtags` của query set; không dùng tất cả operational signals để tạo tích Descartes. Default một term VinCons và một hashtag #VinCons × ba targets = tối đa sáu query jobs/run; quota có thể dừng các job sau. Truy vấn generated được quote term và serialize bằng API params, không shell interpolation; không cho term thay platform restriction.

| Target | Template / example |
| --- | --- |
| Facebook | `site:facebook.com/groups "VinCons"` hoặc `site:facebook.com/groups "#VinCons"` |
| TikTok | `site:tiktok.com "VinCons"` hoặc `site:tiktok.com "#VinCons"` |
| YouTube | `site:youtube.com "VinCons"` hoặc `site:youtube.com "#VinCons"` |

Hashtag Google là string query; không giả Google punctuation matching giống hashtag feed của TikTok. Lưu result ngay cả khi snippet không chứa literal term; actual entity/hashtag matching chỉ khi có platform evidence. Result link không thuộc allowed target host bị loại khỏi routing.

Mặc định `start=0`, một trang/query; số results thực có thể khác nhau. Spec hỗ trợ bounded pagination khi config tăng sau này: mỗi page và retry là API attempt riêng, không reuse page budget giả. Rerun dùng query/window/limits snapshot mới, không reset monthly ledger.

Request budget local được reserve atomically **trước** khi gọi API, persist theo UTC calendar month và run; cả timeout/retry tính vào local attempted-request budget. Đây là cap bảo thủ của dự án, không giả bằng billing provider. Provider trả quota exhausted thì dừng sớm dù local cap chưa hết. Không log endpoint query string có api_key.

Tại ngày lập spec, [SerpApi Free plan](https://serpapi.com/pricing) công bố 250 searches/tháng; default 200 là khoảng dự phòng, không SLA/free quota vĩnh viễn. Không tự bật paid plan/automatic renewal. Sáu requests/run cho phép khoảng 33 lượt manual không retry trong cap 200; chưa phù hợp lịch hai run/ngày cả tháng nếu không đổi query/budget.

## 3. Workflow, routing và YouTube bridge

1. Resolve enabled Google search source/query set và credentials; chốt run/window. Kiểm tra local request budget trước từng call.
2. Gọi SerpApi cho từng query job; parse organic result entries với title/link/snippet/position và acquisition time. Response invalid là extraction failure; `organic_results=[]` hợp lệ khác error payload.
3. Parse/normalize target URL trong allowlist, xác định platform và CONTENT_ITEM/SOURCE_CONTAINER. Original query/run retained trong observations.
4. Prefilter clear post intent trên available snippet/title; complaint/mixed/missing intent REVIEW. Container không xét post intent bằng tên group/channel.
5. DROP → rejection metadata only. Với eligible item, resolve approved target source bằng identity/verified aliases; chưa biết hoặc source chưa ready → queue, không full-fetch.
6. Ready item trong watchlist → fetch Facebook group item, TikTok public video hoặc YouTube bridge theo supported source type và window; giữ discovered_via=GOOGLE_SERPAPI cùng evidence/provenance platform bổ sung.
7. Container → queue/source proposal, không giả content item, không crawl toàn group/account trong Google job.
8. Persist eligible observations/queue/content và source outcome/counters; một query fail không làm mất kết quả query trước.

| Link | Routing rule |
| --- | --- |
| Facebook group permalink/posts trong approved ready group | Facebook group adapter; verified numeric/slug aliases có thể resolve cùng source |
| Facebook group root | SOURCE_CONTAINER; existing-source link hoặc source proposal, không tạo post |
| Facebook Page/profile post hoặc reel không gắn supported group | Queue UNSUPPORTED_SOURCE_TYPE; không dùng group adapter thay page adapter |
| TikTok video có creator thuộc approved ready account source | TikTok item fetch; không walk toàn account |
| TikTok video creator chưa approved | PENDING queue; TikTok search-source permission không tự bao phủ Google URL |
| TikTok profile/hashtag root | SOURCE_CONTAINER; không tự tạo account watchlist; hashtag container là đề xuất query scope |
| YouTube watch/shorts đã biết approved ready channel | YouTube item bridge lấy đúng video |
| YouTube video chưa biết channel | PENDING/UNKNOWN_ORIGIN_SOURCE; không suy channel từ title/snippet |
| YouTube channel root | SOURCE_CONTAINER; đề xuất channel, không crawl mọi upload |

Registry txt lists legacy không được coi verified sources chỉ vì có tên trong file. Bridge cần canonical source gate/ID. Reuse `fetch_video_metadata`/caption primitives sau structural refactor; không gọi whole legacy script để mặc định search nhiều videos hoặc drop metadata-only item. No transcript/media processing ngầm trong Google discovery.

## 4. Output, freshness và outcomes

Candidate platform là nền tảng URL đích, không phải google; registry acquisition source_id vẫn là Google search source, target_source_id nullable. Giữ `position` từ SERP trong Google observation metadata và `search_snippet`/title riêng. Full text chỉ xuất hiện sau adapter fetch đủ gate.

Snippet date/Google indexing time không được dùng làm published_at của bài. Khi discovery chưa có platform time thì publication_precision=UNKNOWN/window_status=UNKNOWN; ngày hint có thể giữ trong search provenance, không gán false freshness. Sau fetch áp SourceAdapter `[start,end)` và REVIEW cho time chưa xác định.

| Scenario | Expected |
| --- | --- |
| Missing/invalid API key | AUTH_REQUIRED với sanitized reason; không network khi missing key |
| Rate limit / account quota hết | RATE_LIMITED hoặc BUDGET_EXHAUSTED; provider quota hết không retry loop |
| Local 20/run hoặc 200/month đạt | Dừng trước call, ledger không reset; nguồn khác vẫn chạy |
| Valid API empty results | NO_NEW_DATA với query metadata |
| Error JSON/invalid result schema/HTML thay JSON | EXTRACTION_FAILED, không empty success |
| Timeout sau query trước thành công | PARTIAL, giữ prior results; retry còn trong query/run/request budget |
| Link ngoài allowlist/không identify được item | Không full-fetch; reason/counters hoặc queue pending nếu target container hợp lệ |

Không hứa Google index đầy đủ mọi bài mới trong 180 phút. Window dùng cho fetch và lineage; discovery có thể tìm item cũ. Không áp strict date filter mặc định để tránh bỏ nguồn chưa indexed đúng date; ưu tiên giới hạn query/results và time kiểm chứng trên platform.

## 5. Acceptance scenarios

| Case ID | Requirement IDs | Input/scenario | Expected |
| --- | --- | --- | --- |
| GG-AC-01 | GG-001/002 | VinCons và #VinCons, ba targets | Đúng engine/gl/hl/domain query, original/effective lineage; tối đa sáu jobs seed |
| GG-AC-02 | GG-003/004 | Organic results có tracking/YouTube v param/short aliases | Tracking bỏ, identity params giữ; aliases resolve bounded; không follow ngoài allowlist |
| GG-AC-03 | GG-003/005 | Group/profile/channel root và link item | Container không content record; item ready dispatch đúng adapter |
| GG-AC-04 | GG-005 | Link outside registry hoặc disabled/unverified source | PENDING queue, zero full fetch/media/LLM |
| GG-AC-05 | GG-006 | Recruitment snippet rõ và complaint có từ tuyển dụng | Clear recruitment DROP không queue raw; complaint REVIEW/PASS |
| GG-AC-06 | GG-006 | Group container tên TUYỂN DỤNG | Không DROP theo container name |
| GG-AC-07 | GG-007 | Request thứ 21/run hoặc 201/month; rerun/process restart | Không API call vượt cap; ledger persist/atomic; retry tính attempt |
| GG-AC-08 | GG-001/010 | Missing key/invalid key/429/quota exhausted/invalid JSON | Typed auth/rate/budget/extraction outcomes, no empty success |
| GG-AC-09 | GG-003/010 | Valid empty organic list và parser lỗi | NO_NEW_DATA khác EXTRACTION_FAILED |
| GG-AC-10 | GG-004/008 | Same video qua hai queries/URL aliases/rerun | Một item/queue entry, đủ observations; platform không phải google |
| GG-AC-11 | GG-005/009 | YouTube unknown channel vs known approved channel | Unknown pending; known bounded fetch đúng video, không walk channel |
| GG-AC-12 | GG-003/009 | Snippet có date nhưng chưa có platform time | published_at null/UNKNOWN; không coi snippet là full text |
| GG-AC-13 | GG-007/010 | Một query fail sau prior queue/content persist | Giữ partial results, jobs khác tiếp tục, no auto paid fallback |
| GG-AC-14 | GG-008 | Google phát hiện video đã có từ approved TikTok search | Attach observation, không refetch/auto approve creator |

Tất cả cases PLANNED. Offline tests mock provider bằng fixture synthetic/redacted, không dùng real key. Live gate cần API response thật với query/gl/hl/date/usage metadata, đối chứng result URLs và routing ready/pending. Ba target queries phải được exercised; empty hợp lệ có evidence được report, không claim coverage toàn nền tảng. Stored evidence không chứa API key/raw provider headers.

## 6. Dependencies và rollout

SerpApi key là tài nguyên riêng của Google; Facebook/TikTok profiles không dùng cho search API. Registry/source verification, query builder, prefilter, queue/review storage, canonical observations và Facebook/TikTok/YouTube bridge là dependencies integration. API feasibility có thể probe sớm trước feature implementation trong cap thử; chưa được gọi trong bước specs này. LLM/Excel/scheduler theo phase riêng ở [specs README](../README.md).
