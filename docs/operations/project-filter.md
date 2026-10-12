# Lọc theo dự án

Đồng bộ 11/10/2026: [projects.yaml](../../config/projects.yaml) có VinCons (`ORGANIZATION_PORTFOLIO`) và VinWonders Vũ Yên; 14 group enabled/VERIFIED, mỗi scope 7 nguồn. [Probe Vũ Yên ngày 09/10](../../reports/vinwonders-source-probes-20261009.json) là xác minh mẫu access/native item, không chứng minh full-window/complaint coverage.

1. Tab **Tìm link Google**: chọn scope để gợi ý keyword/hashtag; có thể thêm vấn đề. Search dùng SerpApi, query/snippet không chứng minh dự án hoặc thời gian đăng của native content.
2. Tab **Thu thập → Chạy ngay**: chọn scope để giới hạn 7 group tương ứng bằng Facebook raw v2; trống chọn tất cả 14 group bật. POST/COMMENT/REPLY lưu trước filter/classify, không cần keyword match.
3. **Lịch crawl** có lựa chọn dự án riêng, lưu cùng lịch. Chọn dự án rồi Bật/cập nhật lịch để áp dụng; chọn ở form chạy một lượt không tự đổi lịch đã lưu. Lịch cũ không có project_id tiếp tục chạy tất cả group đang bật. Hạn mức/thời gian run vẫn giữ nguyên; thêm nguồn có thể giảm coverage.
4. **Phản ánh / Kho dữ liệu**: bộ lọc dự án theo nguồn/alias giúp đọc nội dung chưa phân loại; vấn đề/intent/model fields là evidence/analysis riêng. [Bộ lọc Phản ánh](reflections-workspace.md) dùng `project_basis=SOURCE` trong UI hiện hành, không phải kết luận model. Backend còn hỗ trợ `MODEL`; [workspace](dashboard-workspace.md) giữ phiên bảng/Excel cùng phạm vi.

`MATCHED`: tên/bí danh/hashtag nằm trong title/caption/nội dung bài. `CONTEXT_ONLY`: chỉ nguồn group đã gắn dự án; hiển thị “theo group, chưa xác nhận”, không tạo project fact. `UNRESOLVED`: chưa có bằng chứng hoặc chưa đọc được nội dung. Query/snippet Google hoặc tên group không đủ để chuyển sang MATCHED. Bài nêu rõ dự án khác không bị ép vào dự án của group. Có thể giữ nhiều project matches trên cùng một item; không tạo bản ghi lặp.

Dictionary tại [projects.yaml](../../config/projects.yaml). Tên chuẩn và vị trí tham khảo [VinWonders](https://vinwonders.com/en/wonderpedia/news/vinwonders-vu-yen-hai-phong/). Bí danh gồm cách viết VinWonder/VinWonders và Vin Wonder/Vin Wonders Vũ Yên; “Vũ Yên”/“Royal Island” riêng lẻ không đủ. Chỉ thêm dự án với ID duy nhất, alias đủ đặc trưng, discovery_terms, hashtags và source_ids hợp lệ. Thêm group vào Source Registry/watchlist, kiểm chứng public/access rồi bật; không chỉ sửa source_ids dự án.

Rule chung loại chào bán/đặt vé/đại lý vé rõ intent; refund/access/scam complaints giữ REVIEW. Classifier Gemini và OCR POST đã nối raw v2, còn accuracy/full PF acceptance chưa nghiệm thu. Chưa ASR/video hoặc OCR ảnh COMMENT/REPLY. Trong raw v2, DROP không xóa raw; v1 prefilter vẫn audit-only.

Không cần migrate hay ghi lại raw records để lọc kho: project labels tính từ evidence hiện có. Đánh giá/ghi chú và identity được giữ. Kiểm thử: `tests.contract.test_projects`; UI fixture local: `tests.integration.test_project_dashboard` với `ACQUISITION_BROWSER_TESTS=1`.
