# Lịch crawl Facebook raw v2

Đối chiếu code/config ngày **11/10/2026**. Dashboard có bốn tab; lịch nằm trong **Thu thập → Lịch hằng ngày**. Route crawl thủ công và lịch cùng dùng `RAW_V2_THREADS`, không dùng Facebook acquisition v1. [Luồng raw v2](dashboard-raw-v2.md), [workspace](dashboard-workspace.md).

## Hai khung hằng ngày

UI DAILY_SLOTS mặc định hai khung giờ Việt Nam UTC+7 với chu kỳ 45 phút:

| Khung | Mốc bắt đầu lượt |
| --- | --- |
| 05:00–08:30 | 05:00:01, 05:45, 06:30, 07:15, 08:00, **08:30 (chốt)** |
| 17:00–18:30 | 17:00:01, 17:45, **18:30 (chốt)** |

Lượt chốt được thêm cả khi cuối khung không nằm trên grid 45 phút. Lượt mở khung của dashboard chờ 1 giây để window không rỗng; API dùng `final_tick=true` ở mốc đóng. Window mỗi job `[đầu khung, thời điểm chạy)`, end không vượt cuối khung; node đúng end chưa nằm trong window đó. Cutoff không mở rộng trong lúc browser chạy.

Lịch có schema `dashboard-schedule-v2`, record schema `conversation-record-v2`, loại node POST/COMMENT/REPLY và `storage_order=RAW_THEN_FILTER_CLASSIFY`. Task mới là `conversation-crawl-task-v2`. Startup chuyển lịch v1 sang v2, giữ trạng thái bật/tắt, khung/chu kỳ, project selection và next_run_at; task/report cũ resume theo payload đã lưu.

Snapshot file lịch local đọc ngày 11/10: enabled, DAILY_SLOTS, hai khung trên, min=max=45, project_id trống. Checkout mới không có file lịch vẫn khởi tạo disabled; không tự bật lịch chỉ vì đã có code. Xem trạng thái thực:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/schedule'
```

## Sử dụng và giới hạn

- **Chạy ngay** chọn phạm vi VinCons/VinWonders Vũ Yên hoặc tất cả và khoảng ngày; không tự đổi selection lịch đã lưu.
- **Bật / cập nhật lịch** lưu hai khung, chu kỳ và phạm vi. **Tắt lịch** ngăn lượt tiếp theo; lượt đang chạy được hoàn tất.
- Ngoài khung không bắt đầu lượt mới và không replay toàn bộ tick đã bỏ lỡ. Khi bận trong khung, lượt đến hạn chờ; qua khung chuyển sang mốc tiếp theo. Task raw đã tạo được resume bằng lease/checkpoint.
- Mỗi dashboard run tối đa 1.200 giây; mỗi source tối đa 120 giây và được chia theo budget còn lại, inventory tối đa 100 candidate/group, quét tối đa 20 thread/group. Kết quả có thể PARTIAL/UNKNOWN; không bảo đảm lấy hết feed/comments/replies.
- Group chỉ là context. Raw DROP vẫn lưu; ngày comment/reply xét riêng, không dùng intent/ngày bài cha để loại child.

Lịch lưu atomically ở `sessions/acquisition/dashboard-schedule.json`. `/api/crawl` khởi chạy Facebook raw v2, `/api/search` là Google/SerpApi discovery, `/api/jobs/active` giúp UI nhận lại job sau refresh. API giữ tương thích ROLLING/FIXED: ROLLING tính lookback tại lúc chạy; FIXED dùng khoảng ngày Việt Nam và dừng khi hết khoảng. UI hiện dùng DAILY_SLOTS; giá trị 30 phút/7 ngày của API mới chưa có lịch không phải lịch pilot đã lưu.

**Giữ máy và backend chạy để lịch hoạt động.** Chưa có Windows service/wake hoặc scheduler đa tiến trình. Chỉ chạy một backend cùng DB/profile; xử lý login/CAPTCHA thủ công bằng đúng profile. Source error không xóa raw nguồn khác. CLI có catch-up theo khoảng ngày riêng, khác policy dashboard ngoài khung.

## Bằng chứng

Contract tests ở [test_dashboard.py](../../tests/contract/test_dashboard.py), [test_conversation_schedule.py](../../tests/contract/test_conversation_schedule.py), [test_dashboard_raw_v2.py](../../tests/contract/test_dashboard_raw_v2.py) bảo vệ timezone, lượt chốt, persistence/migration, busy/restart và raw bridge. [Validation lịch v2 ngày 10/10](../../reports/dashboard-schedule-v2-validation.json) có 30 contract tests, 2 Chromium fixtures và đọc API thực; chưa nghiệm thu nhiều ngày live hoặc coverage toàn watchlist.

[Report daily slots ngày 08/10](../../reports/daily-slots-schedule-20261008.json) và các preview hai tab là evidence của scheduler/UI v1 **trước khi thêm lượt chốt**. Số 72/69 tests của các lượt đó là số lịch sử, không phải tổng suite hiện hành. Reports là artifact local, có thể không có trong checkout mới.
