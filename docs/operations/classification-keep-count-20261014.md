# Đối chiếu số kết quả Giữ — 14/10/2026

## Kết luận

Hiện có 18 nội dung với kết quả phân loại hiện hành KEEP (Giữ). Số giảm do các nội dung từng được Giữ đã có kết quả mới REVIEW (Cần xem xét), không phải các nội dung đó bị xóa. Chưa tìm được snapshot chứng minh chính xác mốc 23; không suy diễn năm nội dung cụ thể từ chênh lệch người dùng nhớ.

Các snapshot không giới hạn ngày/dự án ngày 13/10/2026 có cùng bộ lọc `date_basis=published_at`, `project_basis=SOURCE`: lúc 18:01:43 Việt Nam có 20 Giữ; lúc 20:03:11 còn 18. Đối chiếu identity cho thấy hai nội dung đổi từ KEEP sang REVIEW. Cả hai hiện DONE, không có error_code.

| Nội dung | Lý do kết quả hiện hành | Thay đổi đầu vào đối chiếu |
| --- | --- | --- |
| [Bình luận phản ánh lỗi ứng dụng](https://www.facebook.com/groups/1675953926771851/posts/1820192229014686?comment_id=1820305965669979) | OCR ảnh bài cha cần xem xét; dự án nhận diện từ ngữ cảnh nhóm | Ngữ cảnh bài cha và image evidence thay đổi; model khác giữa lần KEEP lịch sử và lần REVIEW gần nhất |
| [Bình luận đăng ký ứng tuyển chưa có phản hồi](https://www.facebook.com/groups/2249052912495339/posts/2303115727089057?comment_id=2305029003564396) | Có phản ánh nhưng ngoài nhóm vấn đề vận hành đang theo dõi | Ngữ cảnh thay đổi; model giống nhau giữa lần KEEP gần nhất và lần REVIEW gần nhất |

## Lịch sử và cách đọc số liệu

- Trong toàn bộ lịch sử còn lưu có 31 identity từng ít nhất một lần KEEP; hiện 18 KEEP và 13 REVIEW. Đây không phải bằng chứng từng có 31 KEEP đồng thời hoặc phép đối chiếu 23 → 18.
- Cả 13 nội dung chuyển trạng thái vẫn còn trong raw và có kết quả hiện hành DONE/REVIEW. Không phải đang lỗi API hoặc mất kết quả vì còn chờ phân loại.
- Đối chiếu payload job giữa lần KEEP gần nhất và kết quả mới nhất: cả 13 có thay đổi revision, context hoặc image evidence; taxonomy snapshot không đổi. Một số cũng đổi model, nhưng không thể quy toàn bộ thay đổi kết quả cho model.
- Dashboard lấy kết quả hợp lệ cho phiên bản hiện tại. Khi dữ liệu/ngữ cảnh/OCR thay đổi, job mới có thể được tạo và nhãn mới thay thế nhãn đang hiển thị; kết quả lịch sử vẫn lưu. Worker tái sử dụng kết quả còn hợp lệ.
- Nhãn REVIEW là lời giải thích của hệ thống/model, chưa phải đánh giá độc lập khẳng định nội dung không liên quan. Case ngoài taxonomy hoặc OCR chưa chắc chắn cần người dùng rà soát.

## Đề xuất tiếp theo

Hiển thị lịch sử đổi nhãn trong chi tiết nội dung; giữ quyết định đánh giá của người dùng riêng với nhãn model. Đối chiếu thay đổi revision/context chỉ do metadata trước khi tối ưu tránh phân loại lại không cần thiết. Chưa thay đổi policy hoặc tự nâng các nội dung REVIEW về KEEP trong lần chẩn đoán này.

Evidence local: `reports/classification-count-audit-20261014.json`, `reports/classification-binding-audit-20261014.json`. Kiểm tra chỉ đọc database; không gọi API Gemini, không sửa nhãn và không xóa dữ liệu.

## Bổ sung: 18 → 17 sau lượt chạy tiếp theo

Đối soát trực tiếp xác nhận một trường hợp khác với việc KEEP → REVIEW ở trên:

- Identity `item_63e4f1ce190944cdbed02c7d01ee54f3`, [bài gốc](https://www.facebook.com/groups/1675953926771851/posts/1810820063285236).
- Kết quả cũ DONE/KEEP còn lưu. Job mới rowid 17542 ở trạng thái PENDING, attempts=0, chưa có lỗi hoặc kết quả model cho phiên bản này tại thời điểm đọc.
- Payload input mới so với job KEEP gần nhất chỉ đổi `revision_id`. Caption cùng 99 ký tự, không có OCR ở cả hai phiên bản, không có context thay đổi.
- Đối chiếu các trường fingerprint raw: chỉ `availability_status` đổi từ AVAILABLE sang UNKNOWN. Điều này tạo revision raw mới, khiến binding phân loại bị coi là thay đổi mặc dù bằng chứng gửi model giống nhau.
- Dashboard chỉ hiển thị analysis của job hợp lệ với revision hiện hành: chọn job PENDING thay vì KEEP của revision trước; vì vậy bộ đếm KEEP tạm giảm. Chưa có bằng chứng bài này bị model đổi sang REVIEW/DROP.

Worker hiện gọi `prepare_saved` trên toàn kho trong mỗi vòng đối soát, không chỉ lúc khởi động. Điều này là quét/đọc local; không đồng nghĩa gửi toàn bộ dữ liệu lên API. Log có nhiều vòng liên tiếp `completed_reused=5012`, `jobs_inserted=0`, `api_calls=0`. Khi revision thay đổi, những nội dung đó mới có thể phát sinh job. Lần chẩn đoán trước chưa kiểm tra đủ nhánh invalidation do metadata; phát biểu “số giảm là đổi nhãn” không bao quát trường hợp 18 → 17 này.

Hướng sửa cần làm: phân biệt phiên bản lưu trữ và fingerprint bằng chứng phân loại; thay đổi availability/thời gian thu/tương tác không tự yêu cầu gọi model lại nếu caption/context/OCR/taxonomy/rule không đổi. Dashboard cần thể hiện riêng kết quả được chấp nhận gần nhất và trạng thái cập nhật để không khiến người dùng hiểu mất phản ánh khi job đang chờ. Không ghim KEEP bất chấp nội dung thay đổi, không sửa số đếm hoặc phục hồi nhãn bằng cách ghi đè database.

Evidence snapshot: `reports/classification-restart-cause-20261014.json`. Bổ sung này chỉ chẩn đoán, chưa thay đổi cơ chế invalidation hay chính sách hiển thị.

## Bản sửa đã triển khai — 14/10/2026

- `evidence_payload` tách nội dung dùng phân loại khỏi revision raw: bỏ riêng `revision_id` của target/context/OCR; giữ text, evidence ID, OCR quality, vai trò, identity, source, project/query scope và mọi trường đầu vào khác.
- Queue tái sử dụng DONE đã accepted khi bằng chứng tương đương, taxonomy và job binding prompt/rule/policy còn hợp lệ. Giữ nguyên model, job, revision và thời điểm phân loại lịch sử; không sao chép kết quả sang một lần gọi model giả.
- Job PENDING đã sinh do metadata-only revision được chuyển STALE với `EVIDENCE_UNCHANGED` khi worker gặp, không gọi model lần nữa. Thử nghiệm model khác với cùng revision vẫn giữ hành vi enqueue trực tiếp.
- Dashboard ưu tiên kết quả accepted còn hợp lệ; PENDING trùng metadata không che kết quả cũ. Caption/context/OCR/taxonomy/prompt thực sự thay đổi vẫn vô hiệu hóa kết quả cũ; không ghim KEEP khi bằng chứng đổi.
- Worker vẫn đọc kho local để đối soát. Bản sửa này không triển khai incremental SQL/outbox-only và không tuyên bố đã bỏ toàn bộ lượt scan local.

Kiểm thử hồi quy: bộ phân loại/dashboard 126 test chạy, **125 đạt / 1 opt-in OCR skip**; thêm **15 storage test đạt** sau khi thêm index. Tổng 140 đạt / 1 skip. Gồm đóng/mở lại database, availability/tương tác/metadata cha thay đổi, PENDING trùng, metadata đổi trong lúc provider chạy, caption thực sự chuyển sang bán hàng, context thiếu, OCR đổi và taxonomy/prompt đổi. Provider fixture xác nhận không gọi lại khi metadata-only. Không gọi Gemini để nghiệm thu việc tái sử dụng.

Đối soát database thật bằng code mới và HTTP dashboard sau nạp: **18 KEEP**, identity bị ảnh hưởng trở lại DONE/KEEP với job `76da151908d5854514e1bbc6ed3ff8e9f65365a217eecc2f96c879fe6cb9b6bb`, model lịch sử `ag/gemini-3.7-flash-low`, thời điểm accepted giữ nguyên `2026-10-09T22:09:14.563936+00:00`. Bản cuối kiểm tra đầy đủ cả query/project context thay vì chỉ tin raw revision. Đo lại từng có request 34,242 giây do tra context Threads lặp lại trên bảng observations chưa có index phù hợp. Đã thêm `observation_node_source(node_id,source_id)` vào DDL và database thật; query plan xác nhận dùng index, API mới trả 200 trong **4,530 giây**, vẫn 18 KEEP. Đây là số đo tại thời điểm nghiệm thu, không phải bảo đảm latency. Report `reports/classifier-metadata-live-20261014.json`.

Job trùng của đúng identity thật cũng đã đi qua `ClassificationJobs.claim(node_ids=[...])`: kết thúc STALE / `EVIDENCE_UNCHANGED`, attempts vẫn 0, không gọi API. Evidence `reports/classifier-metadata-target-queue-20261014.json`. Trạng thái STALE này thuộc job trùng lịch sử, không thay đổi trạng thái DONE/KEEP của kết quả được tái sử dụng.

Đã nạp lại dashboard/classifier sau khi xác minh Facebook/Threads không chạy và không còn lease model có hiệu lực. Supervisor cũ đã dừng trước thời điểm nạp (status file cũ); kiểm tra không còn process rồi khởi động runtime mới ẩn, xác nhận API hoạt động lại. Giữ database, cấu hình lịch, phiên browser và đánh giá. Không dùng lần này làm bằng chứng reboot Windows hoặc sửa triệt để nguyên nhân supervisor cũ dừng.

Trên tab Phản ánh, bấm **Làm mới dữ liệu** để tạo snapshot mới. Reload một URL chứa `view_id` cũ có thể tiếp tục mở snapshot trước bản sửa.
