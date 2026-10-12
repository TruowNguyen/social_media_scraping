# Truy vết nhãn phân loại — 11/10/2026

## Kết quả kiểm tra kho dữ liệu

Ảnh chụp lúc 12:37 giờ Việt Nam: **2.969 nội dung**, gồm 453 bài viết, 2.021 bình luận và 495 trả lời. Mỗi bình luận/trả lời được phân loại độc lập; số nội dung không phải số bài viết hay số phản ánh. Không có thao tác xóa hoặc gán nhãn giả để giảm số lượng.

| Trạng thái hiện hành | Số nội dung | Vì sao chưa có nhãn |
| --- | ---: | --- |
| Hoàn thành | 1.111 | Đã có kết quả được validator chấp nhận |
| Đang chờ | 1.322 | Chưa có kết quả hợp lệ cho đầu vào hiện hành |
| Thiếu nội dung | 306 | Chưa có caption/comment hoặc chữ OCR để phân loại |
| Lỗi | 67 | 66 lỗi điều kiện OCR; 1 lỗi cấu trúc response |
| Bộ lọc loại | 163 | Không cần gọi model; ý định lấy từ quyết định bộ lọc |

1.111 kết quả hoàn thành đều có `content_intents`; 39 có nhãn `UNKNOWN` (model chưa rõ ý định). Kết quả gồm 1.060 DROP, 38 REVIEW và 13 KEEP. Toàn bộ 1.060 DROP có `issues=[]` đúng contract; 33 REVIEW chưa có nhóm vấn đề và cần đối chứng bằng chứng. Không coi nhãn UNKNOWN hoặc REVIEW là thiếu trường/schema, không coi 13 KEEP là tất cả phản ánh tồn tại ngoài hệ thống.

## Nguyên nhân và bản sửa

1. **Số đếm lịch sử:** health cũ cộng mọi job/model/revision, báo 2.161 DONE trong khi chỉ 1.111 nội dung hiện hành hoàn thành. Health mới trả `classification.counts` theo từng node hiện hành; `job_counts` giữ số job lịch sử để kiểm tra. Tab Phản ánh vẫn một dòng/node.
2. **Nhãn giao diện:** “Chưa xác định” trước đây gộp chờ, lỗi, thiếu text, bộ lọc loại và chưa rõ ý định. Bảng/mobile/chi tiết nay phân biệt các trạng thái; REVIEW không có issue hiển thị “Chưa đủ bằng chứng xác định vấn đề”, DROP không issue là “Không ghi nhận vấn đề”.
3. **Điều kiện OCR:** validator yêu cầu mọi item có OCR NEEDS_REVIEW/UNKNOWN, kể cả ảnh của bài cha, phải đánh dấu cần xem xét và không DROP. Hướng dẫn model trước đây dễ hiểu thành chỉ cần review khi quyết định dựa vào OCR; model trả DROP cho caption/bình luận mua bán rõ ràng và bị từ chối dù HTTP 200. Gateway nay nêu rõ thứ tự ưu tiên và gửi danh sách item cần tuân thủ điều kiện này. Không sửa OCR, taxonomy, validator hoặc nhãn model; giữ các kết quả hợp lệ đã lưu.
4. **Bộ lọc ý định:** backend trước đây dùng nhãn prefilter cả cho nội dung đang chờ, trong khi UI chỉ hiển thị nhãn rule ở FILTER_DROP. Nay chỉ dùng ý định model hoặc nhãn rule của FILTER_DROP; không tạo cảm giác đã được model phân loại.

Hướng dẫn gateway chỉ làm rõ điều kiện validator đã có, không đổi chính sách taxonomy/prompt binding để buộc phân loại lại toàn kho. Thiếu text cần thu thập lại; UNKNOWN/REVIEW cần mẫu do người dùng đánh giá, chưa được tự đổi thành COMPLAINT hoặc một nhóm vấn đề.

## Kiểm chứng và bước còn lại

- [Ảnh chụp dữ liệu](../../reports/classification-diagnosis-20261011-audit.json); SQLite đã sao lưu tại `sessions/backups/classification-diagnosis-20261011.sqlite3`.
- 261/261 kiểm thử hồi quy offline đạt, gồm Chromium và OCR; [kết quả](../../reports/ocr-test-result.json).
- [API với dữ liệu hoàn toàn giả lập](../../reports/classification-ocr-synthetic-20261011.json): một bài có OCR thiếu tin cậy và một bình luận có OCR bài cha, HTTP 200, 2/2 vượt validator. Intent vẫn là mua bán, relevance REVIEW do điều kiện OCR. Đây không phải nghiệm thu độ chính xác trên dữ liệu thật.
- [Dashboard đọc thật desktop/mobile](../../reports/classification-label-live-check-20261011.json): kiểm tra trạng thái chờ/lỗi/thiếu nội dung/bộ lọc loại, không crawl hoặc gọi phân loại.
- Người dùng đã cho phép kiểm thử đúng hai trường hợp thật. [Pilot lúc 12:57 giờ Việt Nam](../../reports/classification-diagnosis-20261011-approved-live.json): một request, hai item, HTTP 200, 2/2 vượt validator, không item bị từ chối. Bài bán điện thoại có ADVERTISING + SALES, bình luận có BUY_SELL; cả hai REVIEW, needs_review=true, không issue. Đây là review vì chất lượng OCR, không phải khẳng định có phản ánh.
- Phép thử chỉ đọc đầu vào đã lưu, không ghi kết quả model vào `node_analyses`, không đổi trạng thái job và không gửi thêm nội dung ngoài hai trường hợp được phép. Không coi hai mẫu này là accuracy hoặc nghiệm thu completion toàn kho.
- Worker nền vẫn tạm dừng; dashboard chạy và cấu hình lịch crawl giữ nguyên. Bước vận hành tiếp theo là đưa **chỉ lỗi OCR hiện hành** về hàng chờ và phục hồi worker trong phạm vi được cho phép, giữ DONE hợp lệ. Kiểm tra tỷ lệ accepted/rejected các batch kế tiếp; không tự mở rộng quyền kiểm thử hai item thành gửi toàn kho.
- Thu thập lại 306 nội dung thiếu đầu vào theo trạng thái parser/media. Đối chứng mẫu 39 UNKNOWN và 33 REVIEW không issue với đánh giá con người trước khi thay taxonomy/chính sách OCR của bài cha.
- Đề xuất sau đối chứng: phân biệt OCR mục tiêu với OCR bài cha, và kết luận thực sự dùng OCR với kết luận đủ bằng chứng từ caption/comment. Chính sách hiện tại áp điều kiện review cho mọi OCR thiếu tin cậy trong context nên có thể tăng REVIEW dù ý định bình luận rõ. Việc đổi phạm vi điều kiện này cần sửa contract, bộ ví dụ và acceptance; bản sửa hướng dẫn model hiện tại chưa thay chính sách đó.

Trạng thái: **IMPLEMENTED / OFFLINE_VERIFIED / SYNTHETIC_API_VERIFIED / LIVE_READ_VERIFIED / LIVE_API_VERIFIED (hai mẫu được phép)**. Hai mẫu thật đã xác nhận bản sửa điều kiện OCR; nghiệm thu các lỗi còn lại, chất lượng phân loại và completion hàng chờ chưa hoàn thành.

## Cập nhật sau quyền toàn hàng chờ — 11/10/2026

Các số liệu và trạng thái tạm dừng phía trên là snapshot trước khi người dùng cho phép Gemini chạy toàn hàng chờ. Lượt sau đã phục hồi 195 đầu vào và xử lý hàng chờ: 2.692 DONE / 2.969 node, 166 FILTER_DROP, 111 MISSING_TEXT; không còn job chờ/lỗi hiện hành. Cả 67 lỗi cũ, gồm 66 lỗi OCR, đã DONE. REVIEW/UNKNOWN còn lại là kết luận cần đối chứng, không tự sửa thành phản ánh. Người dùng tiếp tục cho phép worker chạy liên tục cho dữ liệu mới/thay đổi; worker hiện ACTIVE, giữ 2.692 DONE hợp lệ và không gọi lại API trong lượt không có đầu vào mới. [Biên bản và bằng chứng cuối](facebook-recovery-classification-20261011.md), [bằng chứng worker](../../reports/classifier-continuous-enabled-20261011.json).
