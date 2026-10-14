# Vận hành khi máy cá nhân không chạy liên tục

Trạng thái: **LOCAL_IMPLEMENTED / OFFLINE_VERIFIED / LIVE_TASK_API_VERIFIED**. Người dùng chọn local tự khởi động và chạy bù. Supervisor, ledger/lịch sử, planner ca đã đóng và task đăng nhập Windows đã triển khai; xem [runbook](operations/local-runtime-recovery.md). Không chuyển DB sang máy chủ. Trigger qua reboot/logoff và full coverage nhiều ngày live chưa nghiệm thu. Phần server vẫn là đề xuất.

## Mục tiêu

Không phải mở riêng dashboard và classifier sau mỗi lần bật máy. Tác vụ đang dở và nội dung đã lưu được phục hồi; các ca chưa chạy được nhận diện, thay vì im lặng coi là đã hoàn thành. Nếu cần thu đúng lịch khi máy cá nhân tắt, hệ thống phải chạy trên một máy khác luôn bật.

## Hiện trạng đã đối chiếu với code

| Thành phần | Có hiện tại | Còn thiếu |
| --- | --- | --- |
| Facebook | Schedule lưu file; tác vụ durable; resume theo lease; lịch trong dashboard | Tạo tác vụ bù cho ca đã kết thúc khi hệ thống offline, đặc biệt ngày trước |
| Threads | Lịch/query/run durable; catch-up tick gần nhất theo từng ca trong ngày; recovery các trang đã staging trước lease expiry | Catch-up ngày trước; retry có kiểm soát cho lượt đã thất bại vì lỗi phiên |
| Classifier | Worker `--serve`, job queue lưu DB, reuse DONE hợp lệ, reclaim lease hết hạn và retry giới hạn | Khởi động cùng hệ thống; tự restart process nếu lỗi; không phải bấm riêng |
| Profile | Đã gỡ khóa mồ côi; mã nguồn thêm khóa OS và kiểm tra PID/browser | Nạp bản sửa ở lần restart dashboard tiếp theo; phiên hết hạn vẫn cần đăng nhập thủ công |
| Giao diện | Trạng thái riêng crawl/classifier; raw và kết quả lưu lâu dài | Hiển thị ca bỏ lỡ/chạy bù và giới hạn coverage theo ca |

Nguồn đối chiếu: `engine/dashboard.py::schedule_tick/_schedule_loop`, `engine/dashboard_conversations.py::pending_run`, `engine/threads_service.py::tick/_recover_queue`, `engine/classification_worker.py::main/reconcile_saved`, `engine/classification_jobs.py::claim`.

## Hai cách vận hành

### A. Máy hiện tại: tự bật và chạy bù

- Một lệnh quản lý chạy dashboard và classifier như hai process độc lập; kiểm tra trùng trước khi tạo process, restart có backoff và ghi health riêng.
- Đăng ký tác vụ chạy khi người dùng đăng nhập Windows, không phải yêu cầu mật khẩu qua chat. Task Scheduler chỉ kích hoạt supervisor; lịch nền tảng vẫn do hệ thống quản lý.
- Mở máy lại: kiểm tra phiên/profile → phục hồi tác vụ dở → xác định các ca bỏ lỡ trong giới hạn cấu hình → tạo hàng chờ chạy bù → xử lý bình thường.
- Classifier xử lý hàng chờ đã lưu ngay cả khi browser bị chặn. Crawl không đợi Gemini; lỗi API không làm mất raw.
- Khi máy tắt/ngủ, cả hai worker tạm dừng. Chạy bù chỉ lấy được nội dung vẫn còn truy cập được, không phục hồi nội dung đã xóa/ẩn trong thời gian offline.

### B. Máy chủ luôn bật

- Chạy cùng supervisor/crawl/classifier trên một máy chủ; máy cá nhân chỉ xem dữ liệu và điều khiển qua giao diện.
- Thiết lập browser và đăng nhập Facebook/Threads trực tiếp trên máy chủ khi cần; kiểm chứng browser live trước khi chuyển lịch. Không mặc định rằng copy profile Windows là có phiên đăng nhập dùng được trên máy khác.
- Database hoạt động đặt trên ổ đĩa cục bộ của máy chủ. Trong phạm vi một host vẫn có thể giữ SQLite hiện tại; không để hai máy cùng ghi một file SQLite qua thư mục chia sẻ.
- Di chuyển bằng backup SQLite nhất quán; dừng producer cũ trước khi bật producer mới để tránh crawl hai nơi cùng profile/scope. Giữ lịch sử, reviews, raw, OCR và lineage khi đối soát.
- Giao diện hiện bind `127.0.0.1`; cần thiết kế truy cập từ máy cá nhân có xác thực hoặc đường hầm riêng trước khi sử dụng từ xa.
- Server không tự giải quyết lỗi parser, CAPTCHA, nội dung không truy cập được hoặc coverage hữu hạn. Bỏ lỡ do server/mạng dừng vẫn dùng chung cơ chế chạy bù.

## Các phase và nghiệm thu

| Phase | Công việc | Điều kiện chấp nhận |
| --- | --- | --- |
| R0 | Chốt local chạy bù hay server; phạm vi chạy bù và nguồn/dự án | Không thay lịch hoặc bật host thứ hai khi chưa chốt nơi vận hành |
| R1 | Supervisor và single-instance; start/stop/health; backoff và tắt có kiểm soát | Một lệnh khởi động cả dashboard/classifier; gọi lại không nhân đôi; kill classifier rồi tự khởi động lại; không kill job đang chạy khi đọc trạng thái |
| R2 | Lưu lịch sử cấu hình và ledger ca cần xử lý | Mỗi platform/project/source hoặc query snapshot/window có khóa idempotency; lưu trạng thái chờ/đang chạy/kết thúc/blocked và coverage; thay lịch không áp cấu hình mới giả vào lịch sử cũ |
| R3 | Planner chạy bù theo ca, mặc định đề xuất tối đa 7 ngày và được cấu hình | Tắt máy qua hai ca rồi mở lại tạo ca thiếu đúng timezone; không replay mọi tick 45 phút nếu một lần quét toàn ca đã đủ phạm vi; rerun không tạo thêm task trùng |
| R4 | Điều phối recovery và tác vụ đúng lịch | Tác vụ trong ca hiện tại không bị toàn backlog chiếm; mỗi profile một job; giữ budget từng lượt; cần quét tiếp thì giữ coverage PARTIAL, không tự xác nhận đủ window |
| R5 | Khởi động tự động local hoặc triển khai server | Local: thử đăng nhập/reboot và verify worker. Server: pilot live cả Facebook/Threads, backup/restore và đối soát số node/review; client tắt không dừng server |
| R6 | Trạng thái và đối soát UI | Hiển thị ca bỏ lỡ, đang chạy bù, đã quét giới hạn, yêu cầu đăng nhập; tách số raw mới với số phản ánh được giữ; bảng cũ vẫn đọc được khi crawl/API lỗi |

### Quy tắc chạy bù

1. Window theo giờ Việt Nam và `[start, end)`; lấy ngày đăng riêng của bài/bình luận, không dùng ngày thu thay ngày đăng.
2. Ca còn mở chỉ tạo window đến hiện tại; ca đã đóng dùng toàn ca. Ca ngoài thời hạn chạy bù phải được báo skipped/needs-manual-backfill, không coi là thành công.
3. Không chỉ nhìn ngày đăng bài cha: bình luận mới của bài cũ phải vào scope quét thread. Inventory hiện có hỗ trợ nhưng vẫn hữu hạn; cần phân trang/checkpoint qua nhiều lượt để tăng coverage.
4. Gộp các tick bỏ lỡ trong cùng ca thành nhiệm vụ bù theo ca, giữ observations/run lineage; không nhân chi phí bằng replay mọi tick đã bỏ lỡ.
5. Nội dung thiếu timestamp giữ nguyên dấu chưa xác minh, không tính là đã thu đủ ca. Không có nội dung mới chỉ là kết quả quan sát, không mặc định nghĩa là ca không có bài.
6. Tác vụ browser bị login/CAPTCHA dừng nguồn và báo blocked; classifier tiếp tục xử lý dữ liệu còn chờ. Không retry login vô hạn.
7. DONE hợp lệ được reuse; sau crash một request Gemini chưa commit có thể phải gửi lại. Không cam kết exactly-once với provider bên ngoài.

## Kiểm thử cần thực hiện sau triển khai

- Offline: restart hai lần; single-instance; process chết nhả khóa; lỗi profile không cản classifier; lịch sử cấu hình, timezone và slot boundary.
- Offline: mất điện giữa raw commit/outbox/enqueue/classification commit; dữ liệu không mất, job có thể tiếp quản sau lease; worker cũ không commit bằng lease đã hết hạn.
- Offline: hệ thống tắt một ngày, ba ngày, quá giới hạn chạy bù; lịch disabled; thay lịch/dự án giữa downtime; run failed/blocked không báo thành công.
- Live local: đóng toàn bộ process rồi mở bằng một lệnh; dữ liệu mới được crawl/lưu/filter/classify và truy nguyên đúng ca/run. Reboot/đăng nhập thử sau khi đăng ký task.
- Live server nếu chọn: tắt máy cá nhân trong một ca và đối soát server vẫn ghi raw/classification; xác minh session, coverage và tình huống yêu cầu đăng nhập.

## Tài liệu tham khảo

- [Microsoft Task Scheduler](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-start-page): trigger khi boot, đăng nhập và theo lịch.
- [Playwright authentication](https://playwright.dev/python/docs/auth): tái sử dụng trạng thái đăng nhập; profile/state không đưa vào Git.
