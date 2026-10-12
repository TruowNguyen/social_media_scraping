# Kế hoạch mở rộng lọc phản ánh khách hàng theo dự án

Kế hoạch ngày 09/10/2026, đồng bộ 11/10/2026: **IMPLEMENTED_SUBSET / FULL_ACCEPTANCE_PENDING**. Registry có VinCons (tổ chức) và VinWonders Vũ Yên, 14 groups enabled; selection/query/filter/matching và taxonomy/classifier/workspace có increment. [Runbook dự án](../../docs/operations/project-filter.md), [trạng thái hiện hành](../../docs/current-state.md). Full PF contract bên dưới là target; project override/history chuyên biệt, quality pilot và mentor acceptance còn pending.

Mục tiêu: theo dõi nhiều dự án, kể cả ngoài VinCons, xác định phản ánh thuộc dự án nào và khách hàng đang gặp vấn đề gì. Mỗi kết quả có link bài, group nguồn, dự án nếu xác định được, tóm tắt, vấn đề, bằng chứng và chỗ đánh giá. Không bắt buộc bài chứa “VinCons”.

## 1 Phạm vi và hiện trạng

| Nội dung | Hiện tại | Hướng mở rộng |
| --- | --- | --- |
| Dự án | Hai scopes bật trong Project Registry | Mở rộng danh mục/alias có curator và evidence |
| Facebook | 14 groups configured/enabled, raw v2 POST/COMMENT/REPLY | Bổ sung group khách hàng/cư dân được xác minh; đối chứng coverage |
| Google | Search nhận keyword/hashtag người dùng nhập | Sinh truy vấn theo dự án; nguồn mới tiếp tục vào hàng chờ duyệt |
| Phân loại | Per-node intents, project taxonomy, Gemini worker và OCR POST | Full complaint/project attribution quality gate |
| Giao diện | Workspace bốn tab, project/issue filters, reviews và Excel | Override dự án/history chuyên biệt, UAT nghiệp vụ |

Pilot đề xuất: 2–3 dự án, ưu tiên có group công khai của cư dân/khách hàng. Số lượng là đề xuất, chưa phải danh sách được duyệt. Giữ lịch hiện có 05:00–08:30 và 17:00–18:30, chu kỳ 45 phút; thêm nguồn phải kiểm tra tổng thời gian chạy để không tạo job chồng.

7 group công nhân hiện có vẫn là nguồn riêng; không coi thành viên hoặc mọi bài trong đó là phản ánh khách hàng. V1 tận dụng Facebook public-group và Google hiện có. Facebook Page/profile và TikTok live không được coi là đã có coverage; triển khai adapter/kiểm chứng riêng nếu cần mở rộng sang các nguồn này.

## 2 Danh mục dự án và nguồn theo dõi

**PF-001 — Project Registry, P0.** Mỗi dự án có ID ổn định, độc lập với tên doanh nghiệp. Đổi tên/bổ sung bí danh không làm đổi identity của bài.

| Thông tin | Cách dùng |
| --- | --- |
| `project_id`, `name`, `enabled` | Định danh, tên hiển thị và bật/tắt phạm vi theo dõi |
| `aliases` | Tên đầy đủ, tên cũ, viết tắt; ghi bí danh nào cần thêm địa phương để phân biệt |
| `location` | Tỉnh/thành, quận/huyện; block/tòa/phân khu nếu đã xác minh |
| `organization_refs` | Chủ đầu tư/đơn vị vận hành/nhà thầu nếu có; chỉ là thông tin phụ, không phải điều kiện bài bắt buộc nhắc đến |
| `query_terms`, `hashtags` | Cụm tìm kiếm được curator khai báo; không tự cho rằng hashtag là bằng chứng liên quan |
| `source_ids` | Group nguồn đã duyệt; một group có thể liên quan nhiều dự án |
| `feedback_topics` | Nhóm phản ánh cần theo dõi và mức ưu tiên |
| `verification`, `dictionary_version` | Người xác nhận, ngày xác nhận và phiên bản cấu hình để truy vết |

Mẫu dưới đây chỉ minh họa cấu trúc dự kiến; **không phải config có thể nạp bằng loader hiện tại**:

```yaml
schema_version: project-registry-v1
projects:
  - project_id: project_example_a
    name: "Dự án A"
    enabled: false
    aliases:
      - value: "Dự án A"
        requires_location: false
      - value: "DAA"
        requires_location: true
    location:
      province: "Địa phương cần xác nhận"
      district: null
    organization_refs: []
    query_terms: ["Dự án A", "cư dân Dự án A"]
    hashtags: []
    source_ids: []
    feedback_topics: [HANDOVER_QUALITY, WARRANTY_REPAIR, SERVICE_DELAY]
```

**PF-002 — Source mapping, P0.** Gắn nguồn với dự án như bối cảnh hỗ trợ, không tự biến thành kết luận. Group cư dân dự án A vẫn có thể đăng bài về dự án B, quảng cáo hoặc nội dung không liên quan. Nguồn mới giữ draft/disabled đến khi xác minh truy cập và bật riêng. Ưu tiên group cư dân, người mua nhà, khách hàng đang chờ bàn giao; nguồn công nhân chỉ bổ sung góc nhìn khi phù hợp.

## 3 Ba bước lọc độc lập

### Bước 1 Loại nội dung giao dịch và tuyển dụng

**PF-003 — Exclusion chung, P0.** Áp dụng trước deep fetch khi caption đã thể hiện intent rõ; kiểm tra lại khi lấy được nội dung đầy đủ. Giữ rule loại tuyển dụng/xin việc, rao bán, cho thuê/tìm thuê, trao đổi hàng hóa và chào mời vay nợ. DROP không tải media, gọi LLM hoặc lưu raw content; chỉ giữ rejection metadata.

Không loại phản ánh chỉ vì có từ “mua”, “thuê”, “vay” hoặc “tuyển dụng”. Ví dụ “Tôi mua căn hộ, bàn giao bị thấm nhưng bảo hành không phản hồi” phải được giữ. “Cam kết không chậm lương” trong quảng cáo tuyển dụng không phải phản ánh nợ lương. Nội dung giao dịch và phản ánh thật xen nhau chuyển REVIEW nếu chưa rõ intent chính.

### Bước 2 Nhận diện bài thuộc dự án nào

**PF-004 — Project matching, P0.** Đối chiếu caption/nội dung đã đọc với tên/bí danh dự án và địa phương. So khớp Unicode, không phân biệt hoa thường; alias bỏ dấu phải kiểm tra xung đột. Không dùng substring ngắn để tự gán dự án, ví dụ “Vin” không đủ.

| Trường hợp | Kết quả |
| --- | --- |
| Tên dự án đủ đặc trưng xuất hiện trong nội dung bài | MATCHED, lưu đoạn bằng chứng |
| Bí danh có nhiều dự án dùng chung | Cần địa phương/tòa hoặc bằng chứng phân biệt; thiếu thì AMBIGUOUS |
| Chỉ group gắn dự án A, bài ghi “thang máy lại hỏng” | CONTEXT_ONLY; đề xuất A để review, chưa tự xác nhận |
| Chỉ query Google có tên A, snippet không chứng minh | UNRESOLVED; query là lineage, không phải bằng chứng |
| Bài nói cả A và B | Lưu nhiều quan hệ dự án, phân biệt đối tượng phản ánh và dự án chỉ được nhắc đến nếu có bằng chứng |
| Caption rỗng, chỉ thấy ảnh/video | UNRESOLVED/MISSING_EVIDENCE, chưa kết luận không liên quan |

Không có project match không đồng nghĩa DROP. Bài còn thiếu bằng chứng vào hàng cần đánh giá; nội dung rõ thuộc dự án ngoài danh sách được đánh dấu ngoài phạm vi đang chọn, không tự tạo/bật dự án mới.

### Bước 3 Nhận diện phản ánh khách hàng

**PF-005 — Customer feedback, P0.** Đánh giá nội dung có mô tả vấn đề khách hàng/cư dân gặp phải hay chỉ là thông tin/quảng cáo. Không yêu cầu người đăng phải dùng từ “phản ánh”; ví dụ “gửi bảo hành 3 lần chưa ai đến” là tín hiệu cần giữ. Không suy ra người đăng là khách hàng chỉ từ việc họ ở trong group cư dân.

| Chủ đề đề xuất | Ví dụ cần giữ |
| --- | --- |
| Chất lượng và bàn giao | Thấm, nứt, sai hạng mục bàn giao, chậm bàn giao |
| Bảo hành và sửa chữa | Báo lỗi nhiều lần chưa sửa, sửa không đạt |
| Tiến độ xử lý và phản hồi | Chậm xử lý, không trả lời, yêu cầu chưa giải quyết |
| Thái độ và quy trình phục vụ | Nhân viên ứng xử không phù hợp, thủ tục gây khó khăn |
| Phí, chính sách và cam kết | Phí không rõ, tranh chấp dịch vụ, cam kết với khách hàng chưa thực hiện |
| Tiện ích và vận hành | Thang máy, điện nước, vệ sinh, tiếng ồn, an ninh |
| Ra vào và giao thông của khách hàng/cư dân | Thẻ ra vào lỗi, xếp hàng, kẹt xe gây ảnh hưởng |

Các chủ đề là phạm vi đề xuất phục vụ phản ánh khách hàng. Giữ domain PRD `CUSTOMER_COMPLAINT`, dùng subcategory hiện có khi phù hợp; chủ đề mới lưu bằng `issue_tags` dự kiến. Không tự thêm domain/top-level taxonomy trong bước này. Nội dung ra vào/giao thông đủ evidence có thể thuộc `SITE_ACCESS_CONGESTION`; bài nhiều vấn đề vẫn có một domain chính và nhiều issue tags.

**PF-006 — Kết quả xử lý, P0.** `PASS` của prefilter chỉ cho phép xử lý tiếp. Phân loại cuối dùng `KEEP|REVIEW|DROP` riêng: KEEP khi có phản ánh đủ evidence trong phạm vi; REVIEW khi project/intent/evidence mơ hồ; DROP khỏi danh sách tín hiệu khi rõ không liên quan hoặc thuộc intent bị loại. Chưa có bằng chứng không được tự thành KEEP. Một phản ánh được giữ là lời người đăng, chưa phải sự việc đã xác minh.

## 4 Thu thập và dữ liệu đầu ra

**PF-007 — Retrieval theo dự án, P0.** Crawl các group đã duyệt trong window đang chọn; không bắt buộc tên công ty hoặc tên dự án xuất hiện trong mọi caption. Google sinh cả truy vấn rộng theo tên dự án và truy vấn phản ánh như `"Dự án A" "bảo hành"`, `"Dự án A" "không phản hồi"`. Cụm vấn đề hỗ trợ discovery, không là điều kiện duy nhất để thu thập. Link nguồn mới vẫn đi qua Discovery Queue.

Quét một group chung một lần cho cùng run/window, sau đó đối chiếu nhiều dự án. Giữ quota theo nguồn/run; phân phối hạn mức Google cho các dự án, không nhân quota khi thêm dự án. Lưu observed coverage; hết thời gian giữ phần kết quả đã có, không hứa quét đủ mọi bài hay mọi khách hàng.

**PF-008 — Identity, lineage và migration, P0.** Giữ một bản ghi cho cùng platform/native item ID dù qua nhiều dự án/query; các quan hệ dự án và observations lưu riêng. Không gộp các bài khác nhau vì cùng dự án hoặc thiếu caption. Tách acquisition candidate khỏi kết quả phân tích theo phiên bản; thêm dictionary/rule version, thời điểm phân tích, evidence fields và provenance. Dữ liệu cũ chưa phân tích hiển thị “Chưa xác định”, không mặc định VinCons. Reprocess offline trên nội dung đã lưu; bài thiếu evidence cần fetch riêng theo điều kiện truy cập.

Output dự kiến:

| Nhóm | Nội dung |
| --- | --- |
| Bài gốc | Link URL, platform/native ID, group/nguồn, ngày đăng/ngày thu thập |
| Dự án | Danh sách quan hệ `project_id`, vai trò IMPACTED/MENTIONED/UNKNOWN, trạng thái match, alias matched, đoạn bằng chứng |
| Phản ánh | Tóm tắt có căn cứ, domain, nhóm vấn đề, relevance, lý do cần review |
| Đánh giá | Đánh giá người dùng, ghi chú, dự án/chủ đề được sửa và lịch sử sửa |
| Kiểm chứng | Evidence có/thiếu, rule/dictionary/analysis version, lineage nguồn/query/run |

Không đặt numeric confidence tùy ý cho rule deterministic; phân biệt mức bằng chứng với xác suất. Nếu dùng model ở phase sau, confidence phải được đánh giá trên bộ nhãn đối chứng, không auto-accept project/location thiếu evidence.

**PF-009 — UI và Excel, P1.** Thêm lựa chọn “Tất cả dự án” hoặc một/nhiều dự án vào search/crawl, lưu lựa chọn theo lịch. Kho có cột Dự án, Nhóm vấn đề, Trạng thái xác định; giữ Group, Đánh giá, Ghi chú. Bài nhiều dự án vẫn một dòng; Excel thêm sheet quan hệ bài–dự án nếu cần thống kê. Có bộ lọc “Chưa xác định dự án/thiếu nội dung”; người review sửa project/topic có audit. Chọn dự án trong UI không được biến bối cảnh nguồn thành project fact.

## 5 Trình tự triển khai và kết quả bàn giao

| Task | Ưu tiên / trạng thái | Công việc | Kết quả để review |
| --- | --- | --- | --- |
| PF-T01 | P0 / PLANNED | Chốt 2–3 dự án, aliases/địa phương và phạm vi khách hàng | Danh mục xác nhận; chưa có tên thì giữ pending |
| PF-T02 | P0 / PLANNED | Curate group khách hàng/cư dân, xác minh quyền truy cập | Source mapping, trạng thái public/access và enable riêng |
| PF-T03 | P0 / PLANNED | Chốt contract/config và migration tương thích dữ liệu hiện có | Project registry, project–source mapping, schema analysis version |
| PF-T04 | P0 / PLANNED | Matcher và rule phản ánh khách hàng, regression exclusion | Bằng chứng project match, protected complaints; offline tests |
| PF-T05 | P0 / PLANNED | Query/run/scheduler theo dự án, nguồn chung không crawl lặp | Run có selection/window/quota/config snapshot |
| PF-T06 | P1 / PLANNED | Table, review override, bộ lọc dự án và Excel | Review sửa được, dữ liệu không mất qua rerun, export đối chiếu |
| PF-T07 | P0 / PLANNED | Reprocess kho hiện có và pilot có đối chứng | Báo cáo KEEP/REVIEW/DROP, lỗi gán dự án, bài thiếu evidence |

Thứ tự: chốt dự án/nguồn → contract/migration → matcher và fixtures → routing/scheduler → UI/review/export → pilot. Các giai đoạn chỉ nâng OFFLINE_VERIFIED/LIVE_VERIFIED/ACP khi có evidence tương ứng. Không triển khai model/OCR/ASR trước khi xác nhận nhu cầu; caption-based baseline làm trước, phần chỉ có ảnh/video vẫn REVIEW.

## 6 Acceptance và đo chất lượng

| Case | Input | Expected / requirement |
| --- | --- | --- |
| PF-AC01 | Thêm dự án B không có chữ VinCons | Run kế tiếp dùng alias/source B; không sửa collector — PF-001/007 |
| PF-AC02 | “Căn hộ Dự án A bị thấm, bảo hành chưa phản hồi” | KEEP, match A, tags chất lượng/bảo hành; evidence đoạn bài — PF-004/005 |
| PF-AC03 | “Tôi thuê căn hộ A, báo mất nước 3 ngày chưa xử lý” | Giữ phản ánh; không DROP vì “thuê” — PF-003/005 |
| PF-AC04 | “Cho thuê căn hộ A, inbox nhận giá” | DROP; không deep fetch/media/LLM/raw persistence — PF-003 |
| PF-AC05 | “Tuyển công nhân A, cam kết không chậm lương” | DROP; lời cam kết không bị coi là complaint — PF-003 |
| PF-AC06 | “Bị lừa khi mua căn hộ A, chủ đầu tư không trả lời” | Giữ để review/KEEP theo evidence, không loại chỉ vì “mua/lừa đảo” — PF-003/005 |
| PF-AC07 | Alias “Central” trùng hai dự án, thiếu địa phương | AMBIGUOUS, không tự gán — PF-004 |
| PF-AC08 | Group A nhưng bài phản ánh dự án B | Gán B nếu đủ evidence; không ép A — PF-002/004 |
| PF-AC09 | Caption rỗng hoặc chỉ project xuất hiện trong query | REVIEW/UNRESOLVED, project chưa xác nhận — PF-004/006 |
| PF-AC10 | Cùng bài qua query A/B và nhiều run | Một item, nhiều observations/relations; không đếm hai bài — PF-008 |
| PF-AC11 | Thêm alias/xóa alias và chạy lại analysis | Lưu version/history, tôn trọng override người review — PF-001/008/009 |
| PF-AC12 | Nguồn disabled, lỗi session, hết quota | Không crawl disabled; nguồn lỗi có outcome; không mất kết quả nguồn khác — PF-002/007 |
| PF-AC13 | Export nhiều dự án và unknown | Đủ dòng duy nhất, quan hệ đúng, Đánh giá/Ghi chú khớp UI — PF-009 |

Pilot đề xuất 7 ngày trên nhóm nguồn accessible, cùng window/quota để so với baseline. Curator gán nhãn các bài quan sát được gồm cả KEEP, DROP, REVIEW; ghi rõ sample size. Đo precision gán dự án và phản ánh, recall trong tập đối chứng đã đọc được, tỷ lệ tuyển dụng lọt, tỷ lệ thiếu caption và tỷ lệ bài cần review. Không tính bài rỗng là true negative; không tuyên bố recall toàn Facebook. Kiểm tra số phản ánh duy nhất/ngày theo ngày đăng khi có timestamp, tách ngày thu thập và số bài group hiển thị.

Gate bắt buộc: không auto-accept project/location thiếu evidence; không làm mất protected complaint trong fixtures; không phát sinh duplicate do project routing; không lưu raw nội dung DROP. Ngưỡng precision/recall pilot và mục tiêu phản ánh/ngày **cần mentor chốt**, không dùng mặc định 5/ngày trước đây như cam kết cho mọi dự án.

## 7 Traceability và thông tin cần bổ sung

| Requirements | PRD liên quan |
| --- | --- |
| PF-001/002/004 | FR-01/02, source/project dictionary và evidence-grounded project/location |
| PF-003/005/006 | FR-06/09/10/11, negative filtering và complaint/relevance |
| PF-007/008 | FR-03/04/05/12, window, scheduler, dedup và lineage |
| PF-009 | FR-13/14, export và human review |

Cần người dùng/mentor cung cấp: tên dự án pilot, địa phương, bí danh, group khách hàng/cư dân nếu có; xác nhận nhóm vấn đề và ưu tiên; reviewer nhãn đối chứng và ngưỡng chất lượng mong muốn. Ngày hoàn thành phụ thuộc nguồn và review, chưa tự gán deadline.

Liên quan: [Source Registry](../contracts/source-registry.md), [Exclusion rules](../contracts/exclusion-rules.md), [Source Adapter](../contracts/source-adapter.md), [Discovery Queue](../contracts/discovery-queue.md), [TODO](../../TODO.MD).
