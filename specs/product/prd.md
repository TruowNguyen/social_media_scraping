# PRD: SmartCity Operational Social Listening – VinCons

## 1. Thông tin chung

| Mục | Nội dung |
| --- | --- |
| Tên tính năng / sản phẩm | SmartCity Operational Social Listening – VinCons |
| Phiên bản tài liệu | v0.1 |
| Ngày cập nhật | 08/10/2026 |
| Trạng thái | Draft |
| Product Manager (chủ sở hữu) | TBD |
| Design | TBD |
| Engineering lead | TBD |
| QA | TBD |
| Data / AI | TBD |
| Các bên liên quan khác | SmartCity Operations, Customer Experience/CS, Data/AI, Legal/Compliance, IT/Security |
| Liên kết | TBD: Figma, Jira/Epic, technical design, source registry, evaluation dashboard |

### Lịch sử thay đổi

| Phiên bản | Ngày | Người sửa | Nội dung thay đổi |
| --- | --- | --- | --- |
| v0.1 | 08/10/2026 | Draft | Bản PRD đầu tiên, chốt scope MVP theo nguồn dữ liệu, crawl giờ cao điểm, ưu tiên ùn tắc ra/vào công trường và complaint khách hàng |

---

## 2. Tóm tắt (TL;DR)

SmartCity cần một cơ chế phát hiện sớm các tín hiệu vận hành xuất hiện trên mạng xã hội và web công khai, ưu tiên các vấn đề **ùn tắc/check-in/check-out tại cổng công trường** và **phản ánh/khiếu nại của khách hàng** liên quan đến VinCons/các dự án mục tiêu. Hiện dữ liệu phân tán trên Facebook community groups, Google/Web Search, TikTok và YouTube; nhiều nội dung là video, cách diễn đạt không thống nhất và bị nhiễu mạnh bởi bán hàng, bất động sản, tuyển dụng, quảng cáo/PR.

Giải pháp đề xuất là một pipeline thu thập theo **watchlist + keyword/hashtag discovery**, chạy tập trung vào các khung giờ cao điểm, chuẩn hóa nội dung text/media, loại bỏ noise, khử trùng lặp và dùng LLM để gán `domain`, `subcategory`, `description`, `project/location`, `relevance` và `confidence`. Kết quả MVP được lưu có lineage và xuất Excel phục vụ review/vận hành. Hệ thống **không cam kết coverage toàn bộ Internet hoặc toàn bộ Facebook/TikTok**, mà tối ưu khả năng phát hiện tín hiệu trong tập nguồn và truy vấn đã được cấu hình.

---

## 3. Bối cảnh và vấn đề

### 3.1 Vấn đề cần giải quyết

Khối vận hành SmartCity cần nắm bắt sớm các vấn đề phát sinh tại dự án/công trường, nhưng các phản ánh thực tế có thể xuất hiện ở nhiều nơi: Facebook group cộng đồng/cư dân/công nhân, TikTok, YouTube, web/news và các kết quả tìm kiếm được index trên Google.

Các khó khăn chính:

1. **Discoverability thấp:** bài đăng từ trang cá nhân hoặc group không phải lúc nào cũng được search engine/index/API expose.
2. **Dữ liệu đa nguồn, không đồng nhất:** post, comment, video, hình ảnh, caption, transcript, metadata khác nhau theo nền tảng.
3. **Noise cao:** nhiều kết quả liên quan dự án nhưng thực chất là bán nhà, cho thuê, môi giới, booking, tuyển dụng hoặc PR.
4. **Keyword không đủ:** người dùng có thể mô tả vấn đề bằng ngôn ngữ tự nhiên như “đứng chờ 30 phút mới vào được”, không nhất thiết dùng từ “ùn tắc” hay “check-in lỗi”.
5. **Video URL không phải lúc nào LLM cũng đọc trực tiếp được:** cần lớp Media Processing/Resolver để chuyển video thành caption, transcript, OCR và visual summary.
6. **Dữ liệu trùng lặp:** cùng một vấn đề có thể xuất hiện nhiều lần do repost, share, comment hoặc nội dung gần giống nhau.
7. **Nhu cầu mang tính thời điểm:** ùn tắc/check-in/check-out có xác suất xuất hiện cao quanh giờ vào ca/ra ca, do đó crawl đều 24/7 không tối ưu chi phí.

MVP tập trung vào hai domain có giá trị vận hành cao nhất:

- **P0 – `SITE_ACCESS_CONGESTION`:** ùn tắc, xếp hàng, chờ đợi, check-in/check-out, kiểm soát ra/vào, barrier/QR/face recognition và các vấn đề làm chậm luồng người/xe tại cổng công trường.
- **P1 – `CUSTOMER_COMPLAINT`:** phản ánh/khiếu nại của khách hàng/cư dân/người sử dụng dịch vụ về việc chậm xử lý, không phản hồi, lỗi hệ thống/app, thái độ phục vụ hoặc vấn đề dịch vụ khác.

### 3.2 Bằng chứng

Hiện tại chưa có baseline định lượng chính thức. Các bằng chứng/nhận định đã xác định trong giai đoạn discovery:

- Nguồn quan tâm chính được xác định là **Facebook community groups, Google/Web Search theo keyword/hashtag, TikTok và YouTube**.
- Vấn đề ưu tiên cao nhất là **ùn tắc ra/vào công trường**, sau đó là **complaint khách hàng**.
- Nhiễu cần loại bỏ sớm gồm **bán hàng/bất động sản, tuyển dụng, marketing/PR và nội dung không liên quan vận hành**.
- Nhiều nội dung quan trọng có thể là video, trong khi LLM API không đảm bảo đọc trực tiếp URL Facebook/TikTok; cần pipeline tách media thành evidence mà model có thể xử lý.
- Nhu cầu crawl ưu tiên theo **khung giờ cao điểm buổi sáng 05:30–08:00 và khung giờ cao điểm buổi chiều**; giờ chiều cần xác nhận với vận hành.

Baseline về số lượng nguồn, số candidate/run, tỷ lệ relevant, tỷ lệ duplicate, tỷ lệ media xử lý được và chi phí/run sẽ được đo trong POC.

### 3.3 Vì sao làm bây giờ

- Nhu cầu theo dõi vận hành phụ thuộc vào **tính kịp thời**; nếu tín hiệu được phát hiện sau nhiều giờ/ngày thì giá trị xử lý giảm đáng kể.
- Việc thử nghiệm sớm giúp xác định **feasibility của data access**, đặc biệt Facebook group và TikTok, trước khi đầu tư sâu vào dashboard hoặc classifier phức tạp.
- Một pipeline thu thập + chuẩn hóa tốt sẽ tạo nền dữ liệu dùng lại cho các use case sau này như issue clustering, trend tracking, alerting và automated reporting.

---

## 4. Mục tiêu và chỉ số thành công

### 4.1 Mục tiêu

- **Mục tiêu kinh doanh:** cung cấp cho khối vận hành SmartCity một nguồn tín hiệu bổ sung để phát hiện sớm các vấn đề có khả năng ảnh hưởng hoạt động tại dự án/công trường và trải nghiệm khách hàng.
- **Mục tiêu người dùng:** giúp analyst/operations reviewer giảm thời gian tự search thủ công, nhận được danh sách case mới đã được lọc noise, gán tag và tóm tắt theo format thống nhất.
- **Mục tiêu dữ liệu:** xây được pipeline có lineage, dedup, confidence và evidence level để có thể đánh giá chất lượng nguồn/crawler/LLM theo từng run.
- **Mục tiêu kỹ thuật:** tách độc lập source adapters, media processing và LLM enrichment để thay đổi platform/model mà không làm hỏng toàn pipeline.

### 4.2 Chỉ số thành công (Success metrics)

> Các target dưới đây là **mục tiêu đề xuất cho POC/MVP**, cần hiệu chỉnh sau khi có baseline 1–2 tuần đầu.

| Chỉ số | Hiện tại (baseline) | Mục tiêu đề xuất | Thời hạn | Cách đo / nguồn dữ liệu |
| --- | --- | --- | --- | --- |
| Precision của tập `KEEP` sau filtering + LLM | Chưa có | >= 80% trên mẫu review thủ công tối thiểu 200 record | Cuối POC | Human review sample |
| Tỷ lệ structured output hợp lệ từ LLM | Chưa có | >= 98% | MVP | Validation log |
| Tỷ lệ duplicate lọt vào Excel | Chưa có | <= 5% | MVP | Duplicate audit |
| Tỷ lệ scheduled run hoàn tất không lỗi toàn pipeline | Chưa có | >= 95% | 2 tuần pilot | Run logs |
| Tỷ lệ video candidate truy cập được có ít nhất 1 evidence usable: caption/transcript/visual | Chưa có | >= 80% | Cuối POC | Media processing logs |
| Tỷ lệ record có `source_url`, `published_at`, `crawl_run_id`, `domain/relevance` đầy đủ | Chưa có | >= 98% | MVP | Data quality checks |
| Thời gian từ lúc kết thúc crawl window đến khi có file Excel review | Chưa có | <= 30 phút với cấu hình pilot | Pilot | Scheduler/export logs |
| Coverage trong **configured watchlist** | Chưa có | >= 90% các item accessible được xác định bằng kiểm tra đối chứng trong sample window | Pilot | Manual source audit |

### 4.3 Chỉ số bảo vệ (Guardrail metrics)

| Chỉ số | Ngưỡng chấp nhận |
| --- | --- |
| Truy cập dữ liệu ngoài quyền/nguồn cho phép | 0 trường hợp cố tình bypass access control |
| Record thiếu source URL hoặc source identifier | < 2% |
| LLM tạo project/location không có evidence | 0 trường hợp được phép auto-accept; phải để `null/unknown` hoặc review |
| Tỷ lệ pipeline thất bại toàn bộ vì một source lỗi | 0%; source lỗi phải isolated và các source khác tiếp tục |
| Tỷ lệ export chứa record đã bị DROP | < 1% |
| Lộ API key/credential trong log/export | 0 |

### 4.4 Non-goals (không làm trong phiên bản này)

- Không cam kết crawl 100% Facebook/TikTok hoặc 100% bài public trên Internet.
- Không crawl nội dung private/friends-only hoặc cố tình bypass CAPTCHA/access control.
- Không xây social graph hoặc theo dõi cá nhân cụ thể.
- Không tự động kết luận một phản ánh trên social là sự thật đã được xác minh.
- Không tự động tạo ticket/dispatch đội xử lý trong MVP.
- Không xây dashboard realtime đầy đủ trong MVP; output chính là database nội bộ + Excel.
- Không làm sentiment analysis chi tiết nếu không phục vụ trực tiếp `SITE_ACCESS_CONGESTION` hoặc `CUSTOMER_COMPLAINT`.
- Không xây issue lifecycle/clustering đa ngày ở MVP; đây là phase sau.

---

## 5. Người dùng và kịch bản sử dụng

### 5.1 Đối tượng người dùng

| Persona / phân khúc | Mô tả | Nhu cầu chính | Nỗi đau hiện tại |
| --- | --- | --- | --- |
| Operations Analyst / SmartCity Reviewer | Người theo dõi tình hình vận hành | Nhận danh sách case mới, đúng scope, có evidence và source | Search thủ công nhiều nguồn, noise cao, khó tổng hợp |
| Operations Manager | Người cần xem các issue đáng chú ý để ưu tiên kiểm tra | Biết có case gì mới, ở dự án nào, thuộc loại gì | Không có nguồn tổng hợp thống nhất, tín hiệu đến muộn |
| Data/AI Owner | Người vận hành pipeline và đánh giá chất lượng model | Theo dõi source coverage, lỗi crawler, precision, confidence | Khó trace vì sao một case được gán tag |
| Admin/Source Curator | Người quản lý watchlist/keyword/source | Thêm/xóa group, account, hashtag, project alias | Source thay đổi thường xuyên và phụ thuộc discovery |

### 5.2 User stories

- **US-01:** Là một Operations Analyst, tôi muốn sau mỗi khung giờ cao điểm nhận danh sách các case mới có khả năng liên quan đến ùn tắc/ra-vào công trường để tôi review nhanh thay vì tự search nhiều nền tảng.
- **US-02:** Là một Operations Analyst, tôi muốn các nội dung bán hàng, bất động sản, tuyển dụng và PR được loại bỏ trước để giảm noise.
- **US-03:** Là một Reviewer, tôi muốn mỗi case có link nguồn, evidence level, tag, description và confidence để biết vì sao hệ thống xếp case đó vào phạm vi quan tâm.
- **US-04:** Là một Operations Manager, tôi muốn export Excel theo format thống nhất để dùng cho báo cáo và chia sẻ nội bộ.
- **US-05:** Là một Admin/Source Curator, tôi muốn cấu hình project aliases, keywords, hashtags, Facebook groups/accounts và crawl windows mà không phải sửa core code.
- **US-06:** Là một Data/AI Owner, tôi muốn source lỗi được tách riêng, có retry/log rõ ràng và không tạo duplicate khi chạy lại.
- **US-07:** Là một Reviewer, tôi muốn sửa tag/description của case để tạo dữ liệu feedback cho việc cải thiện rules/prompt/model sau này.

### 5.3 Luồng người dùng (User flow)

**Luồng chính:**

1. Admin cấu hình source registry, project aliases, keywords/hashtags, exclusion rules và crawl schedule.
2. Scheduler kích hoạt run tại khung giờ đã cấu hình.
3. Source adapters thu thập candidate từ Facebook group/watchlist, Google/Web Search, TikTok và YouTube.
4. Hệ thống chuẩn hóa metadata cơ bản: source, URL, published time, collected time, text/caption, author/display name nếu cần và được phép.
5. Hệ thống áp dụng dedup sơ bộ và negative filtering.
6. Với media/video cần thêm evidence, Media Resolver lấy caption/transcript/OCR/key-frame summary khi truy cập được.
7. LLM nhận **structured evidence**, không chỉ URL, để gán `relevance`, `domain`, `subcategory`, `description`, `project`, `location`, `confidence`.
8. Validation kiểm tra output schema và các trường bắt buộc.
9. Record low-confidence/ambiguous được gán `REVIEW`.
10. Dữ liệu hợp lệ được lưu cùng lineage và xuất Excel.
11. Reviewer kiểm tra các case mới và sửa tag/description nếu cần.

**Luồng phụ / ngoại lệ:**

- Source yêu cầu đăng nhập lại hoặc access hết hạn → source run = `PARTIAL/FAILED`, các source khác vẫn tiếp tục.
- Video không tải/resolve được → giữ caption/metadata, `media_processing_status=UNAVAILABLE`, giảm confidence nếu cần.
- LLM timeout/invalid JSON → retry có giới hạn; nếu vẫn lỗi, record = `UNCLASSIFIED/REVIEW`.
- Không có candidate mới → vẫn ghi `crawl_run` thành công với `0 new records`.
- Nội dung trùng URL/post ID/hash → không tạo record mới; chỉ cập nhật `last_seen` nếu thiết kế storage hỗ trợ.

---

## 6. Phạm vi và yêu cầu chức năng

### 6.1 Trong phạm vi / ngoài phạm vi

| Trong phạm vi (In scope) | Ngoài phạm vi (Out of scope) |
| --- | --- |
| Facebook community groups/pages/accounts trong watchlist mà hệ thống được phép truy cập | Private/friends-only content không được cấp quyền |
| Google/Web Search theo keyword/hashtag/project alias | Guarantee toàn bộ search index hoặc toàn bộ Internet |
| TikTok keyword/hashtag/account discovery theo khả năng source adapter | Bypass anti-bot/CAPTCHA/platform controls |
| YouTube keyword search và video metadata | Realtime streaming 24/7 |
| Crawl theo khung giờ cao điểm | Full historical backfill nhiều tháng/năm ở MVP |
| Negative filtering | Tự động xác minh đúng/sai của claim social |
| Media processing: caption, transcript, OCR/key frames khi khả thi | Computer vision chuyên sâu cho mọi frame |
| LLM tagging + description | Auto-action/auto-close incident |
| Dedup + lineage | Advanced cross-platform event clustering |
| SQLite/PostgreSQL nội bộ + Excel export | Dashboard production đầy đủ |
| Human review/override cơ bản | Workflow ticketing/CRM tích hợp sâu |

### 6.2 Danh sách yêu cầu chức năng

| Mã | Yêu cầu | Ưu tiên | User story | Tiêu chí chấp nhận (Acceptance criteria) |
| --- | --- | --- | --- | --- |
| FR-01 | Source Registry cho phép cấu hình Facebook groups/pages, TikTok accounts/hashtags, YouTube queries và Web Search queries | P0 | US-05 | Cho trước một source hợp lệ, khi thêm vào config và chạy validation, source được lưu với `source_id`, `type`, `status`, `priority` và có thể enable/disable |
| FR-02 | Project/Entity Dictionary cho phép cấu hình VinCons, project names, aliases, locations và operational keywords | P0 | US-05 | Khi thêm alias mới, run kế tiếp sử dụng alias mà không cần sửa code collector |
| FR-03 | Scheduler hỗ trợ nhiều crawl windows trong ngày | P0 | US-01 | Hệ thống chạy theo cấu hình; mặc định pilot sáng 05:30–08:00, chiều TBD; mỗi run có `crawl_run_id`, start/end/status |
| FR-04 | Source adapters thu thập candidate mới theo freshness/lookback | P0 | US-01 | Candidate phải có tối thiểu `source`, `source_url/id`, `collected_at`; khi có published time thì phải lưu `published_at` |
| FR-05 | Hỗ trợ overlapping lookback và incremental dedup | P0 | US-06 | Chạy lại cùng khoảng thời gian không tạo duplicate record cho cùng source item |
| FR-06 | Negative filtering cho SALES/REAL_ESTATE/RECRUITMENT/GENERAL_PR/IRRELEVANT | P0 | US-02 | Record có intent rõ thuộc nhóm loại bỏ không được đưa vào sheet `Signals`; lý do DROP phải được lưu |
| FR-07 | Media Resolver xử lý content type video/image/text theo fallback hierarchy | P0 | US-03 | Với video accessible, hệ thống cố lấy caption/transcript/visual evidence; nếu thất bại không làm mất record và phải ghi status |
| FR-08 | LLM enrichment theo schema cố định | P0 | US-01, US-03 | Output chỉ hợp lệ nếu có schema version và các trường bắt buộc; invalid output bị retry/review, không silently accept |
| FR-09 | Taxonomy MVP gồm `SITE_ACCESS_CONGESTION`, `CUSTOMER_COMPLAINT`, `OTHER_RELEVANT`, `IRRELEVANT` | P0 | US-01 | Mỗi record sau enrichment có đúng một top-level domain hoặc `REVIEW/UNCLASSIFIED` |
| FR-10 | Hệ thống hỗ trợ subcategory cho hai domain ưu tiên | P0 | US-01 | `SITE_ACCESS_CONGESTION` hỗ trợ tối thiểu ENTRY_QUEUE, EXIT_QUEUE, VEHICLE_CONGESTION, WORKER_CONGESTION, CHECKIN_BOTTLENECK, ACCESS_CONTROL_FAILURE, EXTERNAL_TRAFFIC_IMPACT; complaint hỗ trợ tối thiểu SERVICE_DELAY, NO_RESPONSE, APP_SYSTEM_ISSUE, STAFF_ATTITUDE, UNRESOLVED_ISSUE, OTHER_COMPLAINT |
| FR-11 | Relevance + confidence + evidence level | P0 | US-03 | Mỗi KEEP/REVIEW record có `relevance`, `confidence`, `analysis_evidence`; không đủ evidence thì confidence phải phản ánh mức thấp hơn hoặc chuyển REVIEW |
| FR-12 | Dedup theo URL/source ID/content hash và near-duplicate cơ bản | P0 | US-06 | Exact duplicate không được export lặp; near-duplicate được gán `duplicate_group_id` khi confidence đủ |
| FR-13 | Excel export chuẩn hóa | P0 | US-04 | Sau run thành công, tạo workbook có tối thiểu `Signals`, `Crawl_Runs`, `Source_Registry`, `Review` |
| FR-14 | Human review/override | P1 | US-07 | Reviewer có thể sửa domain/subcategory/description và hệ thống lưu `original_value`, `reviewed_value`, `reviewed_at`, `reviewer` |
| FR-15 | Late reconciliation run | P1 | US-01 | Có thể cấu hình một run buổi tối để bắt các complaint được đăng trễ; record vẫn dedup với run trước |
| FR-16 | Run monitoring và source-level status | P0 | US-06 | Mỗi run ghi số candidate, KEEP/DROP/REVIEW, duplicate, media fail, LLM fail, export status theo source |
| FR-17 | Manual rerun theo source/time window | P1 | US-06 | Operator có thể rerun một source bị fail mà không cần chạy lại toàn pipeline và không sinh duplicate |

### 6.3 Quy tắc nghiệp vụ

1. **Retrieval ưu tiên recall; filtering ưu tiên precision.** Search/crawl không cần hiểu toàn bộ issue, chỉ cần tạo candidate pool đủ rộng trong phạm vi source đã cấu hình.
2. **Không hard-drop chỉ vì một negative keyword.** Ví dụ có từ “bán hàng” nhưng nội dung là complaint về nhân viên bán hàng thì vẫn có thể KEEP.
3. Record được chia tối thiểu thành `KEEP`, `DROP`, `REVIEW` trước khi export.
4. `SITE_ACCESS_CONGESTION` có mức ưu tiên nghiệp vụ cao hơn `CUSTOMER_COMPLAINT` trong MVP.
5. Không được suy diễn `project/location` nếu evidence không đủ; sử dụng `null/unknown`.
6. Social post được coi là **reported signal/claim**, không phải fact đã xác minh.
7. LLM không được dùng URL như nguồn duy nhất nếu model/provider không hỗ trợ đọc URL đó; phải dùng evidence đã trích xuất.
8. Khi media unavailable, record vẫn được giữ nếu caption/text đủ relevance; `analysis_evidence` phải phản ánh đúng dữ liệu đã dùng.
9. Exact duplicate không được tính là case mới.
10. Mỗi record phải trace được tới `crawl_run_id`, `source_id` và `source_url/source_item_id`.
11. Chỉ thu thập và lưu thông tin cá nhân ở mức cần thiết cho use case; tránh lưu dữ liệu nhạy cảm không phục vụ vận hành.

### 6.4 Taxonomy MVP

#### A. `SITE_ACCESS_CONGESTION`

- `ENTRY_QUEUE`: xếp hàng/chờ vào cổng.
- `EXIT_QUEUE`: xếp hàng/chờ ra cổng.
- `VEHICLE_CONGESTION`: xe tải/xe ben/xe công trường ùn tại khu vực cổng.
- `WORKER_CONGESTION`: công nhân/người ra vào tập trung đông, xếp hàng.
- `CHECKIN_BOTTLENECK`: check-in/check-out/chấm công làm chậm luồng vào/ra.
- `ACCESS_CONTROL_FAILURE`: QR/thẻ/face recognition/barrier/access control lỗi hoặc chậm.
- `EXTERNAL_TRAFFIC_IMPACT`: ùn tại cổng lan ra đường/khu vực giao thông bên ngoài.

#### B. `CUSTOMER_COMPLAINT`

- `SERVICE_DELAY`: chậm xử lý/chờ lâu.
- `NO_RESPONSE`: không phản hồi/không liên hệ được.
- `APP_SYSTEM_ISSUE`: lỗi app/hệ thống/dịch vụ số.
- `STAFF_ATTITUDE`: thái độ/hành vi phục vụ.
- `UNRESOLVED_ISSUE`: phản ánh nhiều lần nhưng chưa xử lý.
- `OTHER_COMPLAINT`: complaint phù hợp scope nhưng chưa map được nhóm trên.

#### C. Negative intents

- `REAL_ESTATE_LISTING`
- `SALES_MARKETING`
- `RECRUITMENT`
- `GENERAL_PR`
- `IRRELEVANT`

### 6.5 Các trạng thái đặc biệt

| Tình huống | Hành vi mong đợi |
| --- | --- |
| Trạng thái rỗng | Run vẫn `SUCCESS`; export có header và `0 new records`; không coi là lỗi |
| Đang tải/xử lý | Ghi trạng thái theo step/source; tránh chạy chồng cùng source/window |
| Lỗi mạng/API | Retry có backoff; vượt retry thì đánh dấu source `FAILED/PARTIAL` và tiếp tục source khác |
| Không đủ quyền truy cập | Không bypass; ghi `ACCESS_DENIED/AUTH_REQUIRED`; alert operator |
| CAPTCHA/anti-bot | Dừng source đó và yêu cầu intervention; không tự động vượt cơ chế bảo vệ |
| Video inaccessible | Giữ metadata/caption, `media_processing_status=UNAVAILABLE` |
| LLM invalid output | Retry giới hạn; sau đó `REVIEW/UNCLASSIFIED` |
| Dữ liệu cực lớn | Áp dụng source quota/batch/pagination; không làm mất lineage |
| Website thay đổi selector/HTML | Source adapter fail isolated; health check báo lỗi |

### 6.6 Phân quyền

| Vai trò | Xem | Tạo config | Sửa tag/review | Xóa/disable source | Rerun |
| --- | --- | --- | --- | --- | --- |
| Admin | ✓ | ✓ | ✓ | ✓ | ✓ |
| Data/AI Owner | ✓ | ✓ | ✓ | Disable source | ✓ |
| Operations Reviewer | ✓ |  | ✓ |  |  |
| Viewer/Manager | ✓ |  |  |  |  |

### 6.7 Thiết kế

MVP không yêu cầu UI phức tạp. Các bề mặt tối thiểu:

1. **Config:** YAML/JSON hoặc admin page đơn giản cho source registry, keywords, aliases, exclusions, schedule.
2. **Run monitoring:** CLI/log + bảng run status; có thể dùng Prefect UI hoặc dashboard kỹ thuật tương đương.
3. **Output:** Excel là giao diện nghiệp vụ chính trong MVP.
4. **Review:** ban đầu có thể review trực tiếp trên sheet/CSV hoặc lightweight internal page; cần lưu feedback vào storage thay vì chỉ sửa file mà mất lineage.

#### Excel MVP

**Sheet `Signals`**

- `content_id`
- `crawl_run_id`
- `source_id`
- `source`
- `source_url`
- `published_at`
- `collected_at`
- `content_type`
- `caption/raw_text`
- `transcript`
- `ocr_text`
- `visual_summary`
- `project`
- `location`
- `domain`
- `subcategory`
- `description`
- `relevance`
- `confidence`
- `analysis_evidence`
- `media_processing_status`
- `duplicate_group_id`
- `review_status`

**Sheet `Crawl_Runs`**

- `crawl_run_id`
- `window`
- `started_at`
- `ended_at`
- `source`
- `status`
- `candidate_count`
- `keep_count`
- `drop_count`
- `review_count`
- `duplicate_count`
- `media_fail_count`
- `llm_fail_count`

**Sheet `Source_Registry`**

- `source_id`
- `source_type`
- `name`
- `url/query`
- `priority`
- `enabled`
- `auth_required`
- `last_success_at`
- `last_error`

**Sheet `Review`**

- `content_id`
- `original_domain`
- `reviewed_domain`
- `original_subcategory`
- `reviewed_subcategory`
- `original_description`
- `reviewed_description`
- `reviewer`
- `reviewed_at`
- `note`

---

## 7. Yêu cầu phi chức năng

| Nhóm | Yêu cầu |
| --- | --- |
| Hiệu năng | Với cấu hình pilot, một scheduled run nên hoàn tất trước run kế tiếp; target ban đầu <= 30 phút sau khi kết thúc crawl window để có Excel review |
| Độ ổn định | Source failure phải isolated; một source hỏng không được làm fail toàn pipeline |
| Khả năng mở rộng | Kiến trúc adapter-based để thêm source mới mà không thay đổi core enrichment/storage |
| Idempotency | Rerun cùng source + time window không tạo duplicate record |
| Bảo mật | API key/session secret chỉ lưu ở secret store/.env an toàn; không log credential |
| Quyền riêng tư và tuân thủ | Chỉ thu thập nội dung public/được cấp quyền; data minimization; không bypass privacy/access control; cần review Legal/Compliance trước production |
| Khả năng quan sát | Log theo `crawl_run_id`, source, step; có metric count và error reason |
| Chất lượng dữ liệu | Schema validation bắt buộc trước khi lưu/export; nullable field phải rõ ràng |
| Đa ngôn ngữ / địa phương hóa | Ưu tiên tiếng Việt; UTF-8; timezone Asia/Bangkok; hỗ trợ text Việt có dấu/không dấu |
| Tương thích | Runtime ưu tiên Python 3.11+; Windows/local POC và Linux/server deployment về sau |
| Tính thay thế | LLM provider và source adapter phải thay thế độc lập qua interface/config |

### 7.1 Kế hoạch theo dõi (Analytics/Operational telemetry)

| Tên sự kiện | Kích hoạt khi | Thuộc tính đi kèm | Phục vụ chỉ số |
| --- | --- | --- | --- |
| `crawl_run_started` | Scheduler bắt đầu run | run_id, window, source_count | Run reliability |
| `source_collection_completed` | Một source kết thúc | source_id, status, candidate_count, duration | Source health/coverage |
| `candidate_discovered` | Tìm thấy candidate mới | source, content_type, query/source_id | Retrieval yield |
| `candidate_dropped` | Negative filter loại | drop_reason, matched_rule | Noise rate |
| `media_processing_completed` | Media resolver xong | status, evidence_types, duration | Media success rate |
| `llm_enrichment_completed` | LLM trả kết quả | domain, confidence, valid_schema, model | LLM quality |
| `duplicate_detected` | Duplicate được phát hiện | duplicate_type, group_id | Duplicate leakage |
| `record_sent_to_review` | Record low-confidence/ambiguous | reason, confidence | Review load |
| `review_override_saved` | Reviewer sửa nhãn | old/new domain/subcategory | Model/rule feedback |
| `excel_export_generated` | Export hoàn tất | run_id, row_count, path/version | Delivery SLA |

---

## 8. Phụ thuộc, giả định và ràng buộc

### 8.1 Phụ thuộc

| Phụ thuộc | Đội / bên chịu trách nhiệm | Hạn cần có | Trạng thái |
| --- | --- | --- | --- |
| Danh sách Facebook groups/pages/community sources ưu tiên | SmartCity Ops / Source Curator | Trước POC live | Chưa chốt |
| Cơ chế truy cập Facebook hợp lệ/session/account phục vụ watchlist | IT/Security + Ops | Trước FB adapter pilot | Cần feasibility review |
| Web/Google Search API/provider | Engineering/Data | POC | Chưa chốt provider |
| YouTube Data API credential | Engineering/Data | POC | Chưa chốt |
| TikTok data access method | Engineering/Data + Legal | POC | Cần feasibility spike |
| LLM API provider/model | Data/AI | POC | Chưa chốt |
| Media tools: FFmpeg/ASR/vision | Engineering/Data | POC | Khả thi, cần benchmark |
| Storage + secret management | IT/Engineering | MVP | TBD |
| Legal/privacy review | Legal/Compliance | Trước pilot production | TBD |

### 8.2 Giả định

| Giả định | Cách kiểm chứng | Người phụ trách |
| --- | --- | --- |
| Các group/community source mục tiêu có đủ signal vận hành để tạo giá trị | Theo dõi 1–2 tuần, đo relevant yield/source | Ops + Data |
| Crawl tập trung giờ cao điểm tăng mật độ `SITE_ACCESS_CONGESTION` | So sánh relevant yield theo window | Data |
| Broad retrieval + negative filtering tốt hơn search issue quá hẹp | A/B query set trên cùng thời gian/source | Data |
| LLM có thể gán domain/description đủ tốt khi nhận structured evidence | Human review >= 200 mẫu | Data/AI |
| Caption + transcript + vài key frames đủ cho phần lớn video | Media ablation test | Data/AI |
| Source watchlist có giá trị hơn chỉ search global | So sánh yield và precision theo acquisition method | Data |

### 8.3 Ràng buộc

- **Thời gian:** ưu tiên POC nhanh để đánh giá data access trước khi xây dashboard/model phức tạp.
- **Nhân lực / ngân sách:** chưa chốt; thiết kế phải chạy được với batch schedule thay vì realtime để giảm cost.
- **Công nghệ:** source adapters có thể hỏng khi website/API thay đổi; phải tách biệt và có fallback.
- **Pháp lý / platform policy:** chỉ sử dụng nguồn public hoặc nguồn được cấp quyền; không bypass access controls.
- **Coverage:** không thể bảo đảm phát hiện mọi post từ trang cá nhân hoặc private group.
- **LLM:** URL video Facebook/TikTok không được coi là input đủ; cần media processing/fallback.

---

## 9. Rủi ro và câu hỏi mở

### 9.1 Rủi ro

| Rủi ro | Khả năng xảy ra | Mức ảnh hưởng | Phương án giảm thiểu |
| --- | --- | --- | --- |
| Facebook/TikTok chặn automation hoặc thay đổi UI/API | Cao | Cao | Adapter isolation, health check, watchlist ưu tiên, fallback search/indexed result, feasibility spike trước production |
| Bỏ sót bài từ trang cá nhân không discoverable | Cao | Cao | Không đặt KPI global recall; tập trung configured watchlist + seed expansion + community sources |
| Search query quá hẹp làm recall thấp | Cao | Cao | Broad retrieval theo project/entity/source; filtering downstream |
| Noise bán hàng/tuyển dụng quá lớn | Cao | TB | Negative intent classifier + rules + human review sample |
| Video không truy cập/resolve được | TB/Cao | TB | Fallback caption/metadata; evidence level + confidence |
| LLM gán sai tag/description | TB | Cao | Schema validation, evidence grounding, confidence, REVIEW, human feedback |
| Duplicate/repost làm phóng đại số case | Cao | TB | URL/post ID/hash + near-duplicate detection |
| Complaint được đăng trễ ngoài peak window | Cao | TB | Overlapping lookback + optional late reconciliation run |
| Credential/session hết hạn | TB | TB | Source-level auth health check, alert, manual re-auth |
| Vi phạm privacy/platform terms | TB | Cao | Legal review, data minimization, no bypass, audit source access |
| Chi phí media/LLM tăng nhanh | TB | TB | Cascade: metadata/caption → ASR → vision; chỉ gọi bước đắt khi cần |
| Website selector thay đổi | Cao | TB | Tests per adapter, monitoring, graceful failure |

### 9.2 Câu hỏi mở (Open questions)

| Câu hỏi | Người chịu trách nhiệm | Hạn chốt | Câu trả lời / quyết định |
| --- | --- | --- | --- |
| Danh sách 20–100 Facebook group/page/account ưu tiên ban đầu là gì? | SmartCity Ops | Trước POC live | Chưa có |
| Khung giờ chiều chính xác là bao nhiêu? 16:30–19:00 chỉ là đề xuất ban đầu | SmartCity Ops | Trước scheduler config | Chưa có |
| Có cần crawl comment ngay trong MVP hay chỉ post/video? | Product/Ops | Trước scope freeze | Chưa có |
| TikTok sẽ dùng API chính thức, search/browser, provider bên thứ ba hay watchlist account? | Engineering/Legal | Feasibility spike | Chưa có |
| Google Search sẽ dùng provider/API nào? | Engineering | POC | Chưa có |
| Có cần run reconciliation buổi tối hay chỉ peak windows? | Ops | Sau 1 tuần POC | Chưa có |
| Ngưỡng confidence nào chuyển `REVIEW`? | Data/AI | Sau baseline | Chưa có |
| Ai là reviewer nghiệp vụ và SLA review là bao lâu? | Ops | Trước pilot | Chưa có |
| Thời gian lưu raw media/raw text là bao lâu? | Legal/IT/Product | Trước production | Chưa có |
| Có được lưu author/display name không, hay chỉ pseudonym/source URL? | Legal/Compliance | Trước pilot | Chưa có |
| Mức coverage nào được coi là đủ giá trị nếu không thể đo global recall? | Product/Ops | Sau POC | Chưa có |
| Excel format cuối cùng có cần thêm owner/status/action column cho vận hành không? | Ops | UAT | Chưa có |

---

## 10. Kế hoạch triển khai

### 10.1 Các mốc thời gian đề xuất

> Đây là timeline đề xuất để chạy feasibility-first; có thể điều chỉnh theo quyền truy cập nguồn và nhân lực.

| Mốc | Nội dung | Ngày dự kiến | Người phụ trách |
| --- | --- | --- | --- |
| Kickoff / Scope freeze | Chốt 2 domain MVP, source categories, success metrics | 08–09/10/2026 | Product/Ops/Data |
| Data-source feasibility spike | Test Facebook group, Web Search, TikTok, YouTube; lập Source Feasibility Matrix | 10–14/10/2026 | Engineering/Data |
| POC ingestion | Source registry, scheduler, adapters đầu tiên, raw storage, dedup | 15–20/10/2026 | Engineering/Data |
| Media + LLM enrichment | Caption/ASR/frames, schema, taxonomy, confidence | 21–26/10/2026 | Data/AI |
| Excel + review loop | Export, review fields, run metrics | 27–29/10/2026 | Data/Product |
| QA / UAT | Chạy trên real window, manual review >= 200 mẫu | 30/10–02/11/2026 | QA/Ops/Data |
| Pilot | Chạy theo lịch thật với source watchlist ban đầu | Từ 03/11/2026 | Ops/Engineering |

### 10.2 Phân pha

**MVP / POC:**

- Source Registry.
- Google/Web Search + YouTube + ít nhất 1 cơ chế Facebook watchlist khả thi.
- TikTok ở mức feasibility hoặc collector nếu access đủ ổn định.
- Peak-window scheduler.
- Incremental lookback + dedup.
- Negative filtering.
- Media fallback.
- LLM relevance/tag/description.
- Taxonomy 4 top-level classes.
- SQLite/PostgreSQL + Excel.
- Run logging và QA sample.

**v1:**

- Human review UI nhẹ.
- Late reconciliation run.
- Comments ingestion cho source ưu tiên.
- Better near-duplicate clustering.
- Source discovery/seed expansion.
- Alerting cho high-confidence `SITE_ACCESS_CONGESTION`.

**v2 trở đi:**

- Issue clustering đa nguồn/đa ngày.
- First seen / last seen / trend.
- Lifecycle tracking: NEW → MONITORING → IN_PROGRESS → RESOLVED → REOPENED.
- Dashboard operational intelligence.
- GIS/location mapping.
- Auto-generated daily report.
- Tích hợp ticket/incident management nếu business yêu cầu.

### 10.3 Chiến lược ra mắt

- **Hình thức:** beta kín/internal pilot với tập source giới hạn.
- **Tiêu chí mở rộng:**
  - precision KEEP đạt target;
  - source run ổn định >= 95%;
  - duplicate leakage <= 5%;
  - không có privacy/access-control incident;
  - operations xác nhận signal có giá trị thực tế.
- **Kế hoạch rollback:** disable từng source/adapter hoặc toàn scheduler; giữ nguyên dữ liệu đã thu và lineage để audit; không xóa raw/evidence tự động khi rollback nếu chưa qua retention policy.

### 10.4 Truyền thông và vận hành

- Tạo tài liệu `Source Feasibility Matrix` và `Runbook` cho từng source.
- Có danh sách owner của source adapter và người phụ trách re-auth/session.
- Reviewer nghiệp vụ được hướng dẫn phân biệt `KEEP/DROP/REVIEW` và sửa taxonomy.
- Theo dõi hằng ngày trong pilot: failed sources, relevant yield, media failure, LLM invalid output, duplicate rate.
- Sau 1–2 tuần pilot, review lại crawl windows, source priority và taxonomy trước khi mở rộng.

---

## 11. Phụ lục

### 11.1 Kiến trúc logic đề xuất

```text
Configured Sources / Queries
        │
        ├── Facebook community watchlist
        ├── Google/Web keyword & hashtag search
        ├── TikTok keyword/hashtag/account
        └── YouTube keyword search
        │
        ▼
Candidate Discovery
        │
        ▼
Raw Metadata + Lineage
        │
        ▼
Exact Dedup
        │
        ▼
Negative / Noise Filtering
        │
        ▼
Media Resolver
  ┌─────┼──────────────┐
  │     │              │
Text  Audio/ASR     Frames/OCR
  │     │              │
  └─────┴──────┬───────┘
               ▼
        Unified Evidence
               │
               ▼
          LLM Enrichment
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
Relevance    Tag     Description
               │
               ▼
       Schema Validation
               │
               ▼
    Near-Dedup / Review Gate
               │
               ▼
         Storage + Excel
```

### 11.2 Crawl schedule đề xuất

**Morning peak – pilot**

- 05:30
- 06:30
- 07:30
- 08:15 close-window crawl

**Afternoon peak – provisional, cần Ops chốt**

- 16:30
- 17:30
- 18:30
- 19:15 close-window crawl

**P1 – reconciliation**

- 22:00, lookback 12–18 giờ để bắt complaint đăng trễ và repost.

Các run sử dụng overlapping lookback; hệ thống chấp nhận crawl trùng và dedup downstream để giảm nguy cơ miss dữ liệu.

### 11.3 Query strategy

Query không chỉ dựa vào từ “VinCons”. Hệ thống cần kết hợp:

- Company/entity: `VinCons`, aliases.
- Project aliases: tên dự án, viết tắt, vị trí.
- Access context: `cổng`, `ra vào`, `checkin`, `check-out`, `chấm công`, `barrier`, `QR`, `face recognition`, `xe tải`, `xe ben`.
- Congestion/problem terms: `ùn`, `tắc`, `kẹt`, `xếp hàng`, `nối đuôi`, `chờ`, `đông`, `chậm`, `không vào được`, `không ra được`.
- Complaint terms: `phản ánh`, `khiếu nại`, `bức xúc`, `không hài lòng`, `chờ lâu`, `không phản hồi`, `không hỗ trợ`, `chưa xử lý`.
- Negative intents: bán nhà/căn hộ, booking, môi giới, cho thuê, tuyển dụng, việc làm, PR/marketing.

Nguyên tắc: **search rộng trong ecosystem/source phù hợp, sau đó filter**, thay vì cố search chính xác từng issue từ đầu.

### 11.4 LLM output schema đề xuất

```json
{
  "schema_version": "social-signal-v1",
  "relevance": "KEEP|DROP|REVIEW",
  "domain": "SITE_ACCESS_CONGESTION|CUSTOMER_COMPLAINT|OTHER_RELEVANT|IRRELEVANT",
  "subcategory": "string|null",
  "project": "string|null",
  "location": "string|null",
  "description": "string",
  "confidence": 0.0,
  "evidence_used": ["caption", "transcript", "ocr", "visual_summary", "metadata"],
  "drop_reason": "string|null"
}
```

Validation rules:

- JSON/schema phải hợp lệ.
- `confidence` trong [0,1].
- Không được invent project/location nếu evidence không có.
- `DROP` phải có `drop_reason`.
- `SITE_ACCESS_CONGESTION`/`CUSTOMER_COMPLAINT` phải có `description` mô tả case, không chỉ lặp lại keyword.
- Nếu evidence mâu thuẫn hoặc quá ít → `REVIEW`.

### 11.5 Nền tảng kỹ thuật tham khảo

Không phải yêu cầu cứng của PRD, nhưng hướng triển khai hiện tại có thể tận dụng:

- Base collector/pipeline pattern từ các repo social-media scraping đa nguồn.
- Crawlee/Playwright cho browser-based source adapter.
- yt-dlp + FFmpeg + ASR cho media processing khi phù hợp và được phép.
- Prefect hoặc scheduler tương đương cho run windows/retry/observability.
- SQLite cho POC, PostgreSQL khi cần concurrent/multi-user.
- LLM provider qua adapter để không lock vào một model.

### 11.6 Thuật ngữ

- **Candidate:** nội dung vừa được discovery, chưa qua relevance filtering.
- **Signal:** content đã được coi là có khả năng liên quan vận hành.
- **Evidence:** dữ liệu dùng để phân loại: text, caption, transcript, OCR, visual summary, metadata.
- **Watchlist:** danh sách source/account/group/query được ưu tiên kiểm tra định kỳ.
- **Source Registry:** cấu hình và trạng thái các nguồn dữ liệu.
- **Overlapping lookback:** mỗi run tìm lùi chồng lên khoảng run trước để giảm miss; dedup xử lý phần trùng.
- **Reconciliation run:** run bổ sung sau peak window để bắt nội dung đăng trễ.
- **Claim:** phản ánh/tuyên bố trên social; không mặc định là fact đã xác minh.

---

## Checklist tự kiểm tra trước khi gửi review

- [ ] Phần vấn đề có bằng chứng, không chỉ là ý kiến → hiện mới có discovery evidence; cần baseline POC để hoàn thiện định lượng.
- [ ] Mỗi mục tiêu có chỉ số đo được, có baseline và mốc thời gian → target đã đề xuất; baseline cần đo.
- [x] Đã ghi rõ non-goals.
- [x] Mỗi yêu cầu có mã số, mức ưu tiên và tiêu chí chấp nhận kiểm thử được.
- [x] Đã mô tả trạng thái lỗi, trạng thái rỗng và trường hợp biên.
- [x] Không dùng từ mơ hồ mà không có tiêu chí đo cho các yêu cầu chính.
- [x] Đã liệt kê phụ thuộc, rủi ro và câu hỏi mở.
- [x] Có kế hoạch theo dõi sự kiện để đo chỉ số thành công.
- [x] Có kế hoạch ra mắt và rollback.
- [x] Đã cập nhật lịch sử thay đổi.
