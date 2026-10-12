# Tab Phản ánh: bộ lọc và taxonomy

## Mục đích

Tìm nội dung đã lưu, xem nhóm vấn đề theo taxonomy, đọc hội thoại và ghi nhận đánh giá. Dữ liệu đang chờ phân loại không được coi là phản ánh đã xác nhận hoặc nội dung đã bị loại.

Đánh giá Impeccable được thực hiện trực tiếp theo lựa chọn của người dùng, không dùng agent phụ. Bản trước chỉnh sửa được lưu tại [bản đánh giá](../../.impeccable/critique/2026-10-10T13-58-45Z__engine-dashboard-workspace-html.md). Điểm 22/40 là đánh giá UX trước thay đổi, không phải độ chính xác classifier hoặc điểm sau triển khai.

## Bộ lọc hiện tại

| Bộ lọc | Vị trí | Backend / ý nghĩa |
| --- | --- | --- |
| Từ khóa | Chính | `keyword`: văn bản đích và chữ OCR đã lưu, tìm không phân biệt dấu |
| Dự án theo dõi | Chính | `project_id` + `project_basis=SOURCE`: nguồn gắn trong cấu hình dự án hoặc bí danh trong văn bản; giữ được nội dung đang chờ |
| Nhóm vấn đề | Chính | `issue_id`: ID taxonomy trong kết quả model đã được chấp nhận; danh mục lấy từ backend, thu hẹp theo dự án |
| Group | Chính | `source_id`: nguồn đã ghi nhận của nội dung; một nội dung có thể thuộc nhiều group |
| Kết quả phân loại | Chính | `relevance`: Giữ, Cần xem xét, Loại, Chưa có kết quả; Loại gồm bộ lọc hoặc model |
| Khoảng ngày | Chính | `start_date` / `end_date`: ngày Việt Nam, gồm ngày kết thúc |
| Trạng thái xử lý | Thêm bộ lọc | `processing_status`: đang chờ, đang xử lý, hoàn thành, lỗi, thiếu nội dung, cần phân loại lại, vượt kích thước, chưa có job, bộ lọc loại |
| Đánh giá của tôi | Thêm bộ lọc | `review`: đánh giá người dùng, lưu riêng với kết quả model |
| Loại nội dung | Thêm bộ lọc | `node_type`: bài viết, bình luận, trả lời |
| Ý định nội dung | Thêm bộ lọc | `intent`: đủ 10 giá trị từ schema backend; kết quả model, hoặc rule đã lưu khi bộ lọc loại |
| Khoảng ngày tính theo | Thêm bộ lọc | Ngày đăng hoặc có lần thu thập trong khoảng; không dùng ngày của bài cha thay cho ngày bình luận |

Sắp xếp theo thời gian và xuất Excel nằm cạnh kết quả. Chất lượng trích xuất, OCR và lựa chọn lần thu thập mới nhất nằm trong Kho dữ liệu. Bỏ bộ đếm bấm nhanh trùng với dropdown kết quả và bỏ lựa chọn căn cứ dự án khỏi giao diện mới.

Backend vẫn đọc được liên kết/phiên cũ dùng `project_basis=MODEL` hoặc bộ lọc kỹ thuật. Giao diện ghi rõ khi đang lọc dự án theo model; “Xóa bộ lọc” đưa về mặc định nguồn theo dõi. Phiên chốt cũ vẫn giữ dữ liệu cũ; dùng “Làm mới dữ liệu” để xem phiên mới.

### Xóa bộ lọc

Nút **Xóa bộ lọc** bỏ các điều kiện tìm kiếm, trả sắp xếp về mới nhất và tự tải lại bảng từ trang 1; không cần bấm Áp dụng thêm. Thông báo hiển thị khi đang tải và sau khi hoàn tất. URL và phiên chốt được cập nhật theo bảng mới. Thao tác này không xóa dữ liệu, đánh giá, ghi chú hoặc rule phân loại.

Nếu tải lỗi, bảng giữ kết quả trước và thông báo yêu cầu bấm Xóa bộ lọc để thử lại; không báo thành công khi chưa nhận được dữ liệu. Sửa ngày sai cũng xóa trạng thái báo lỗi của trường ngày.

Kiểm chứng bản sửa ngày 10/10/2026: 13 kiểm thử contract/browser đạt, gồm xóa không cần Áp dụng ở cả hai tab, về trang 1, cập nhật URL, giữ nháp, lỗi tải và thử lại. Dashboard thật desktop/mobile xác nhận mỗi lần xóa gửi một yêu cầu đọc mới, trả 2.598 nội dung, không lỗi JavaScript. Bằng chứng trước/sau: `reports/filter-reset-before.json` và `reports/filter-reset-after.json`. Không gọi API phân loại hoặc chạy crawl trong kiểm chứng này.

## Bảng

**Nguồn | Nội dung | Ngày đăng | Dự án | Nhóm vấn đề (taxonomy) | Ý định nội dung | Kết quả phân loại | Trạng thái xử lý | Đánh giá | Ghi chú**

Có thêm checkbox chọn nội dung. Tên nhóm vấn đề được ánh xạ từ `analysis.issues[].issue_id` qua danh mục taxonomy; phần tóm tắt không thay cho tên nhóm. Dự án trong cột kết quả lấy từ `analysis.project_matches`, độc lập với phạm vi dự án theo nguồn dùng để tìm kiếm.

Nội dung chưa có kết quả để nhóm vấn đề/dự án/ý định là “Chưa xác định”; trạng thái xử lý nói rõ đang chờ, thiếu đầu vào hay lỗi. Không suy ra nhãn model từ tên group hoặc scope nguồn. Rule loại nội dung được ghi rõ “Bộ lọc: loại”.

Mở nội dung để đọc đầy đủ bài/bình luận, ngữ cảnh, chữ OCR, nhóm vấn đề và lý do xử lý. Bảng desktop hỗ trợ cuộn ngang và focus bàn phím; mobile hiển thị nhãn nghiệp vụ trong từng nội dung.

## Sửa lỗi backend kèm theo

- `filter_options` do backend cung cấp danh mục ý định/trạng thái; backend kiểm tra giá trị, ID nguồn/dự án/nhóm vấn đề và bộ lọc không được hỗ trợ, trả lỗi rõ ràng thay vì bỏ qua.
- Sửa `SOURCE` trước đây chỉ xét bí danh, bỏ qua `project_context_ids` gắn với group. Scope hiện tại dùng cả nguồn và bí danh; không ghi đè project matches của model.
- Bộ đếm kết quả được tính sau điều kiện OCR, cùng phạm vi dữ liệu trả về. Bộ lọc kỹ thuật vẫn được hỗ trợ trong Kho dữ liệu và link cũ.
- Bảo vệ điều khiển khi khôi phục trang để thao tác xóa bộ lọc không bị request khôi phục cũ ghi đè.
- Excel giữ tóm tắt vấn đề, thêm tên nhóm taxonomy, ID nhóm và ý định tiếng Việt. Các cột OCR hiện có giữ vị trí; export dùng dữ liệu của phiên chốt, không lấy bản nháp chưa lưu.

## Kiểm chứng ngày 10/10/2026

- 255/255 kiểm thử hồi quy đạt; lượt kiểm tra cuối sau chỉnh bố cục gồm 14 kiểm thử contract/browser đạt. Không cộng lượt lặp thành test mới.
- Desktop/mobile trên dashboard thật: 11 cột (gồm checkbox), taxonomy hiển thị tên, không lỗi JavaScript hoặc tràn ngang toàn trang; mở nội dung đã phân loại từ tab Thu thập vẫn đọc được taxonomy.
- Dự án theo nguồn: VinCons 2.049 nội dung, trong đó 775 đang chờ; VinWonders Vũ Yên 549 nội dung, trong đó 373 đang chờ. Số liệu là tại thời điểm kiểm tra, không phải KPI phản ánh.
- Excel có taxonomy/ý định/trạng thái. SQLite `quick_check=ok`, 2.598 nội dung đã lưu; lịch crawl vẫn bật.
- Bằng chứng: `reports/reflections-live-validation.json`, `reports/ocr-test-result.json`, ảnh `reports/reflections-after-desktop.png` và `reports/reflections-after-mobile.png`.

Đây là nghiệm thu lọc/hiển thị dữ liệu đã lưu và thao tác giao diện. Độ chính xác model và khả năng lấy đủ dữ liệu trong window tiếp tục theo nghiệm thu acquisition/classification riêng.
