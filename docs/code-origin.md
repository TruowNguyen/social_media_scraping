# Nguồn gốc code

Repository `TruowNguyen/social_media_scraping` là repository độc lập do `TruowNguyen` quản lý. Bộ collector và pipeline ban đầu được phát triển từ [ashkanchaji/social_media_scraping](https://github.com/ashkanchaji/social_media_scraping), tác giả lịch sử là `ashkanchaji`. Commit nguồn `929aef1` có trailer đồng tác giả `Claude Opus 5`; đây là thông tin của lịch sử nguồn, không phải collaborator hoặc quyền quản trị repo hiện tại.

Phần mở rộng của dự án gồm refactor `engine → src`, Source Registry, acquisition Facebook/Threads, lưu hội thoại raw, OCR ảnh Facebook, taxonomy theo dự án, Gemini batching, lịch crawl và dashboard. Chi tiết triển khai, kết quả kiểm chứng và phần chưa nghiệm thu ở [TODO](../TODO.MD) và [bàn giao dev](development-handoff-20261012.md).

Ngày 12/10/2026, theo yêu cầu của chủ repository, lịch sử Git hiện hành được khởi tạo lại từ snapshot code đã triển khai, sau đó repository được xóa và tạo lại cùng tên. Root commit ghi người tạo snapshot là `TruowNguyen`; việc này không thay đổi nguồn gốc những thành phần kế thừa. Backup lịch sử trước khi khởi tạo lại và trước khi tạo lại repository được giữ local, không publish lên repository.
