# Source Registry, dự án và cấu hình runtime

Threads bổ sung `threads.yaml`: platform/provider enabled, query theo project, version/CAS, ambiguous/archive gates, readiness và budgets. Provider hiện tại `THREADS_BROWSER`, profile riêng `sessions/browser/threads`; không cần Threads token. Lịch lưu độc lập trong `platform_schedules`, cấu hình YAML không tự bật lịch. Pilot đã xác minh một keyword Vũ Yên, chưa xác minh API hoặc exact topic tags. [Hướng dẫn vận hành](../docs/operations/threads-acquisition.md).

**VinCons 13/10:** config v3 có bảy query, ưu tiên `"VinCons"` và tên + vấn đề; `limits.unverified_conversations_per_query=2` (hợp lệ 0–20, mặc định 2 nếu config cũ chưa có). Scope gate lấy aliases từ `projects.yaml`, không suy entity bằng tên query, không bắt caption phải chứa issue. Không tự thêm tên công trường chưa xác nhận. [Kết quả pilot và giới hạn](../docs/operations/threads-vincons-scope-20261013.md).

Đồng bộ với YAML/code ngày **11/10/2026**. Registry hiện có **14 group Facebook đã bật và xác minh**, gồm 7 nguồn VinCons và 7 nguồn VinWonders Vũ Yên. Phạm vi/tình trạng nghiệm thu: [trạng thái hiện hành](../docs/current-state.md).

| File | Vai trò hiện tại |
| --- | --- |
| [sources.yaml](sources.yaml) | 14 Facebook groups, ID ổn định, URL, metadata/provenance và access/enable gates |
| [acquisition.yaml](acquisition.yaml) | Google/TikTok search scopes và watchlist ACTIVE `vincons_acquisition_v1` |
| [watchlists.yaml](watchlists.yaml) | Watchlist seed `vincons_facebook_seed_v1`, 7 VinCons groups; vẫn DRAFT/disabled |
| [projects.yaml](projects.yaml) | Hai phạm vi bật: VinCons (tổ chức/nhiều công trường) và VinWonders Vũ Yên; aliases, hashtags, discovery_terms, source_ids |
| [keywords.yaml](keywords.yaml) | Query sets và operational signals; không mặc định keyword match là relevance |
| [exclusions.yaml](exclusions.yaml) | Rule intent thương mại/tuyển dụng, được acquisition v1 tham chiếu |
| [taxonomy/v1](taxonomy/v1/common.yaml) | Taxonomy runtime 1.0.0 APPROVED/enabled, khác snapshot draft trong specs |
| [Source Registry contract](../specs/contracts/source-registry.md) | Schema/config fields, references và readiness rules |

## Nguồn và watchlists

14 entries trong `sources.yaml` đều có `enabled=true`, `verification_status=VERIFIED`, `access_verified=true`, `requires_login=true`. Cấu hình dùng profile Facebook đã lưu; không suy rằng public group luôn đọc được anonymous hoặc nguồn sẽ không gặp access error ở lượt khác. Mẫu kiểm tra nguồn và backfill chưa chứng minh coverage đầy đủ.

| Phạm vi | Source IDs |
| --- | --- |
| VinCons | `fb_group_139108668844789`, `fb_group_880263084346112`, `fb_group_2249052912495339`, `fb_group_669205626514948`, `fb_group_suanhathuduc`, `fb_group_144732306144575`, `fb_group_1675953926771851` |
| VinWonders Vũ Yên | `fb_group_vinwondersroyalparkhaiphong`, `fb_group_reviewhaiphong.vinwondersvuyen`, `fb_group_1280258833374137`, `fb_group_1463368281672061`, `fb_group_1500004461400003`, `fb_group_681283966885365`, `fb_group_718379403948782` |

Watchlist ACTIVE chứa 16 source references: 14 Facebook, `google_social_vincons` enabled/VERIFIED và `tt_search_vincons` disabled/PENDING_VERIFICATION. Watchlist seed disabled không ngăn dashboard chọn các group trong watchlist ACTIVE. Trạng thái readiness được [Registry loader](../engine/registry.py) kiểm tra mỗi lượt; không chỉnh metadata để che lỗi runtime.

Group mapping là ngữ cảnh, không chứng minh mọi bài/comment thuộc dự án. Không gán địa điểm từ slug hoặc tên group. VinCons là `ORGANIZATION_PORTFOLIO`, không phải một công trường duy nhất. Quy tắc aliases và phân biệt project match/model evidence: [runbook dự án](../docs/operations/project-filter.md).

## Policy lưu raw và loại nội dung

| Luồng | Quy tắc |
| --- | --- |
| Dashboard Facebook raw v2 / conversation CLI | Lưu POST/COMMENT/REPLY trước filter/classify, giữ raw kể cả DROP. Intent bài cha không chặn child; OCR ảnh POST bổ sung evidence riêng |
| Acquisition v1 / Google routing | Rule `NO_SALES_RECRUITMENT_BUY_SELL_EXCHANGE` chạy trước deep fetch, kiểm tra lại trước reuse/output. Clear DROP không lưu raw, chỉ rejection audit bảy trường |
| Collector legacy | Đọc `.env`, `keywords/*.txt` và `sources/*.txt` theo CWD; `examples/` chỉ là template để copy. Không dùng exclusion YAML |

Rule v1 đã được implement trong [prefilter.py](../src/acquisition/prefilter.py), không còn là config chưa thực thi. Sales, tuyển dụng, thuê, mua bán, vay nợ, trao đổi hàng hóa rõ intent bị loại; complaint/scam/nợ lương/mixed intent giữ REVIEW. Chữ “tuyển dụng” trong tên group hoặc một keyword riêng lẻ không đủ để loại cả nguồn. Filter raw v2 còn có [content intents](../src/analysis/content_intents.py); `PASS/REVIEW` của heuristic không tự là kết luận model hoặc sự cố đã xác minh.

## Thay đổi cấu hình và vận hành

1. Giữ ID ổn định; kiểm tra alias/numeric ID nếu slug trỏ đến nguồn đã có.
2. Thêm project/source/query references hợp lệ, ghi provenance; chỉ bật nguồn đã xác minh và adapter hỗ trợ.
3. Giữ key trong `.env`/environment, profile trong `sessions/browser/`; không đưa key/cookies vào YAML.
4. Chạy validation offline trước lượt crawl:

```powershell
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.acquisition_cli validate
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.acquisition_cli sources list
```

Lịch dashboard lưu riêng tại `sessions/acquisition/dashboard-schedule.json`, không nằm trong `schedule_profile=null` của watchlist v1. [Lịch raw v2](../docs/operations/dashboard-crawl-schedule.md) dùng hai khung giờ Việt Nam, có lượt chốt cuối khung. Raw, Google/acquisition, jobs, reviews dùng chung DB mặc định `sessions/acquisition/acquisition.sqlite3`.

Các xác nhận public thủ công và probe login/invalid-key ban đầu ngày 08/10 được giữ trong [verification lịch sử](../docs/operations/facebook-source-verification.md) và [implementation report](../docs/acquisition-implementation.md); không dùng chúng thay cấu hình hiện hành.
