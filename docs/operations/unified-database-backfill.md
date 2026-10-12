# DB chung và Facebook backfill — 09/10/2026

DB hoạt động duy nhất: `sessions/acquisition/acquisition.sqlite3`. Dashboard mặc định dùng cùng file cho search, raw, library/review và classifier; worker mặc định đọc file này. `--conversation-db` chỉ còn là override cho kiểm thử hoặc nhu cầu đặc biệt. File raw riêng cũ được bỏ sau xác minh; backups dưới `sessions/backups/consolidation-20261009T162412Z/` là bản khôi phục, không được service sử dụng.

Hợp nhất đã sao lưu cả hai SQLite bằng backup API (bao gồm WAL), copy schema/data raw vào DB acquisition, đối chiếu từng hàng, integrity/FK check, rồi map 28 bản ghi Facebook cũ sang nodes. Với identity đã có raw mới, migration giữ nguyên caption/revision mới; không dùng caption cũ ghi đè. Reviews/notes, observations, aliases, job/analysis history được giữ. Kết quả ngay sau merge: 31 POST và 6 COMMENT; 31 permalink được đưa vào thread inventory. Legacy tables giữ làm audit; dữ liệu từng bị purge không được phục hồi bằng migration này. Báo cáo: `reports/database-consolidation.json`.

## Chạy

```powershell
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.dashboard
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.classification_worker --serve
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.facebook_backfill
```

Nếu inventory đã phát hiện permalink nhưng chưa kịp mở vì time budget, chạy `engine.facebook_backfill --pending-only --start <UTC-start> --end <UTC-end> --report reports/facebook-backfill-pending.json`. Lượt này không discovery lại, chỉ mở post chưa từng được thử trong saved inventory, tối đa 1.200 giây/group và 3.600 giây/run. Các lượt dùng cùng window cố định; ghi rõ số đã thử và số còn lại. Đã thử một thread không đồng nghĩa đã lấy hết comments của thread đó.

Backfill trực tiếp browser Facebook, không dùng SerpApi. Window cố định 14×24 giờ trước lúc chạy, UTC `[start,end)`; dữ liệu được hiển thị theo giờ Việt Nam. Chạy lần lượt tất cả group được bật/xác minh (14 group). Inventory tối đa 5.000 candidate/group, 100 giây duyệt feed, chờ tối đa 8 lượt không phát hiện bài mới; sau đó quét cả các permalink cũ đã biết để tìm comment mới. Budget tối đa 180 giây/group, 60 giây/thread, 3.600 giây/run; giữ tiến độ/outcome vào DB và `reports/facebook-backfill-14-days.json`. Worker phân loại xử lý raw đủ text khi raw được commit; nội dung DROP vẫn giữ.

Giới hạn này tăng phạm vi so với pilot, **không chứng minh đã thu mọi bài/comment**. Kết quả phải ghi rõ candidate cap, hết thời gian, lỗi truy cập/parser, số permalink chưa quét, thời gian bài/comment chưa xác minh và coverage PARTIAL/UNKNOWN. Không dừng chỉ vì gặp một bài cũ hoặc pinned post, không suy thời gian comment từ bài gốc. Rerun dedup raw bằng identity; fair inventory ưu tiên thread lâu chưa kiểm tra.

Trong tab Kho dữ liệu, chọn ngày đăng để chỉ xem node đã xác minh nằm trong window; bỏ lọc ngày hoặc chọn ngày thu thập để xem node chưa rõ giờ. Tab phân loại bao gồm dữ liệu cũ đã map vào raw chung, không chỉ pilot trước đây. Xem số liệu thực và outcome từng group trong report sau khi run hoàn tất; không dùng tổng số trong DB làm số dữ liệu mới của riêng run.

## Kiểm tra bổ sung feed

Diagnostic live cho thấy feed vẫn tải thêm DOM khi cuộn, nhưng Story JSON chỉ chứa các post ban đầu, role=article chủ yếu thuộc comments. Discovery đã bổ sung parent permalink references từ anchor trong DOM; reference chỉ chứng minh ID/URL bài gốc, không mượn caption/timestamp/author của comment. Nội dung và thời gian bài được xác minh khi fetch permalink. Fixture Chromium kiểm tra độc lập quy tắc này; pilot cùng một group tăng từ 3 lên 5 post sau cuộn (`reports/facebook-listing-reference-live-validation.json`). Report lượt đầu được giữ tại `reports/facebook-backfill-14-days-first-pass.json`; lượt bổ sung dùng cùng start/end, không trượt window theo giờ rerun. Đây là tăng coverage, chưa là bằng chứng lấy hết feed.

## Kết quả crawl thực — 10/10/2026

Ba lượt đã hoàn tất trên 14 group; cùng window `[2026-09-25T16:27:32.769749Z, 2026-10-09T16:27:32.769749Z)` — giờ Việt Nam 23:27 ngày 25/09 đến 23:27 ngày 09/10. Lượt pending chỉ mở inventory chưa từng được thử; sau cùng còn 0 permalink chưa thử. Đây là tình trạng inventory quan sát được, không phải chứng minh toàn bộ Facebook group đã được thu thập.

| Chỉ số đã dedup | POST | COMMENT | REPLY |
| --- | ---: | ---: | ---: |
| Tổng đang lưu trong DB chung | 301 | 1.208 | 284 |
| Có văn bản đã đọc được | 285 | 1.144 | 138 |
| Xác nhận thời gian riêng của node trong window | 237 | 850 | 82 |
| Nội dung mới so với baseline sau merge | 270 | 1.202 | 284 |
| Nội dung mới được xác nhận trong window | 209 | 844 | 82 |

Baseline 37 nodes gồm 31 POST và 6 COMMENT. Không cộng số observations giữa các lượt để tính nội dung mới. Bài cũ được giữ để truy vết comment mới; node không rõ giờ vẫn giữ raw nhưng không tính là IN_WINDOW. 395 nodes còn publication precision UNKNOWN. Metadata-only hoặc media-only không được coi là đã lấy đủ caption/comment.

Snapshot tổng hợp lúc 00:27 ngày 10/10: 856 analysis hiện hành; 597 jobs PENDING và 4 RUNNING, worker tiếp tục xử lý. 13 jobs FAILED gồm 12 `COMPLAINT_INTENT_CANNOT_BE_DROPPED` và 1 `INVALID_RESPONSE_ENVELOPE`; raw còn nguyên, không coi lỗi validation là kết quả phân loại hợp lệ. Đây là số tại thời điểm báo cáo, không phải tổng sau khi worker xử lý hết.

`PRAGMA integrity_check = ok`, foreign-key violations = 0; DB riêng cũ không còn. Dashboard trả dữ liệu từ DB chung. Kiểm tra kỹ thuật: 186 contract tests, 8 Chromium acquisition/reference fixtures và 2 Chromium dashboard fixtures pass. Các fixtures không thay thế kiểm chứng độ bao phủ live. Chi tiết từng group/lượt, baseline, thời gian và giới hạn: [report tổng hợp](../../reports/facebook-backfill-14-days-summary.json). Trạng thái **PARTIAL**, `full_window_coverage_verified=false`; chưa đủ bằng chứng nghiệm thu “mọi bài/comment trong 14 ngày”.
