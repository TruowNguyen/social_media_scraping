# Source Registry / Watchlist configuration contract v1

**Threads PLANNED:** [feature](../features/threads-adapter.md) đề xuất `THREADS_SEARCH` theo project/query version, provider capabilities và lịch riêng. Query source không phải group; profile từ kết quả search không tự bật giám sát. Type này chưa có trong `engine.registry.SUPPORTED`; [kế hoạch triển khai](../../docs/implementation-plan-threads.md) và [contract đa nền tảng](multi-platform-conversations.md) là thiết kế, không phải config runtime.

Contract khởi tạo 08/10/2026, đồng bộ trạng thái 11/10/2026. `sources.yaml` hiện có 14 Facebook groups VERIFIED/enabled; `acquisition.yaml` thêm Google enabled, TikTok disabled và watchlist ACTIVE. Watchlist seed trong `watchlists.yaml` vẫn DRAFT/disabled. Loader/gates/adapters/storage đã implement; [config index](../../config/README.md) và [trạng thái hiện hành](../../docs/current-state.md) phân biệt metadata, implementation và full live acceptance.

Requirement links: PRD FR-01 Source Registry, FR-02 Dictionary, FR-04 Acquisition, FR-06 Negative filtering và FR-16 Source status. [Source Adapter](source-adapter.md) và [Discovery Queue](discovery-queue.md) đã có runtime và contract tests; full product/ACP vẫn pending.

## Files và version

`config/sources.yaml`: `schema_version=source-registry-config-v1`, list `sources`.

`config/watchlists.yaml`: `schema_version=watchlist-config-v1`, list `watchlists`.

`config/keywords.yaml`: `schema_version=keyword-config-v1`, list `query_sets`.

`config/exclusions.yaml`: `schema_version=exclusion-config-v2`, list `exclusion_sets`. Loader/runtime v1 đã thực thi prefilter policy v2, không diễn giải như v1 SIGNALS_ONLY. Raw conversation v2 có policy lưu-before-filter riêng.

YAML UTF-8; identifier và numeric-looking references là strings. Loader dùng safe parser, không thực thi YAML tags; schema/version/reference gates đã có code và tests.

## Source fields

| Field | Type / meaning |
| --- | --- |
| `source_id` | Nonempty unique string, ổn định qua rename group/URL alias |
| `platform`, `source_type` | Hiện seed: facebook / FACEBOOK_GROUP; future support phải có adapter/type validation |
| `name` | Display label; chưa được coi là tên group thật khi name_verified=false |
| `platform_group_ref` | Numeric ID hoặc slug nguyên dạng string; slug không được giả làm numeric ID |
| `url` | HTTPS Facebook group URL; identity phải đối chiếu platform_group_ref |
| `project`, `location` | Nullable source context; không tự propagate thành fact ở record |
| `priority` | P0/P1/P2; source polling priority riêng với domain business priority |
| `enabled` | Boolean; false tuyệt đối không dispatch acquisition |
| `monitoring_scope` | Seed scope RECENT_POSTS_AND_VIDEOS; không mặc định comments/private/history |
| `access_type` | UNKNOWN/PUBLIC/AUTHORIZED; UNKNOWN không cho dispatch live |
| `requires_login` | bool hoặc null khi chưa biết; runtime không coi null là false |
| `verification_status` | PENDING_VERIFICATION/VERIFIED/REJECTED; state curatorial, không phải source-run status |
| `name_verified`, `access_verified` | Booleans; access_verified=false không cho dispatch live |
| `name_verification_method` | Nullable string; USER_MANUAL_CONFIRMATION cho tên người dùng đã tra cứu và cung cấp; không có nghĩa browser đã đối chiếu |
| `name_verified_on` | Nullable ISO date string; có giá trị khi name_verified=true, đi kèm method |
| `access_verification_method` | Optional nullable string; USER_MANUAL_CONFIRMATION ghi nhận public/truy cập thủ công do người dùng xác nhận, chưa chứng minh phiên browser của dự án |
| `access_verified_on` | Optional nullable ISO date; đi kèm access_verification_method khi access_verified=true |
| `submitted_on` | ISO date string, ngày người dùng gửi seed |
| `owner`, `notes` | Nullable string / string; không chứa credential/session secrets |

Một source chỉ đủ điều kiện live khi enabled=true, verification_status=VERIFIED, access_verified=true, access_type khác UNKNOWN, requires_login đã xác định và có adapter/access method phù hợp. Đây là proposed validation/dispatch rule; YAML hiện chưa được runtime đọc. Empty source batch vẫn phải khác AUTH_REQUIRED/SOURCE_UNAVAILABLE sau integration.

## Watchlist/reference rules

Xác nhận thủ công có thể đặt access_verified=true với method/date rõ ràng. verification_status vẫn PENDING_VERIFICATION tới khi nhu cầu login, phiên browser và phương thức acquisition của dự án được kiểm chứng. access_verified=true riêng lẻ không vượt qua dispatch gate; probe_access vẫn cần ở mỗi lượt chạy.

Watchlist có unique `watchlist_id`, name/status/enabled, source_ids, query_set_ids, exclusion_set_id, optional prefilter_rule_ids, domain_priorities, retrieval và nullable schedule_profile.

- `source_ids` phải trỏ existing source; không trùng ID trong cùng watchlist. Source có thể thuộc nhiều watchlist.
- `query_set_ids` và `exclusion_set_id` phải resolve vào đúng config files; IDs không được trùng trong collection của chúng.
- `prefilter_rule_ids` phải unique và resolve vào enabled rules trong exclusion set mà watchlist sử dụng; unknown rule không được silently bỏ qua.
- Draft watchlist hiện disabled. Enabled watchlist chỉ dispatch những source vừa enabled vừa đủ validation/access; không bật source theo inheritance.
- `retrieval.mode=RECENT_SOURCE_ITEMS`, require_keyword_match=false cho broad acquisition; không có nghĩa all candidates được KEEP.
- include_comments=false và content_types=[POST,VIDEO] là scope seed.
- lookback_minutes/max_items_per_source phải là positive integers, không chấp nhận bool. Seed defaults là provisional; scheduler/readiness được quyết định riêng.
- schedule_profile=null không được ngầm chọn production schedule; scheduled run cần profile hợp lệ sau khi scheduler integration có contract.
- Domain priorities chỉ SITE_ACCESS_CONGESTION=P0 và CUSTOMER_COMPLAINT=P1 ở seed; không thay source priorities.

## Mở rộng acquisition đã chốt, chưa áp dụng vào config seed

Feature contracts: [Facebook public groups](../features/facebook-adapter.md), [TikTok keyword/hashtag](../features/tiktok-search.md), [Google social discovery](../features/google-social-discovery.md). Các fields/types sau là phần mở rộng draft để implement cùng loader; không tự thêm vào config live hoặc tăng version đang release trong lượt specs này.

| Source type dự kiến | Platform | Gate / capability |
| --- | --- | --- |
| FACEBOOK_GROUP | facebook | Ready/enabled và access_type=PUBLIC; login thủ công nếu public UI cần; discover recent + fetch group item |
| TIKTOK_SEARCH | tiktok | Ready/enabled query scope; keyword/hashtag modes từ query set; public video result không cần creator account watchlist |
| GOOGLE_SEARCH | google | Ready/enabled search scope + SerpApi credential ref; discover social URLs, không tự cấp target approval |
| TIKTOK_ACCOUNT | tiktok | Approved/ready public creator source cho Google target-item fetch; không auto walk whole account |
| YOUTUBE_CHANNEL | youtube | Approved/ready public channel cho Google item bridge; native channel ID hoặc verified alias, không phỏng đoán name match |

Registry platform `google` khác candidate platform: Google candidate vẫn có platform facebook/tiktok/youtube và acquisition source_id của Google. `target_source_id` nullable trỏ nguồn đích được duyệt, không overwrite lineage source_id. Source query permission TikTok không tự blanket-approve Google-discovered creator/video.

Optional proposed fields: `adapter_key`, `capabilities`, `browser_profile_ref`, `credential_ref`, `query_set_ids`, `verified_url_aliases` và `platform_source_ref` cho creator/channel. `platform_group_ref` của Facebook giữ nguyên; native source/item IDs luôn string. Reference vào credential chỉ là `env:SERPAPI_API_KEY`, không có secret trong YAML. Browser refs mặc định dưới ignored `sessions/`, không trỏ profile cá nhân.

Loader tương lai phải validate supported platform/type/mode/capability, reference và access policy; source chưa có adapter không được im lặng coi empty success. Query config cũng disabled cho tới access verification. Existing source-registry-config-v1 seed vẫn hợp lệ; field additions chỉ draft, không thay meaning của fields cũ. Khi release schema mới phải có compatibility/version gate theo README.

Queue APPROVED chỉ bind/create source proposal: source mới enabled=false, verification_status=PENDING_VERIFICATION, access_verified=false, access_type=UNKNOWN, requires_login=null khi chưa rõ. “Draft” không thêm enum DRAFT vào verification_status. Source readiness và watchlist membership phải được xác minh/bật riêng trước fetch, kể cả reviewer đã APPROVED.

Public source yêu cầu login dùng access_type=PUBLIC và requires_login=true; AUTHORIZED trong enum registry chung không mở phạm vi private group của Facebook v1. Source name/proposed context không chứng minh content relevance hoặc item access. Runtime health/locks/monthly budget và approval history ở storage, không ghi counters vào YAML.

## Query/exclusion rules

Query set lưu entity aliases, project/location dictionaries, discovery terms/hashtags và operational signals riêng. Keyword match đơn lẻ không chứng minh relevance. Accent-insensitive matching chỉ dùng bản normalized để so khớp; lưu original UTF-8 text.

Exclusion set hiện mode EXCLUDE_CLEAR_INTENT, hard_drop_on_keyword=false và preserve_operational_complaints=true. Rule mới loại sales/recruitment/real estate listing/buy-sell/goods exchange theo primary intent rõ, trước deep fetch/media/LLM; ambiguous hoặc operational complaint được giữ để review/classify. GENERAL_PR vẫn là signal ngoài rule mới. Các negative intents không phải top-level domains. DROP lưu rule/reason và rejection metadata, không lưu raw content bị loại. Chi tiết ở [exclusion-rules.md](exclusion-rules.md).

## Acceptance/checks

Đã kiểm tra offline bộ seed: YAML parse được; đủ bảy URL người dùng; source IDs/URLs và set IDs không trùng; reference resolution; bool/null/string và positive quotas phù hợp; draft sources/watchlist disabled; unknown names/project/location/access giữ explicit. Kiểm tra này không xác minh live group existence/privacy/access.

**Snapshot curatorial ngày 08/10/2026 (lịch sử):** sáu tên được người dùng xác nhận; tên 2249052912495339 khi đó chưa xác minh. Bảy groups PUBLIC/access_verified theo USER_MANUAL_CONFIRMATION, vẫn disabled/PENDING_VERIFICATION tại thời điểm đó. Metadata vận hành mới nhất xem config index; snapshot này không ghi đè nguồn đã enabled/VERIFIED.

Khi implement loader/runtime cần contract tests tương ứng cho duplicate/unknown references, wrong types/platform/source URL, unknown versions, enabled-unverified source, disabled dispatch và source outcome isolation. Runtime metrics/health lưu DB, không thuộc config YAML. Schema/behavior change phải version/migration theo [specs ownership](../README.md).

Acceptance mở rộng: AD-AC-01 (dispatch gate), DQ-AC-02/04 (approval khác readiness), FB-AC-01/02 (slug/name/access), TT-AC-01/02 (query types), GG-AC-03/04/11 (target routing/container/unknown channel). Tất cả PLANNED, chưa phải test execution evidence.
