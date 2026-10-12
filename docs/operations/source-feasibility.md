# Feasibility matrix — 2026-10-08

> **Snapshot lịch sử theo ngày trong tài liệu.** Các trạng thái “chưa triển khai”, disabled hoặc lỗi probe chỉ áp dụng cho lượt kiểm tra đó. Đối chiếu code/config hiện hành ngày 11/10/2026 tại [trạng thái dự án](../current-state.md); không dùng snapshot này để kết luận runtime hiện tại.

Trạng thái mới nhất: Chromium của dự án đã chạy probe thật. Facebook group 1675953926771851 gặp LOGIN_REQUIRED; TikTok keyword CAPTCHA và hashtag LISTING_SELECTOR_MISMATCH; SerpApi trả INVALID_KEY sau một attempted request. [Probe evidence](acquisition-live-probes.json), [runbook](acquisition-runbook.md). Các kết quả Browser connector unavailable/key absent dưới đây là lịch sử giai đoạn trước, không phải trạng thái tài nguyên hiện tại.

Kết quả kiểm tra tài nguyên, không phải báo cáo crawl live. Không có navigation nền tảng, candidate hoặc coverage claim trong lượt này. Group config không bị tự bật/sửa name/access metadata.

| Task / mode | Kiểm tra đã thực hiện | Outcome / tài nguyên còn cần |
| --- | --- | --- |
| RES-01 Chromium | Cài browser tier; hai headless persistent contexts trên HTML local, tách profile; khóa và cleanup offline pass | LOCAL_SMOKE_PASSED; manual sign-in/session reuse trên nền tảng chưa kiểm chứng |
| RES-02 bảy Facebook groups | Khởi tạo Browser runtime, gọi getForUrl cho group 1675953926771851; đọc troubleshooting; discovery list trả [] | BROWSER_UNAVAILABLE, không xác nhận public/private của bất kỳ group nào; cần browser kết nối và access verification |
| FEAS-01 Facebook group | Không thể bắt đầu navigation do không có browser kết nối | BLOCKED tại resource gate; không gán ACCESS_DENIED cho group khi chưa thử truy cập |
| FEAS-02 TikTok keyword + hashtag | Chung browser gate chưa sẵn sàng; không dùng account-filter/Google làm thay thế | BLOCKED; cả hai UI mode chưa exercised |
| RES-03 / FEAS-03 Google | Kiểm tra boolean của SERPAPI_API_KEY trong environment và .env, không xuất value | false; BLOCKED do thiếu credential, 0 API requests; không có quota/error response giả |

Report chưa có source/query/window/item live evidence. Seed VinCons/#VinCons và quota ở specs là planned config, không là truy vấn đã chạy. Snapshot bảy nguồn vẫn 0 enabled/0 access_verified. Khi tài nguyên sẵn sàng, bổ sung window UTC cố định, native IDs, observed order, extracted field/missing reasons, source outcome và counts thực theo acceptance FEAS/VER-02.

Các phần không phụ thuộc live đã tiếp tục: BASE-01 contracts, BASE-02 characterization, BASE-03 structural refactor. CORE-01 đến CORE-07 và adapters mới tiếp tục theo TODO; browser preparation không tự đánh dấu các task đó complete.

Cập nhật sau kiểm tra công cụ: người dùng xác nhận cả bảy group public/truy cập được thủ công. Snapshot mới là 7 PUBLIC, 7 access_verified theo USER_MANUAL_CONFIRMATION, 0 enabled; cả bảy PENDING_VERIFICATION/requires_login=null. RES-02 chuyển IN_PROGRESS; FEAS-01 chưa có browser/adapter live evidence. Các số liệu 0 access_verified phía trên là lịch sử trước xác nhận này.
