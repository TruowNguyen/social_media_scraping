# Taxonomy v1 — vấn đề theo dõi theo dự án

Version **1.0.0-draft.1**, ngày 09/10/2026. **DRAFT, chưa được mentor duyệt, chưa bật runtime.** Đây là bàn giao đầu tiên của P0, không hoàn tất toàn P0. [Contract](../../contracts/project-issue-taxonomy.md), [phase/acceptance](../../../docs/phased-delivery-v2.md), [TODO](../../../TODO.MD).

Snapshot specs này vẫn DRAFT/disabled. Runtime **1.0.0 APPROVED/enabled** được tạo riêng tại [config/taxonomy/v1](../../../config/taxonomy/v1/common.yaml) sau khi người dùng chấp nhận baseline để triển khai; [worker](../../../docs/operations/classification-worker.md) đọc config đó. [26 development cases](../../../tests/fixtures/taxonomy_v1/README.md) và taxonomy CLI mặc định vẫn dùng draft review. Approval provenance của runtime không thay mentor/held-out quality acceptance.

File định nghĩa dùng chung: [common.yaml](common.yaml). Hai profile: [VinCons](vincons.yaml), [VinWonders Vũ Yên](vinwonders_vu_yen.yaml). Mỗi issue có định nghĩa, ví dụ nhận/loại, bằng chứng tối thiểu và mapping PRD; priority đặt theo profile. Files nằm trong specs snapshot, không được loader runtime đọc như config active.

## 1. Mục tiêu và đối tượng

Phát hiện **reported signals** về trở ngại ra vào, ùn tắc và phản ánh dịch vụ liên quan dự án. Không coi phát biểu mạng xã hội là sự cố đã được xác minh. Không yêu cầu người viết phải tự nhận là khách hàng mới đọc phản ánh; nhưng không tự gắn công nhân thành khách hàng. Role nếu không rõ giữ UNKNOWN.

VinCons là phạm vi doanh nghiệp/nhiều công trường; `project_id: vincons` không có nghĩa mọi bài thuộc cùng công trường. [projects.yaml](../../../config/projects.yaml) hiện có entry VinCons `ORGANIZATION_PORTFOLIO` và VinWonders Vũ Yên. Cần evidence cho địa điểm cụ thể, thiếu giữ null; group hoặc mention Royal Island/Vũ Yên riêng lẻ không xác nhận vụ việc tại công viên. Metadata `PROPOSED_NOT_ACTIVE` trong draft profile là snapshot review, không thay Registry hiện hành.

## 2. Phân cấp ưu tiên

- **P0:** kiểm soát ra vào, cổng và luồng người/xe.
- **P1:** phản ánh phục vụ, hỗ trợ và dịch vụ số.
- **P2:** tín hiệu liên quan ngoài các nhóm trên cần xem xét phạm vi.

Đây là mức ưu tiên theo dõi, không là severity đã xác minh. An toàn có thể cần chú ý ngay nhưng chưa được tự tạo severity hoặc workflow cảnh báo trong v1.

## 3. VinCons: vấn đề cần quan tâm

| Issue | Ưu tiên | Cần chú ý khi đọc phản ánh |
| --- | --- | --- |
| ACCESS_DENIED | P0 | Không được vào/ra; chưa kết luận bảo vệ sai quy định |
| ACCESS_SYSTEM_FAILURE | P0 | Lỗi thẻ, nhận diện, QR, barrier; không suy nguyên nhân kỹ thuật |
| CHECKIN_BOTTLENECK | P0 | Kiểm giấy tờ/đăng ký/xử lý ngoại lệ gây chậm |
| ENTRY_QUEUE / EXIT_QUEUE | P0 | Tách chiều vào/ra bằng bằng chứng, không chỉ dựa giờ vào ca/tan ca |
| GATE_CONGESTION_UNSPECIFIED | P0 | Có claim kẹt cổng nhưng chưa rõ chiều/người/xe, giữ thông tin thay vì ép nhãn |
| VEHICLE_CONGESTION | P0 | Xe ùn/chắn cổng/lối tiếp cận; loại xe và vị trí chỉ trích khi nêu |
| WORKER_CONGESTION | P0 | Claim công nhân ùn ứ, không suy từ tên group |
| EXTERNAL_TRAFFIC_IMPACT | P0 | Đường ngoài công trường ảnh hưởng đến/ra dự án |
| SERVICE_DELAY / NO_RESPONSE | P1 | Chậm xử lý hoặc đã liên hệ nhưng chưa có trả lời; phân biệt hai trạng thái |
| APP_SYSTEM_ISSUE | P1 | App/portal phục vụ đăng ký/hỗ trợ lỗi, khác máy tại cổng |
| STAFF_ATTITUDE | P1 | Claim hành vi nhân sự kiểm soát/hỗ trợ, không suy từ từ chối vào |
| UNRESOLVED_ISSUE | P1 | Đã báo nhưng vấn đề còn; gán cùng issue gốc khi có evidence |
| OTHER_CUSTOMER_COMPLAINT | P1 | Complaint dịch vụ rõ chưa thuộc nhóm cụ thể; role/địa điểm chưa biết không bịa |
| OTHER_RELEVANT | P2 | Tín hiệu khác liên quan mục tiêu; scope mới cần REVIEW |

Nợ lương/điều kiện lao động/chỗ ở/an toàn là **phạm vi cần mentor xác nhận**, không tự gọi CUSTOMER_COMPLAINT, cũng không loại vì chứa từ nợ/tuyển dụng. Tin đề nghị vay/quảng cáo thuê trọ thuần túy có thể DROP ở view phản ánh; complaint thật/mixed phải xét riêng.

## 4. VinWonders Vũ Yên: vấn đề cần quan tâm

| Issue | Ưu tiên | Cần chú ý khi đọc phản ánh |
| --- | --- | --- |
| ACCESS_DENIED | P0 | Vé/QR bị từ chối, không vào/ra được |
| ACCESS_SYSTEM_FAILURE | P0 | Máy quét/QR tại cổng lỗi; ghi claim, không xác nhận vé giả bằng suy đoán |
| CHECKIN_BOTTLENECK | P0 | Khâu soát vé/kiểm tra gây chậm |
| ENTRY_QUEUE / EXIT_QUEUE | P0 | Chờ qua cổng vào/ra, khác chờ trò chơi |
| GATE_CONGESTION_UNSPECIFIED | P0 | Kẹt cổng nhưng chưa rõ hướng/nguyên nhân |
| VEHICLE_CONGESTION / EXTERNAL_TRAFFIC_IMPACT | P0 | Bãi xe/cổng/đường tiếp cận; có liên hệ công viên |
| SERVICE_DELAY | P1 | Chậm quầy hỗ trợ/đổi vé/phục vụ; hàng chờ trò chơi có complaint cũng xét nhóm này |
| NO_RESPONSE | P1 | Đã gọi/nhắn hỗ trợ hoặc người bán nhưng không được phản hồi |
| APP_SYSTEM_ISSUE | P1 | Mua vé/thanh toán/nhận vé trên app lỗi |
| STAFF_ATTITUDE | P1 | Claim hành vi phục vụ hoặc nhân viên kiểm soát |
| UNRESOLVED_ISSUE | P1 | Đã khiếu nại, chưa xử lý; có thể đi cùng refund/app issue |
| REFUND_DISPUTE | P1 | Chậm/không/thiếu hoàn tiền; phân biệt đại lý với công viên |
| OTHER_CUSTOMER_COMPLAINT | P1 | Vệ sinh, tiện ích, giá thu sai hoặc trải nghiệm dịch vụ chưa có nhãn chi tiết |
| OTHER_RELEVANT | P2 | Tín hiệu khác cần review, gồm scope an toàn chưa duyệt |

Không bật WORKER_CONGESTION trong profile v1 của công viên; nếu có claim phù hợp scope khác thì REVIEW/shared-profile, không mất raw. Không bật REFUND_DISPUTE ở VinCons v1 nhưng giữ khả năng review complaint hoàn tiền liên quan, không DROP vì issue chưa bật.

## 5. Quy tắc phân loại và các ranh giới dễ nhầm

| Tình huống | Quy tắc v1 |
| --- | --- |
| “Cổng đông vui” | Không có claim cản trở, không tự gán congestion |
| “Kẹt cổng quá” | GATE_CONGESTION_UNSPECIFIED nếu evidence/source context đủ; không đoán chiều vào |
| “QR không nhận, chờ vào 40 phút” | ACCESS_SYSTEM_FAILURE + ENTRY_QUEUE; CHECKIN_BOTTLENECK chỉ thêm nếu có evidence khâu kiểm gây chậm |
| “Đông người” không nói cổng/đường hoặc tác động | Không ép thành gate issue; thiếu context REVIEW |
| Bài quảng cáo vé, comment “hủy vé hai tuần chưa được hoàn” | Xét comment REFUND_DISPUTE độc lập; parent không chặn child |
| “Chờ chơi trò này 40 phút” | Có complaint thì SERVICE_DELAY, không ENTRY_QUEUE của cổng dự án |
| “Đã báo thẻ lỗi nhưng vẫn không vào được” | UNRESOLVED_ISSUE + ACCESS_DENIED; chỉ thêm system failure nếu text nêu biểu hiện lỗi cụ thể |
| “Không ai trả lời, tiền cũng chưa hoàn” | NO_RESPONSE nếu đã liên hệ; REFUND_DISPUTE nếu đủ context giao dịch |
| Chỉ “đúng rồi” dưới complaint | Context endorsement chưa đủ claim độc lập; REVIEW, không copy toàn claim cha |
| Group Vũ Yên, comment chỉ rõ công viên khác | Ưu tiên explicit evidence, conflict/unresolved; không gán Vũ Yên từ group |
| Complaint rõ nhưng taxonomy chưa có nhãn | OTHER_CUSTOMER_COMPLAINT hoặc OTHER_RELEVANT đúng definition, kèm candidate mới; không ép nhãn gần nhất |
| Mốc “sáng nay”, “ngày hôm qua” trong text | Thời điểm sự việc khác published_at; không tự sửa ngày xuất bản metadata |

Mỗi node có thể nhiều issues nhưng vẫn một identity raw. Không cùng lúc gán GATE_CONGESTION_UNSPECIFIED và các nhãn gate cụ thể cho **cùng một claim** khi bằng chứng đã đủ; nếu node có hai claim khác nhau, evidence phải tách. OTHER_CUSTOMER_COMPLAINT chỉ cho claim còn lại, không dùng làm nhãn lặp cùng claim đã classified.

REFUND_DISPUTE và SERVICE_DELAY có thể cùng xuất hiện nếu có claim chậm xử lý riêng; không tự thêm delay chỉ vì chữ chưa hoàn. NO_RESPONSE không tự là UNRESOLVED_ISSUE nếu chưa có claim vấn đề đã được báo và vẫn tồn tại. Không tự suy technical root cause từ “không vào được”.

## 6. Project attribution, relevance và evidence

- `CONTENT_EXPLICIT`: target nêu tên/alias xác nhận dự án. `PARENT_CONTEXT`: dựa cha có evidence dự án. `GROUP_CONTEXT`: chỉ group mapping. `UNRESOLVED`: chưa đủ bằng chứng. Context-only không xuất như fact đã xác nhận.
- KEEP khi có claim liên quan mục tiêu và evidence đủ; vẫn ghi project basis nếu chỉ context. REVIEW khi thiếu context/project ambiguity/scope ngoài danh mục approved. DROP có reason nội dung rõ không liên quan/intent thuần túy, không dùng khi raw chưa đọc.
- Evidence quote trích nguyên input, chỉ rõ origin item ID. Claim trong parent không biến thành lời target; tác giả/URL/ngày lấy DB.
- Không lấy sự hiện diện từ khóa “tuyển dụng”, “bán vé”, “nợ”, “thuê” làm quyết định DROP. “Tuyển người, lương hấp dẫn” khác “Tôi bị nợ lương” về intent.
- Unknown author role giữ UNKNOWN. Người bán/đại lý/công viên/nhà thầu bị nhắc là đối tượng claim, không là trách nhiệm đã xác minh.

## 7. Version, mapping và điều kiện duyệt

17 shared issue definitions, mỗi profile có 16 enabled issues và một issue chưa bật. Priority chỉ đặt trong profile. Các nhãn tương thích PRD dùng mapping trong common.yaml; v2 nhiều issues cần legacy projection chọn một primary issue có evidence và ghi lý do theo priority/profile, giữ toàn v2 analysis. Cùng priority dùng policy explicit đã test, không chọn theo thứ tự JSON tùy tiện.

GATE_CONGESTION_UNSPECIFIED là extension mới, không có subcategory PRD v1 tương ứng chính xác. V2 giữ nhãn này; strict legacy projection đưa REVIEW/UNCLASSIFIED kèm reason NEEDS_GATE_SUBCATEGORY, không tự invent ENTRY_QUEUE hoặc gửi domain congestion với null subcategory qua validator v1. Không mở rộng enums v1 âm thầm.

P0 taxonomy checklist:

- [x] V1 definitions + positive/negative evidence examples, profiles và mapping draft.
- [x] Người dùng chấp nhận phạm vi baseline để tiếp tục triển khai.
- [ ] Mentor/reviewer xác nhận approved snapshot và mức ưu tiên chính thức.
- [ ] Chốt phạm vi lao động/an toàn/chất lượng dịch vụ và trách nhiệm bên thứ ba.
- [ ] Chốt VinCons project/site registry semantics; không tự activate proposed entry.
- [ ] Tạo golden/held-out labelled fixtures, kiểm thử TX-AC và live LLM phase sau.

Đổi định nghĩa/scope sau review tăng version; snapshot lưu cùng analysis. Runtime loader/classifier/Gemini đã có theo runbook worker, còn bàn giao draft này không có accuracy result. Checklist bên trên là gate review nghiệp vụ của draft, không dùng để kết luận hệ thống chưa có runtime.
