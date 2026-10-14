# Vận hành thu thập Threads

**Cập nhật VinCons 13/10:** parser v5 xác minh query/vùng search, scope gate sau commit raw, bảy query VinCons và giới hạn hội thoại thiếu evidence. Các kết quả v4 bên dưới là lịch sử; xem [đối chiếu hiện hành](threads-vincons-scope-20261013.md). Lịch thực đọc từ backend; tự khởi động/chạy bù hiện theo [local runtime](local-runtime-recovery.md).

Cập nhật **12/10/2026 · IMPLEMENTED / OFFLINE_VERIFIED / LIVE_PARTIAL**. Pilot dùng **Playwright Python + Chrome**, profile riêng `sessions/browser/threads`. Không dùng Threads API trong các kết quả live bên dưới. Đã áp dụng [Impeccable](../../.agents/skills/impeccable/SKILL.md) để mở rộng giao diện hiện có, kiểm chứng trực tiếp và không dùng agent phụ.

## Luồng đã chạy

Trong tab **Thu thập**, chọn **Threads**, dự án, truy vấn, thời gian và phạm vi bài viết hoặc bài viết + trả lời. Hệ thống tìm kiếm Mới đây → mở hội thoại → ghi trang vào hàng chờ bền vững → commit raw, observations và checkpoint → bộ lọc → Gemini theo batch. Kho dữ liệu và Phản ánh dùng chung database với Facebook, có bộ lọc **Nền tảng** và **Nguồn / truy vấn**. Đọc bảng, xem chi tiết và export không gọi crawler hoặc Gemini.

Một nội dung có một identity theo nền tảng và native ID, hoặc URL nếu chưa có native ID. Shortcode không được coi là native ID. Gặp lại nội dung tạo observation; chỉ thay đổi nội dung, evidence hoặc ngữ cảnh mới tạo revision. URL ảnh CDN đổi chữ ký và thiếu tạm thời mô tả ảnh không làm phân loại lại. Hai trường hợp chưa chứng minh được bài gốc được giữ với `UNRESOLVED_ROOT`; không ghép trả lời làm bài gốc.

## Kết quả pilot thật

| Hạng mục | Kết quả / bằng chứng |
| --- | --- |
| Provider | `THREADS_BROWSER`, phiên đăng nhập do người dùng hoàn tất |
| Truy vấn | `threads_vwy_name` · `VinWonders Vũ Yên` |
| Window cố định | UTC `[2026-09-27 16:31, 2026-10-11 16:31)`; Việt Nam `[27/09 23:31, 11/10 23:31)` |
| Lượt chạy từ giao diện | `threads_ddeda69648d6461cb98f0835eade5f0a`; [report](../../reports/threads-production-live-run.json) |
| Kho sau các lượt đối chiếu | 43 nội dung Threads: 4 bài viết, 39 trả lời; không phải 43 phản ánh độc lập |
| Thời gian/văn bản | 43/43 có văn bản và timestamp đăng; việc đọc được không chứng minh relevance |
| Tái chạy | [reuse confirmation](../../reports/threads-production-reuse-confirmation.json): 42 nội dung thấy lại, 0 nội dung mới, 0 revision mới |
| Parser cuối | `threads-dom-v4`: loại thời gian/nút dịch/composer khỏi caption bằng cấu trúc DOM; [live report](../../reports/threads-production-parser-v4.json) |
| Phân loại | 42 DONE Gemini + 1 FILTER_DROP, không còn hàng chờ/lỗi; 11 KEEP, 2 REVIEW, 30 loại (29 model + 1 rule). [Snapshot](../../reports/threads-deployment-final.json) |
| Facebook | 3.070 nội dung trước pilot được giữ; có backup trước nâng schema và đối soát fingerprint |

Lượt sau có thể thấy ít hơn lượt trước do thứ tự tìm kiếm, lazy loading và giới hạn scroll; hệ thống giữ nội dung đã lưu. Các lượt browser ghi **PARTIAL**, `full_window_coverage_verified=false`, `DOM_PARENT_MAPPING_UNVERIFIED`. Chưa nghiệm thu thu hết mọi bài trong khoảng thời gian hoặc mọi trả lời lồng nhau. Chưa có precision/recall được reviewer xác nhận; nhiều KEEP có thể là các phần/trả lời trong cùng một hội thoại.

Đánh giá output hiện hành: trong 4 bài viết, model giữ 1 và loại 3. Cả 11 nội dung KEEP thuộc **một hội thoại đã biết**, gồm bài gốc và các phần/trả lời; không báo cáo thành 11 phản ánh độc lập. Một phản ánh trải nghiệm công viên được nhận diện; các bài thương mại/thông tin khác đã bị loại ở bước xử lý, raw vẫn giữ để kiểm tra. Pilot chứng minh luồng thu–lưu–lọc–phân loại chạy được, chưa chứng minh recall của Threads hoặc chất lượng trên mọi truy vấn dự án.

Lịch pilot ban đầu bật cho VinWonders Vũ Yên. Ngày 12/10 đã cập nhật giao diện và lưu lịch **VinCons + VinWonders Vũ Yên**, chạy tuần tự, giữ hai ca/45 phút và trạng thái bật; Snapshot mới đã có dữ liệu qua truy vấn VinCons; chưa nghiệm thu tính liên quan/coverage. Dashboard và Gemini worker đang chạy. [Cập nhật và kiểm chứng](workspace-platforms-20261012.md). [Excel 43 dòng](../../reports/threads-live-results.xlsx) đã đối soát: Group để trống với Threads, có Nguồn / truy vấn, Nền tảng và ID nguồn. [Ảnh pilot](../../reports/threads-workspace-live.jpg).

## Cách chạy

```powershell
Set-Location 'D:\task\social_listening\social_media_scraping'
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.acquisition_cli validate
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.dashboard
```

Mở `http://127.0.0.1:8765`, **Thu thập → Threads**. Các phần Chạy ngay, Lịch tự động, Lịch sử và Nguồn theo dõi hoạt động độc lập với Facebook. **Kho dữ liệu → Nền tảng: Threads → Áp dụng** để xem toàn bộ raw; **Phản ánh** để lọc quyết định, taxonomy và ý định. Nút **Xem dữ liệu lượt này** lọc theo run ID. **Xuất Excel** dùng đúng phiên kết quả đang xem.

Khi phiên hết hạn, dừng lượt và mở đăng nhập thủ công. Dùng Chrome đã cài với profile riêng; không lấy cookie từ Chrome cá nhân hoặc gửi cookie qua chat.

```powershell
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.browser_session --platform threads --login --channel chrome
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.threads_cli probe --query-id threads_vwy_name --report reports/threads-access.json
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.threads_cli run --query-id threads_vwy_name --start 2026-09-27T16:31:00Z --end 2026-10-11T16:31:00Z --max-candidates 12 --max-pages 5 --seconds 180 --report reports/threads-manual.json
```

CLI nhận timestamp UTC có timezone; giao diện nhận giờ Việt Nam. `--pilot` dành cho kiểm chứng capability khi platform chưa bật, không vượt query đang tắt. Không mở đồng thời cửa sổ đăng nhập và crawler cùng profile.

Classifier liên tục đã được người dùng cho phép; giữ kết quả DONE còn hợp lệ. Nếu cần khởi động riêng:

```powershell
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.classification_worker --serve --poll-seconds 15 --report reports/classifier-latest.json
```

## Lịch và tài nguyên

Lịch Threads chọn được nhiều dự án, hiện VinCons và VinWonders Vũ Yên; hai ca **05:00–08:30** và **17:00–18:30**, chu kỳ **45 phút**, thêm lượt đóng ca. Các mốc: `05:00, 05:45, 06:30, 07:15, 08:00, 08:30` và `17:00, 17:45, 18:30`. Đầu ca cập nhật inventory không tạo window giả; các lượt sau thu window tích lũy từ đầu ca đến mốc chạy và rescan bài đã biết để tìm trả lời mới. Khi khởi động muộn, catch-up các ca đã đến trong ngày hiện tại; chưa backfill tự động ngày đã bỏ lỡ. Mỗi dự án có lượt độc lập, chờ phiên Threads rảnh. Trạng thái bật/lượt tiếp theo đọc trong giao diện, không suy từ seed.

Dashboard cần chạy để scheduler sống; đóng terminal/service thì lịch không chạy. Khóa profile và lease Threads độc lập với Facebook; SQLite dùng WAL và transaction ngắn. Kiểm thử offline đã chạy hai producer và review writer; chưa nghiệm thu hai crawler mạng thật hoạt động đồng thời trong ba ngày.

Tài nguyên browser hiện đủ: Chrome, profile Threads đã đăng nhập, config query, SQLite và Gemini đang cấu hình. Không cần Threads API token để chạy provider hiện tại. Prototype `THREADS_API` có kiểm thử lỗi offline nhưng **chưa pilot**, vì chưa có `THREADS_ACCESS_TOKEN`; quyền đọc, trường trả về và quota thực phải kiểm chứng riêng. Không tự chuyển provider khi browser bị chặn.

## Phục hồi và giới hạn còn lại

Backup trước Threads: `sessions/backups/pre-threads-v3-20261011.sqlite3`. Không thay database đang chạy bằng backup v2 sau khi đã có nội dung Threads. Nếu rollback, dừng producer/worker, giữ bản mixed DB, khôi phục bản backup cùng phiên bản code tương ứng và đối soát IDs/reviews trước khi chạy.

Trang thu nằm tại `sessions/acquisition/ingest/acquisition/{ready,archive,dlq}`. ACK và checkpoint cùng transaction raw. Sau crash, trang đã commit replay receipt, không tạo dữ liệu trùng; trang trước thời điểm lease hết hạn được recovery, trang đến muộn bị chặn. Không xóa `ready` khi chưa đối soát; `recovery_error` trong acquisition catalog báo trang chưa commit. Facebook vẫn ghi qua repository trực tiếp: chưa chuyển toàn bộ crawler Facebook sang spool chung và chưa có daemon storage riêng.

Các phần chưa nghiệm thu: nested parent chính xác; bài cũ/trả lời mới có tập đối chứng live; toàn bộ aliases/VinCons/topic-tag; Threads OCR; provider API/hybrid; precision/recall held-out và theo dõi lịch ba ngày. Xem [TODO](../../TODO.MD) và [plan](../implementation-plan-threads.md) cho các gate còn mở.

Kiểm chứng: 251 contract tests (250 đạt, 1 opt-in skip), 2 browser parser tests và 2 desktop/mobile workspace tests đạt. Snapshot triển khai ghi thời điểm, số raw, kết quả phân loại hiện hành, schedule và bằng chứng live; không coi fixtures offline là live ACP.
