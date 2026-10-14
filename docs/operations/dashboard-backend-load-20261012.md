# Dashboard bị chậm / không đọc được trạng thái — 12/10/2026

Trạng thái: **IMPLEMENTED / OFFLINE_VERIFIED / LIVE_API_UI_VERIFIED**.

## Nguyên nhân quan sát được

- Dashboard vẫn lắng nghe cổng 8765 nhưng `/api/health` timeout sau 12 giây; `/api/jobs/active` có lần mất 7,4 giây. Tiến trình dashboard dùng khoảng 2 GB RAM.
- Giao diện kiểm tra mỗi 15 giây: đọc trạng thái rồi gọi `/api/views` để xem có dữ liệu mới. Việc kiểm tra này dựng toàn bộ tập kết quả, đối chiếu raw/OCR/lịch sử phân loại và có thể ghi snapshot dù người dùng chưa yêu cầu cập nhật bảng.
- Backend giữ các hàng job lịch sử kèm taxonomy binding lớn và cho các request đọc nặng chạy đồng thời. Snapshot trong RAM được giữ tới 32 key. Trên database thật: khoảng 3.400 nội dung, 7.300 job lịch sử; 128 snapshot lưu khoảng 800 MB. Job lịch sử không tương đương số nội dung hiện tại.
- Hai dashboard được mở cùng cổng trên Windows. Trước bản sửa, services/schedulers khởi động trước khi kiểm tra cổng; các tiến trình có thể cạnh tranh profile và task.
- Sau restore URL, `markEditing` tính khi form còn disabled, để lại thông báo giả “Chưa áp dụng thay đổi”, khiến kiểm tra dữ liệu mới bị bỏ qua.

## Thay đổi đã áp dụng

1. Đọc job theo luồng, chỉ giữ trạng thái của job hợp lệ mới nhất cho từng node; giữ kiểm tra taxonomy, revision, context, OCR và identity. Lịch sử vẫn ở database.
2. Giới hạn một lần dựng bảng/thống kê nặng trong mỗi dashboard; request cạnh tranh nhận `503 READ_BUSY` trong khoảng một giây thay vì xếp thêm các lần dựng lớn. Các API nhẹ vẫn phản hồi. Cache bảng tối đa bốn key.
3. Cache thống kê phân loại 15 giây theo generation; vô hiệu khi số node, thời điểm thấy dữ liệu hoặc thống kê job thay đổi. `counts_as_of` ghi thời điểm tính. Heartbeat, schedule và source outcome vẫn được đọc lại.
4. `/api/health` bỏ raw thread content khỏi báo cáo nguồn và bỏ danh sách rows khỏi active job; giữ trạng thái, lỗi và coverage cần cho giao diện.
5. Thêm `/api/views/version`: đọc các marker dữ liệu, trả version hash và thời điểm đọc. Polling không gọi classifier và không tạo snapshot. Người dùng bấm cập nhật/làm mới mới dựng bảng. Marker áp dụng toàn kho, nên thông báo có cập nhật không khẳng định bộ lọc hiện tại sẽ có thêm dòng.
6. Chiếm cổng độc quyền trước khi tạo service/scheduler; chạy trùng dừng với exit code 2. Đã retire hai dashboard cũ sau khi giải phóng profile và khởi động một dashboard mới. Worker phân loại riêng tiếp tục hoạt động.
7. Tính lại trạng thái form sau khi restore xong; reload giữ bộ lọc đã áp dụng và không báo thay đổi giả.

## Kết quả kiểm chứng

60 kiểm thử dashboard/raw/classifier/view/Chromium đạt. Chromium desktop/mobile xác nhận polling chỉ gọi `/api/views/version`, không gọi `/api/views` để dựng lại snapshot; hồi quy 404/reconnect/409, bộ lọc, nháp và Excel đạt.

| API trên database thật | Thời gian đo | HTTP |
| --- | --- | --- |
| `/api/jobs/active` | 0,055 giây | 200 |
| `/api/views/version` | 0,153–0,257 giây; 124 byte | 200 |
| `/api/health` lần tính thống kê | 1,423 giây | 200 |
| `/api/health` dùng cache | 0,241 giây | 200 |
| Bảng phản ánh, 25 dòng / tập 3.435 node | 2,629 giây | 200 |

Thử năm request đồng thời: một bảng hoàn thành trong 3,481 giây; bảng cạnh tranh nhận `READ_BUSY` sau 1,164 giây; version/catalog/active vẫn trả 200 trong 0,143–0,463 giây. Kiểm tra mở dashboard thứ hai bị chặn trước khi tạo scheduler. RAM sau triển khai khoảng 194 MB tại thời điểm đo; đây là snapshot, không phải cam kết mức RAM tối đa.

Giao diện thật sau reload đọc được trạng thái và giữ khoảng ngày 10–12/10, kết quả REVIEW; không còn thông báo lỗi hoặc thay đổi bộ lọc giả. [Ảnh kiểm chứng local](../../reports/dashboard-backend-load-recovered-20261012.png). Logs kiểm thử và runtime trong `reports/` được ignore.

## Phần còn mở

Việc dựng bảng lần đầu vẫn đối chiếu tập raw trong Python; phân trang hiện tại diễn ra sau khi dựng tập kết quả. Bước tiếp theo khi quy mô tăng: bảng dữ liệu đọc đã chuẩn hóa / trạng thái phân loại hiện hành, truy vấn và phân trang SQL, tổng hợp số liệu bởi worker; kiểm chứng nhiều client và theo dõi RAM/độ trễ dài hạn. Chưa thay SQLite hoặc xóa raw/reviews/snapshot đang còn hạn trong đợt xử lý này. Kết quả hiệu năng không chứng minh full crawl coverage hoặc chất lượng phân loại.
