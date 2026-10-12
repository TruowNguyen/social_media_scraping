# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Người dùng vận hành social listening của dự án: chọn nguồn/query và khoảng thời gian, kiểm tra nội dung thu được, xem phân loại, đánh giá và ghi chú, xuất Excel. Yêu cầu đã xác nhận trong cuộc hội thoại dự án; không giả định thêm role hoặc phân quyền doanh nghiệp.

## Product Purpose

Thu thập và lưu nội dung mạng xã hội trước, sau đó lọc và phân loại phản ánh theo taxonomy của từng dự án. Hai scope đã xác nhận là VinCons và VinWonders Vũ Yên. Thành công phải có dữ liệu/thời gian/nguồn truy vết được và giới hạn thu thập rõ ràng.

## Operating Context

Dashboard web local chạy bằng Python trên Windows, giao diện tiếng Việt. Lịch người dùng đã chọn: 05:00–08:30 và 17:00–18:30 mỗi ngày, chu kỳ cố định 45 phút. Người dùng xem bảng, hội thoại, đánh giá, ghi chú và Excel.

## Capabilities and Constraints

- Runtime Facebook có POST/COMMENT/REPLY, raw revisions/observations, OCR ảnh POST, batch Gemini, review và export. Coverage Facebook còn partial; không gọi số thu được là toàn bộ dữ liệu nền tảng.
- Threads đã triển khai subset browser Playwright + Chrome, tìm theo truy vấn dự án, thu POST/REPLY và lưu vào kho chung. Pilot có dữ liệu thật; coverage/nested parent chưa nghiệm thu đầy đủ. Provider API và OCR Threads chưa live-verified. Target theo dự án/query đã duyệt, không mặc định topic rộng.
- Người dùng xác nhận ngày 11/10/2026: dùng chung tab **Thu thập**, chọn Facebook hoặc Threads ở đầu màn hình; cấu hình/lượt chạy/lịch của hai nền tảng độc lập. Kho dữ liệu và Phản ánh dùng chung với platform filter.
- Raw lưu trước filter/classify; không xóa raw khi analysis DROP. Mỗi reply có ngày đăng/identity riêng, parent cũ vẫn là context.
- SQLite chung có identity theo nền tảng, reader mixed v2/v3, observations/revisions và writes bằng transaction ngắn. Threads có durable ingest pages, lease/profile riêng và lịch nhiều dự án chạy tuần tự. Facebook và Threads có lịch/lượt độc lập; cần dashboard đang chạy để lập lịch hoạt động.

## Evidence on Hand

[Trạng thái hiện hành](docs/current-state.md), [runbook Threads](docs/operations/threads-acquisition.md), [UI và kiểm chứng 12/10](docs/operations/workspace-platforms-20261012.md), [kế hoạch Threads](docs/implementation-plan-threads.md), [feature spec](specs/features/threads-adapter.md), [conversation contract](specs/contracts/multi-platform-conversations.md). UI ở `engine/dashboard_workspace.html`, `.css`, `.js` và `dashboard_threads.js`, đã quan sát trực tiếp trong Chrome. Số liệu live là snapshot có ngày; không chứng minh recall/accuracy hoặc trạng thái hiện tại của phiên/API. Reports/database/profiles là artifacts local, không đi cùng checkout GitHub.

## Product Principles

- Xác định scope bằng dự án/query, xác định phản ánh bằng evidence và taxonomy.
- Tách đã thu, đã lưu, đã phân loại và người dùng đánh giá; không dùng một nhãn thay tất cả.
- Giữ nội dung/ngữ cảnh/lịch sử, dedup theo identity nền tảng.
- Tách ngày đăng và ngày thu thập; hiển thị thiếu dữ liệu và coverage trung thực.
- Cấu hình và lỗi một nền tảng không gây dừng nền tảng kia.

## Open Decisions

Threads API, exact topic tags, nested parent, coverage toàn window và hiệu quả truy vấn còn chờ nghiệm thu. Query VinCons có kết quả nhiễu như “Vincent”, cần đối chứng relevance; số nội dung tìm được không phải số phản ánh. Tên/alias công trường VinCons cụ thể cần người dùng bổ sung trước khi target. Không đặt thêm brand claims, customer metrics hoặc deployment promises.
