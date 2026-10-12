# OCR ảnh Facebook trong kho raw v2

Luồng hiện tại: lưu caption/comment/reply → nhận diện ảnh thuộc bài → đọc chữ bằng Tesseract → lưu evidence riêng → filter/classify. Caption, ngày đăng và identity của node giữ nguyên. Không OCR ảnh comment/reply, video, avatar hoặc ảnh của shared story trong phiên bản này.

## Chạy và kiểm tra

```powershell
Set-Location 'D:\task\social_listening\social_media_scraping'
uv pip install --python .venv\audit\Scripts\python.exe -r requirements-ocr.txt
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.image_ocr_cli --probe
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.dashboard
```

Engine local tại `.venv/tesseract/tesseract.exe`, traineddata `vie` và `eng` trong `tessdata/`. Có thể chỉ định `TESSERACT_CMD` và `TESSDATA_PREFIX` nếu dùng nơi khác. `FACEBOOK_OCR_ENABLED=true` là mặc định; đặt `false` để tắt enrichment. OCR không cần API key.

Máy dự án đã có Tesseract `5.5.3.20260724`, pytesseract `0.3.13`, Pillow `12.3.0`. Binary được giải nén vào thư mục riêng, không cần thay PATH hay cài vào Program Files. Nguồn: [Tesseract Windows](https://github.com/UB-Mannheim/tesseract/wiki), [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast), [pytesseract](https://pypi.org/project/pytesseract/).

SHA256 traineddata hiện dùng:

- vie: `79df64caf7bcfb2a27df5042ecb6121e196eada34da774956995747636d5bfa1`
- eng: `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`

Thu lại ảnh và OCR của một bài đã lưu:

```powershell
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.image_ocr_cli --node-id <ID-bai-viet> --seconds 90 --report reports\ocr-one-post.json
```

CLI mở lại đúng permalink của nguồn đủ điều kiện, làm mới media references rồi OCR. Không tự OCR toàn kho khi khởi động. Batch reprocess và nút reprocess trên giao diện chưa triển khai.

## Giới hạn và dữ liệu

- Tối đa 3 ảnh/bài; 50 ảnh/lượt dashboard crawl (chia sẻ giữa các source). Worker CLI đơn lẻ áp dụng 50 ảnh/task.
- 8 MB/ảnh, 20 megapixel; host HTTPS `*.fbcdn.net`; redirect cũng phải qua kiểm tra. Cookies dùng trong bộ nhớ, không lưu trong evidence hoặc log.
- Tải ảnh tối đa 15 giây, OCR tối đa 20 giây/ảnh; nằm trong budget thread/source. Thread có ảnh dành một phần budget cho OCR sau scan comments. Hết budget báo PARTIAL, giữ dữ liệu đã thu.
- Không giữ file ảnh lâu dài; decode trong bộ nhớ. Không dùng full-page screenshot làm input OCR.
- Caption có intent thương mại/tuyển dụng rõ DROP: giữ raw v2, bỏ enrichment ảnh. Nội dung OCR không tự xóa bài; intent đáng loại hoặc OCR yếu chuyển REVIEW.
- `image_evidence` lưu kết quả bất biến; `node_image_evidence` giữ pointer hiện tại theo node/ảnh. Ảnh trùng hash và engine/traineddata/config trùng được dùng lại OCR; tải lại ảnh để xác minh hash. Refresh ảnh lỗi không xóa evidence thành công trước đó.
- Evidence gồm text, trạng thái, chất lượng, hash ảnh, kích thước, engine/traineddata/config, word boxes/confidence và thời gian UTC. Confidence là điểm nhận diện chữ, không phải độ tin cậy nghiệp vụ.
- Hình/config/OCR thay đổi làm job classification cũ hết hiệu lực qua evidence binding; không đổi caption hoặc tạo post trùng. Context OCR của bài cha cũng làm job của comment cần cập nhật.
- Request classifier bổ sung `image_evidence` tùy chọn, phân biệt TARGET và ROOT_POST/PARENT_COMMENT. Model phải trích dẫn đúng evidence ID/quote; OCR yếu yêu cầu review. Schema request/result vẫn tương thích record/job cũ không có OCR.

## Xem và xuất

Trong chi tiết nội dung, mở **Chữ trong ảnh** để xem text/trạng thái từng ảnh. Bộ lọc bổ sung có **Chữ trong ảnh**; keyword tìm cả caption và OCR. Kết quả thuộc cùng phiên view đã chốt, cần Làm mới để nhận enrichment mới.

Excel có ba cột OCR bổ sung và sheet **Chữ trong ảnh**. Text dài được chia thành nhiều phần trên sheet này, không mất phần vượt giới hạn ô. Formula injection được xử lý như export hiện có. Bản xuất không lưu cookies hoặc API keys; URL ảnh có thể hết hạn.

## Kết quả kiểm chứng 10/10/2026

- Kiểm thử local Tesseract trên ảnh chữ Việt tự tạo; Chromium fixtures xác nhận post/comment mở rộng, link text, không lẫn shared-story photo; cache/ownership/stale jobs/filter/Excel được kiểm chứng offline.
- Pilot browser Facebook thật: bài Suối Khoáng Mỹ Lâm đọc được 17 comment/reply quan sát; một permalink khác CONTENT_UNAVAILABLE; không tuyên bố exhaustive coverage.
- Bài `2162101618523183` trong group `1280258833374137`: giữ caption 474 ký tự, nhận diện 5 ảnh, xử lý 3; OCR text lần lượt 465/139/437 ký tự. Một ảnh ACCEPTABLE, hai ảnh NEEDS_REVIEW. Album PARTIAL vì giới hạn 3 ảnh.
- Pilot gửi Gemini cho đúng một bài được người dùng xác nhận riêng: ba lần thử đều HTTP 503, job FAILED sau giới hạn retry. Input caption + 3 OCR đã qua validation; chưa có output live hợp lệ hoặc node_analyses cho binding mới. Theo dõi `reports/ocr-classification-live-pilot.json`; thử lại bằng nút đưa lỗi về hàng chờ khi provider hồi phục.

Không dùng các kiểm thử trên để khẳng định chất lượng OCR toàn bộ group hoặc đã đọc hết comments. Cần tập ảnh đối chứng 30–50 ảnh và reviewer nghiệm thu trước khi kết luận độ chính xác/false drop.

Regression/API/UI evidence: `reports/ocr-test-result.json`, `reports/ocr-full-tests.log`, `reports/ocr-browser-review.json`, `reports/ocr-implementation-validation.json`.

Nghi?m thu regression cu?i: **249/249 PASS**, kh?ng skip; UI desktop/mobile kh?ng l?i JavaScript ho?c tr?n ngang. Config acquisition VALID; SQLite quick_check OK v? foreign_key_check kh?ng l?i. L?ch h?ng ng?y 05:00?08:30, 17:00?18:30, chu k? 45 ph?t gi? nguy?n.
