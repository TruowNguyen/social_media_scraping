# Kiểm tra nội dung chưa phân loại — 10/10/2026

## Kết quả

Dashboard đã tách **Nguồn** (tên và link group, gồm mọi nguồn đã ghi nhận) khỏi **Nội dung** (bài/bình luận, tác giả và link URL). Áp dụng cho Phản ánh và Kho dữ liệu; trên điện thoại hai phần được ghi nhãn riêng.

Tại thời điểm kiểm tra có 2.598 nội dung. Nhãn “Chưa phân loại” cũ gộp cả dữ liệu chưa vào hàng chờ, kết quả không còn hiệu lực và dữ liệu chưa có văn bản. Đây không phải một quyết định nghiệp vụ của model.

Kiểm tra trước đối soát:

- 1.446 nội dung hiển thị chưa phân loại; trong đó 298 thiếu văn bản/OCR và 1.148 có đầu vào cần kiểm tra hàng chờ.
- Trong nhóm chưa phân loại: 721 chưa từng có job; các job cũ bị thay đổi văn bản đích (136), ngữ cảnh (590), hoặc chữ OCR (185). Các nguyên nhân thay đổi có thể trùng nhau; không cộng thành tổng.
- 27 job hiện tại bị lỗi: 15 kết quả mâu thuẫn giữa nhãn phản ánh và quyết định loại, 11 lỗi HTTP, 1 response envelope không hợp lệ. Một job khác đang chờ thử lại sau lỗi API tạm thời.
- Chỉ có 3 đánh giá của người dùng đã lưu: 1 liên quan, 2 không liên quan. Không phát hiện xung đột trực tiếp với quyết định loại trong các đánh giá này; mẫu quá nhỏ để đánh giá độ chính xác phân loại tổng thể.

## Điều chỉnh

- `MISSING_TEXT`: thiếu caption/comment/OCR; không tính là nội dung đủ điều kiện gửi model.
- `STALE`: có job trước nhưng đầu vào hoặc cấu hình không còn tương ứng; giữ kết quả lịch sử, không dùng làm kết quả hiện tại.
- `UNCLASSIFIED`: có nội dung nhưng chưa có job hiện tại.
- `PENDING`, `FAILED`, `OVERSIZED`: hiển thị nguyên nhân xử lý bằng tiếng Việt, tách khỏi relevance của model.
- Prompt nhắc rõ không kết hợp `COMPLAINT` với `DROP`; trường hợp không xác nhận được dự án/vấn đề phải `REVIEW`. Validator vẫn từ chối kết quả mâu thuẫn; chưa xác nhận hiệu quả prompt bằng API thật.
- Job lỗi cuối cùng không mang thời điểm tự thử lại. Người dùng phải đưa lỗi về hàng chờ qua hành động retry riêng.

Đã sao lưu database bằng SQLite backup rồi đối soát tại chỗ, bổ sung 1.147 job. Không gọi model hoặc sửa đánh giá của người dùng. Sau đối soát:

| Trạng thái hiện tại | Số nội dung |
| --- | ---: |
| Hoàn thành | 983 |
| Đang chờ | 1.148 |
| Thiếu văn bản/OCR | 298 |
| Bộ lọc loại | 142 |
| Lỗi phân loại | 27 |

## Vận hành

Chuẩn bị hàng chờ riêng, không gọi API:

```powershell
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.classification_worker --prepare-only --report reports/classification-queue-reconciliation.json
```

Lệnh idempotent: chỉ bổ sung binding mới, không phân loại lại kết quả còn hiệu lực. `--prepare-only` không dùng cùng `--serve` hoặc `--results`. Nút **Xử lý hàng chờ** vẫn chạy một lượt tối đa 10 nội dung. Chuẩn bị hàng chờ không đồng nghĩa model đã hoàn thành phân loại.

Kiểm tra gateway bằng câu thử không có dữ liệu khách hàng vẫn trả **HTTP 503**. Không gửi hàng loạt caption/comment/OCR trong lần kiểm tra này. Cần khôi phục tuyến model trước khi nghiệm thu độ chính xác phân loại thật.

## Kiểm chứng

- 252/252 kiểm thử đạt, gồm Chromium và Tesseract thật; model trong kiểm thử tự động là fixture.
- Dashboard thật desktop/mobile: hai phần nguồn/nội dung tách rõ, 8 cột trên bảng, không có lỗi JavaScript hoặc tràn ngang trang.
- SQLite `quick_check=ok`; lịch crawl vẫn bật.
- Bằng chứng: `reports/classification-miss-audit.json`, `reports/classification-queue-reconciliation.json`, `reports/source-columns-classification-validation.json`.

Chưa thể đánh giá recall/precision trên toàn bộ các “case rõ ràng” khi API phân loại vẫn lỗi. Dữ liệu thiếu văn bản cần thu thập lại; nội dung còn trong hàng chờ chưa được coi là đã lọc đúng hay sai.
