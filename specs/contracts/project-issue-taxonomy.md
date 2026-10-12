# Taxonomy vấn đề theo dự án

**Đồng bộ 11/10/2026:** [review snapshot 1.0.0-draft.1](../taxonomy/v1/README.md) vẫn DRAFT/disabled; runtime riêng tại `config/taxonomy/v1` là 1.0.0 APPROVED/enabled, có approval provenance từ người dùng chấp nhận baseline để triển khai. Loader, profiles, fixtures và classifier đã có code; mentor/held-out acceptance còn pending. [Trạng thái hiện hành](../../docs/current-state.md).

Contract `project-issue-taxonomy-v1` thiết kế ngày 09/10/2026; taxonomy/runtime increment đã implement, full business acceptance chưa hoàn tất. Thuộc [kế hoạch tổng thể](../../docs/implementation-plan-v2.md), input cho [batch classification](llm-batch-classification.md). YAML snippet 2026-10-09.draft1 bên dưới là proposal ban đầu, không thay version/schema của snapshot runtime 1.0.0.

## 1. Cấu trúc và nguyên tắc

Taxonomy chung định nghĩa nhóm vấn đề; mỗi dự án bật subset và có thể bổ sung issue riêng. Project Registry tiếp tục quản lý tên/alias/group, chỉ tham chiếu taxonomy version, không trộn rule vào metadata nguồn. Mã issue ổn định; đổi định nghĩa ảnh hưởng kết quả phải tạo version mới. Ngừng dùng nhãn bằng deprecated, không đổi nghĩa ID cũ.

| ID requirement | Yêu cầu |
| --- | --- |
| TX-001 | Versioned taxonomy dùng chung + cấu hình per-project; validate references trước enqueue |
| TX-002 | Mỗi issue có định nghĩa, include/exclude, required evidence và priority; keyword không đủ để gán nhãn |
| TX-003 | Node có thể nhiều issues/dự án; project fact khác context group; dự án chưa rõ không bị loại ngay |
| TX-004 | OTHER_RELEVANT + REVIEW hỗ trợ vấn đề chưa có nhãn/thiếu evidence; không ép vào category gần nhất |
| TX-005 | Mapping taxonomy→domain/subcategory PRD explicit; version/reanalysis giữ lịch sử và review |

Đường dẫn cấu hình dự kiến: `config/taxonomies/common.yaml`, `config/taxonomies/projects/<project_id>.yaml`. Loader dự kiến `src/analysis/taxonomy.py`; code dưới `src` không import `engine`. Chưa tạo config active hoặc thay config hiện tại bằng file spec.

```yaml
schema_version: project-issue-taxonomy-v1
taxonomy_version: "2026-10-09.draft1"
project_id: vinwonders_vu_yen
status: DRAFT
enabled_issue_ids:
  - ACCESS_DENIED
  - CHECKIN_BOTTLENECK
  - ENTRY_QUEUE
  - EXIT_QUEUE
  - VEHICLE_CONGESTION
  - SERVICE_DELAY
  - NO_RESPONSE
  - REFUND_DISPUTE
issues:
  - issue_id: CHECKIN_BOTTLENECK
    name: Kiểm soát ra vào chậm
    definition: Phản ánh chậm trễ tại khâu kiểm tra quyền vào hoặc ra.
    family_id: SITE_ACCESS_CONGESTION
    include_examples:
      - Quét QR vé mãi không được, xếp hàng chờ kiểm tra rất lâu.
    exclude_examples:
      - Hướng dẫn khách chuẩn bị QR trước khi đến.
      - Cổng đông vui, đi chơi rất thích.
    required_evidence:
      - Có claim chậm trễ hoặc trở ngại kiểm soát ra vào, không chỉ có từ cổng.
    priority: P0
    legacy_domain: SITE_ACCESS_CONGESTION
    legacy_subcategory: CHECKIN_BOTTLENECK
```

Priority là ưu tiên theo dõi của dự án, không phải mức nghiêm trọng sự cố do model suy đoán.

## 2. Seed và mapping đề xuất

| issue_id | Định nghĩa ngắn / điều kiện | Nhóm | Mapping PRD v1 |
| --- | --- | --- | --- |
| ACCESS_DENIED | Bị từ chối/không thể vào hoặc ra, có claim cụ thể | SITE_ACCESS_CONGESTION | ACCESS_CONTROL_FAILURE |
| CHECKIN_BOTTLENECK | Thẻ/QR/giấy tờ/khâu kiểm tra gây chậm trễ | SITE_ACCESS_CONGESTION | CHECKIN_BOTTLENECK |
| ENTRY_QUEUE | Xếp hàng/chờ tại chiều vào | SITE_ACCESS_CONGESTION | ENTRY_QUEUE |
| EXIT_QUEUE | Xếp hàng/chờ tại chiều ra | SITE_ACCESS_CONGESTION | EXIT_QUEUE |
| VEHICLE_CONGESTION | Xe ùn tắc trong phạm vi tiếp cận/cổng/bãi xe có liên hệ dự án | SITE_ACCESS_CONGESTION | VEHICLE_CONGESTION |
| WORKER_CONGESTION | Công nhân tập trung ùn ứ, không tự suy từ group công nhân | SITE_ACCESS_CONGESTION | WORKER_CONGESTION |
| EXTERNAL_TRAFFIC_IMPACT | Giao thông bên ngoài ảnh hưởng tiếp cận dự án | SITE_ACCESS_CONGESTION | EXTERNAL_TRAFFIC_IMPACT |
| SERVICE_DELAY | Chậm xử lý/phục vụ có phản ánh | CUSTOMER_COMPLAINT | SERVICE_DELAY |
| NO_RESPONSE | Không nhận phản hồi sau yêu cầu/liên hệ | CUSTOMER_COMPLAINT | NO_RESPONSE |
| APP_SYSTEM_ISSUE | Lỗi app/hệ thống khách dùng | CUSTOMER_COMPLAINT | APP_SYSTEM_ISSUE |
| STAFF_ATTITUDE | Phản ánh thái độ nhân viên có claim | CUSTOMER_COMPLAINT | STAFF_ATTITUDE |
| UNRESOLVED_ISSUE | Vấn đề đã báo nhưng chưa được giải quyết | CUSTOMER_COMPLAINT | UNRESOLVED_ISSUE |
| REFUND_DISPUTE | Tranh chấp/chậm/từ chối hoàn tiền, không phải quảng cáo chính sách hoàn tiền | CUSTOMER_COMPLAINT | OTHER_COMPLAINT |
| OTHER_CUSTOMER_COMPLAINT | Khiếu nại rõ nhưng không thuộc nhóm chi tiết đã bật | CUSTOMER_COMPLAINT | OTHER_COMPLAINT |
| OTHER_RELEVANT | Liên quan mục tiêu dự án nhưng ngoài các nhóm trên | OTHER_RELEVANT | null |

Mỗi seed khi triển khai phải có include/exclude/required evidence đầy đủ, không chỉ table này. Nếu mở thêm an toàn/chất lượng dịch vụ, phải xác nhận định nghĩa và mapping, không âm thầm thêm domain vào schema PRD v1.

VinCons đề xuất ưu tiên ACCESS_DENIED, CHECKIN_BOTTLENECK, ENTRY_QUEUE, EXIT_QUEUE, VEHICLE_CONGESTION, WORKER_CONGESTION, EXTERNAL_TRAFFIC_IMPACT. VinCons chưa có project entry riêng trong config hiện tại: cần tạo project ID/alias/source mapping đã xác nhận trước khi bật taxonomy.

VinWonders Vũ Yên đề xuất ưu tiên kiểm soát vé/QR, hàng chờ vào/ra, xe, chậm phục vụ, không phản hồi và hoàn tiền. Group bán vé không tự chứng minh người viết là khách của công viên; model phải phân biệt lời quảng cáo với trải nghiệm/phản ánh.

## 3. Phân loại và ambiguity

Relevance KEEP/DROP/REVIEW độc lập với issue. DROP có reason intent hoặc không liên quan và thường không có issues. KEEP cần grounded issue hoặc OTHER_RELEVANT. REVIEW khi thiếu text/context, mâu thuẫn, phản ánh có thể liên quan nhưng project chưa rõ hoặc không đủ evidence.

Không dùng toàn bộ vấn đề đã bật làm giả định rằng mọi node đều thuộc chúng. Một comment “kẹt cổng quá” có thể cần context; nếu group dự án là bằng chứng duy nhất thì project basis GROUP_CONTEXT, không CONTENT_EXPLICIT. Comment chỉ “đúng rồi” không tự trở thành phản ánh độc lập đã xác nhận.

Project matches: CONTENT_EXPLICIT, GROUP_CONTEXT, PARENT_CONTEXT hoặc UNRESOLVED. Nếu nội dung chỉ rõ dự án khác với group, ưu tiên evidence nội dung, giữ conflict để review. Nếu nhiều dự án có khả năng khớp, dùng candidate profiles và đánh dấu ambiguity; không nhân node thành nhiều raw rows.

## 4. Acceptance — PLANNED

| ID | Input | Expected |
| --- | --- | --- |
| TX-AC01 | Missing issue/duplicate ID/unknown mapping/cấu hình chưa approved | Fail validation; không enqueue taxonomy lỗi |
| TX-AC02 | “Cổng đông vui” và “chờ cổng 40 phút” | Câu đầu không tự gán congestion; câu sau có evidence |
| TX-AC03 | QR lỗi và hàng chờ trong cùng comment | Nhiều issues nếu đủ evidence, không ép một nhãn |
| TX-AC04 | Group Vũ Yên nhưng text nhắc dự án khác | Không khẳng định Vũ Yên từ group; conflict/explicit match rõ |
| TX-AC05 | Complaint rõ chưa có issue / comment thiếu context | OTHER complaint hoặc OTHER_RELEVANT đúng definition; missing evidence REVIEW |
| TX-AC06 | Đổi taxonomy, nhãn deprecated và reprocess | Analysis mới có version, lịch sử/review không mất, không gọi nhãn cũ là nghĩa mới |

Đối chiếu FR-02/06/09/10/11/14 và yêu cầu taxonomy per-project ngày 09/10/2026. ACP: mentor duyệt danh sách pilot cùng examples/mapping; tests và dữ liệu đối chứng sau triển khai.
