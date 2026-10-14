# Threads VinCons: truy vấn và kiểm tra đúng đối tượng

Ngày 13/10/2026. Trạng thái **IMPLEMENTED / OFFLINE_VERIFIED / LIVE_PARTIAL**. Provider **THREADS_BROWSER**, Playwright + Chrome và profile Threads hiện có; không dùng Threads API. Database, phiên đăng nhập, đánh giá thủ công và lịch hai nền tảng được giữ.

## Vấn đề và thay đổi

Đối soát ban đầu: 195 nội dung gắn nguồn `threads_vincons_name`, gồm 39 bản ghi POST và 156 REPLY. Không caption POST nào chứa `VinCons`/`Vin Cons`; 29 caption chứa `Vincent`. POST browser có thể chưa xác minh loại node, nên không coi đây là 39 bài gốc đã xác nhận. Pilot trực tiếp thấy ô tìm kiếm/URL đúng `VinCons` nhưng thẻ trong vùng kết quả vẫn không liên quan. Chưa xác định cơ chế xếp hạng/sửa lỗi của nền tảng; không khẳng định parser hoặc Threads tự đổi keyword thành Vincent.

Parser `threads-dom-v5` xác minh host/path/query và giá trị ô tìm kiếm trước khi đọc kết quả. Chỉ nhận card hiển thị thuộc `threads_search_results_*`; bỏ vùng gợi ý bên ngoài và DOM ẩn. URL sai báo `SEARCH_QUERY_MISMATCH`, ô tìm kiếm không xác minh được báo `SEARCH_QUERY_UNVERIFIED`, cấu trúc vùng kết quả đổi báo `SEARCH_RESULTS_SELECTOR_MISMATCH`. Không biến selector lỗi thành lượt thành công rỗng. Giá trị `filter=recent` và thứ tự UI được ghi nhận; không hứa nền tảng trả mọi bài theo thứ tự thời gian tuyệt đối.

Luồng: **search → commit raw/observation → kiểm tra evidence dự án và intent → fetch hội thoại đủ điều kiện → commit raw trả lời → filter/classify theo batch**. Việc hoãn hội thoại không xóa raw hoặc tự kết luận relevance DROP.

| Evidence scope | Hành vi |
| --- | --- |
| `MATCHED` | Caption/OCR có alias dự án đúng ranh giới từ; có thể fetch/rescan nếu không phải intent thương mại rõ |
| `NO_TARGET_EVIDENCE` | Caption có chữ nhưng không có bằng chứng đúng dự án; lưu raw, hoãn fetch/rescan, giữ để xem lại |
| `MISSING_EVIDENCE` | Thiếu caption hoặc có media có thể bổ sung evidence; cho phép kiểm tra trong quota riêng |

Alias lấy từ `config/projects.yaml`, không lấy keyword/query làm chứng cứ. `Vincent`, `notvincons`, `vinconsxyz` không khớp `VinCons`. Không bắt buộc caption chứa tên vấn đề: bài trung tính đúng VinCons vẫn có thể có bình luận phản ánh mới. Bài cũ đúng dự án hoặc có trả lời đã lưu nhắc đúng dự án vẫn được rescan; không bắt bài cha phải đăng trong window mới. Classifier nhận thêm alias `Vin Cons` là `CONTENT_EXPLICIT`; query đơn thuần vẫn là `QUERY_CONTEXT`, không đủ để KEEP.

Giới hạn mặc định: tối đa **2 hội thoại thiếu evidence/query**, tính cả lần thử lỗi. Gặp giới hạn ghi `UNVERIFIED_CONVERSATION_LIMIT`; raw đã lấy được vẫn giữ. Bài thiếu alias có thể bị hoãn dù bình luận chưa thu chứa phản ánh; đây là giới hạn recall cần reviewer đối chiếu, không được tuyên bố thu hết. OCR Threads chưa nghiệm thu; có media không đồng nghĩa đã OCR thành công. Intent thương mại rõ được kiểm tra sau commit raw và trước deep fetch; phản ánh có từ tuyển dụng vẫn giữ để xử lý. Một hội thoại fetch thành công chỉ mở một lần trong cùng run khi gặp qua nhiều query; observations tìm kiếm vẫn giữ từng query.

## Truy vấn đã bật

Config Threads version 3, tổng bảy truy vấn VinCons:

| ID | Chuỗi tìm kiếm |
| --- | --- |
| `threads_vincons_exact` | `"VinCons"` |
| `threads_vincons_gate` | `"VinCons" kẹt cổng` |
| `threads_vincons_shift` | `"VinCons" tan ca` |
| `threads_vincons_attendance` | `"VinCons" chấm công` |
| `threads_vincons_face` | `"VinCons" nhận diện khuôn mặt` |
| `threads_vincons_alias` | `Vin Cons` |
| `threads_vincons_name` | `VinCons`, giữ ID và lịch sử cũ |

Ưu tiên query có ngoặc kép và vấn đề trước query rộng. Ngoặc kép là chuỗi đã pilot, không phải cam kết exact-match hoặc Boolean AND của Threads. Các query theo vấn đề là seed cần đánh giá tiếp bằng phản ánh hữu ích; không suy tên/vị trí công trường chưa có metadata xác nhận. UI **Thu thập → Threads → VinCons → Nguồn theo dõi** đọc danh sách từ backend, không cần điền lại link. Lịch đã chọn VinCons tự dùng các query bật ở lượt kế tiếp; run đang chạy giữ query snapshot riêng.

## Kiểm chứng thật

Pilot truy vấn một trang/query, window đối chiếu UTC `[29/09/2026 05:20:20, 13/10/2026 05:20:20)`; query và window cố định trong report `reports/threads-vincons-query-pilot-20261013.json`. Không fetch hội thoại hoặc gửi model trong pilot này.

| Query | Card quan sát | Caption đúng alias | Thiếu evidence/media | Chưa có evidence dự án |
| --- | ---: | ---: | ---: | ---: |
| `VinCons` | 0 | 0 | 0 | 0 |
| `Vin Cons` | 0 | 0 | 0 | 0 |
| `VinCons kẹt cổng` | 7 | 0 | 2 | 5 |
| `"VinCons"` | 6 | 2 | 1 | 3 |

Kết quả 0 chỉ nói về trang quan sát lúc pilot, không chứng minh không tồn tại nội dung. Hai caption đúng alias chưa phải hai phản ánh; một tài khoản/đường dẫn có dấu hiệu tuyển dụng cũng phải qua rule và model. Không suy precision toàn nền tảng từ sáu card.

Sau triển khai, scheduler đã tự chạy `threads_8cd13e61a84547a19b809ca9859b98ae` qua lease chung, window UTC `[13/10 02:00, 13/10 05:00)` = Việt Nam **09:00–12:00**. Report đối chiếu `reports/threads-vincons-production-pilot-20261013.json` giữ window, query snapshot, outcomes, scopes và raw IDs. Bản chụp giữa lượt lúc 12:27:03 có 34 candidate, 10 caption khớp alias, 19 chưa có evidence, 5 thiếu evidence; 53 node đã lưu gồm các trả lời, 13 trong window và 40 ngoài window. Hoãn 6 hội thoại không có evidence và 2 intent thương mại, 8 roots không đủ evidence được bỏ khỏi inventory rescan. Các số này là snapshot đang chạy, không phải kết quả cuối hoặc số phản ánh.

**Kết quả lượt cuối lúc 12:29:34:** cả bảy query đã chạy, `PARTIAL`, tất cả xác minh query và parser v5. Quan sát 82 candidate occurrences: 11 khớp alias, 26 thiếu evidence, 45 không có evidence dự án. Lưu 142 node duy nhất trong run (70 POST, 72 REPLY chưa xác minh parent); 25 trong window, 117 ngoài window do inventory/hội thoại. Hoãn 38 lần mở hội thoại không có evidence, 4 intent thương mại và 26 do quota thiếu evidence; 67 lượt xét root không đủ evidence không được thêm vào rescan. Counts hoãn có thể gặp cùng root qua nhiều query, không phải số bài duy nhất bị loại. Mở thành công 19 hội thoại; chưa có bản phân loại model cho tập này tại snapshot 12:31, 142 jobs đang PENDING trong hàng chờ chung. Worker vẫn hoạt động và có HTTP 200 cho batch khác; không coi pending là kết quả model hoặc 11 caption đúng tên là 11 phản ánh.

Trong lần quan sát này, các query vấn đề chưa có caption xác nhận VinCons. Ngoặc kép cải thiện số caption nhắc đúng tên trong tập quan sát; chưa chứng minh các query mới tăng recall phản ánh. Bước tiếp theo cần reviewer đánh giá output đã phân loại và bổ sung tên công trường/vị trí được xác nhận, không tự mở topic chung `kẹt xe`/`công nhân`.

## Nghiệm thu và còn mở

**109 kiểm thử đạt**, dùng config v3 cuối cùng. Kiểm thử local gồm alias/ranh giới từ, OCR/missing caption, raw-first/không xóa reviews, rerun/dedup, bài cũ/comment mới, complaint có chữ tuyển dụng, quota thiếu evidence, query URL/input mismatch, vùng gợi ý/DOM ẩn, selector drift và hồi quy classifier/lịch/database/dashboard. Log: `reports/threads-scope-tests-20261013.log`.

Live chứng minh parser v5 và scope gate đã được dùng trong lượt scheduler thật; không nghiệm thu thu hết window, nested parent, chất lượng tất cả seed hoặc số phản ánh/ngày. Query context không tự xác nhận dự án; `MATCHED` cũng chỉ xác nhận bằng chứng tên, không xác nhận nội dung là khiếu nại. Phân loại còn theo taxonomy hiện hành, giữ DONE còn hợp lệ. Để xem raw đã hoãn, dùng **Kho dữ liệu → Threads → nguồn/query**; bộ lọc Phản ánh hiển thị kết quả nghiệp vụ sau xử lý, không đồng nhất tổng raw với tổng phản ánh.
