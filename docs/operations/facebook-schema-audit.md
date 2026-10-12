# Đối chiếu Facebook parser và schema — 09/10/2026

> **Snapshot lịch sử theo ngày trong tài liệu.** Các trạng thái “chưa triển khai”, disabled hoặc lỗi probe chỉ áp dụng cho lượt kiểm tra đó. Đối chiếu code/config hiện hành ngày 11/10/2026 tại [trạng thái dự án](../current-state.md); không dùng snapshot này để kết luận runtime hiện tại.

**Cập nhật kiểm tra lại:** [truy vết mới nhất](facebook-root-cause-recheck.md) cho thấy sau khi lưu phiên, cùng permalink đã đọc được caption/thời gian. Đã sửa phạm vi comment popup/nested dialog. Kết luận không khả dụng dưới đây là ảnh chụp tại thời điểm kiểm tra cũ, không phải trạng thái hiện tại.

## Kết luận

Lỗi pilot `LISTING_SELECTOR_MISMATCH` không xuất phát từ validator schema. Browser thật hiển thị thông báo **“Bạn hiện không xem được nội dung này”** cho permalink `987006180721696` thuộc group `139108668844789`. Không xác nhận bài đã xóa hay cả group không truy cập được. [Ảnh trang thực tế](../../reports/p2-facebook-schema-recheck.png), [bộ đếm DOM](../../reports/p2-facebook-schema-recheck-live.json).

Lỗi ban đầu nằm ở access detector chỉ đọc heading/alert, trong khi thông báo này nằm trong text thông thường. Vì chưa nhận diện trạng thái đó, `wait_listing` tiếp tục tìm selector và phát lỗi parser. Sau sửa, [pilot chạy lại](../../reports/p2-facebook-schema-recheck-outcome.json) trả `SOURCE_UNAVAILABLE / CONTENT_UNAVAILABLE`; caption/comment vẫn chưa lấy được từ permalink này.

## Đối chiếu và sửa

| Lớp | Đối chiếu | Kết quả |
| --- | --- | --- |
| Access outcome | Bài không khả dụng khác parser mismatch, khác không có comment | Thêm nhận diện exact visible notice; tránh match text trong article |
| Browser → candidate v1 | Caption có thể tồn tại khi published_at chưa biết | Sửa Story parser bỏ điều kiện bắt buộc epoch; conflicting timestamps giữ null/UNKNOWN |
| Candidate → conversation v2 | `facebook` → `FACEBOOK`, native ID/UTC/nullable/POST mapping | Mapping có chủ đích, khác version không phải conflict; Chromium round-trip caption thiếu timestamp pass |
| Raw → classifier request v2 | Text riêng target; root/parent có revision/evidence; timestamp không bắt buộc trong request LLM | Input builder + strict validator pass; không dùng thời gian thu thập giả làm ngày đăng |
| Evidence | Không có timestamp không được gán native publication-time evidence | Sửa fetch để chỉ giữ provenance thật từ metadata |
| Raw access state | Bài không đọc được không được mặc định AVAILABLE | Thread adapter error ghi FAILED + error reason + UNAVAILABLE/UNKNOWN; giữ raw đã thu trước đó, không gán DELETED_CONFIRMED |
| Load timing | Hydration có thể đến sau DOMContentLoaded | Chờ listing/data trước đọc Story trên permalink; không sửa schema để bù dữ liệu không hiện |

Các schema candidate/raw/classifier có mục đích khác nhau; không đưa payload candidate nguyên trạng vào request LLM. Storage/UI/API đầy đủ vẫn theo các phase còn lại; audit này không xác nhận toàn target contract đã triển khai.

## Nghiệm thu

- Chromium integration: 9 tests pass, gồm post/comment ownership, timestamp conflict/missing, candidate → raw → classifier round-trip, unavailable notice và nội dung article không bị nhận nhầm thành màn hình lỗi.
- Contract regression cuối: **166 tests pass**, gồm hai test mới xác minh lưu đúng trạng thái lỗi và giữ caption cũ. [Report audit](../../reports/facebook-schema-audit.json).
- Native pilot hiện chưa đạt acquisition coverage; cần permalink khác thực sự hiển thị trong phiên crawler để nghiệm thu caption/comment. Đổi schema không khôi phục nội dung mà Facebook không cung cấp.
