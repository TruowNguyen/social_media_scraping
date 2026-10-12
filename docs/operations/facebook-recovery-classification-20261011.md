# Thu lại nội dung thiếu và phân loại hàng chờ — 11/10/2026

## Phạm vi được yêu cầu

Người dùng yêu cầu crawl lại để lọc lại dữ liệu; sau đó cho phép Gemini xử lý toàn bộ hàng chờ, gồm dữ liệu phục hồi và dữ liệu chưa phân loại trước đó. Model nhận caption/comment, OCR và ngữ cảnh bài cha qua gateway đang cấu hình. Kết quả DONE còn khớp đầu vào được giữ; không xóa raw, lịch sử phân loại hoặc đánh giá của người dùng.

Đầu vào lúc bắt đầu: 2.969 node, 306 node chưa có text/OCR đủ làm input, thuộc 123 bài gốc trên 13 nguồn. Đây là thu lại các bản ghi thiếu đã lưu theo permalink, không phải xác nhận crawl hết mọi bài/comment của group trong hai tuần.

## Thứ tự xử lý

1. Sao lưu SQLite. Dùng Playwright/Chromium và profile Facebook hiện có để mở đúng permalink của từng POST/COMMENT/REPLY thiếu nội dung.
2. Lưu vào cùng identity và ghi observation/revision; không lấy caption bài cha thay cho comment, không gán nội dung của feed phía sau. OCR runtime chỉ áp dụng ảnh POST.
3. Chạy bộ lọc cục bộ trên dữ liệu đã lưu. Các trường hợp thiếu chữ hoặc không truy cập được giữ outcome riêng.
4. Sau khi hoàn tất manifest thu lại, đối soát đầu vào phân loại và giữ DONE còn hợp lệ. Thử lại một lần các job FAILED hiện hành đủ điều kiện; mỗi job vẫn tối đa ba attempts, có backoff.
5. Gửi batch đến Gemini, chỉ lưu kết quả vượt validator. Lỗi API/schema vẫn giữ dữ liệu và trạng thái lỗi, không biến thành kết quả thành công.

## Bằng chứng đang cập nhật

- [Manifest thu lại](../../reports/facebook-missing-recrawl-20261011.json): kết quả riêng từng identity, không chứa caption, cookie hoặc key.
- [Kết quả phân loại](../../reports/facebook-recovery-classify-20261011.json): tạo sau khi manifest thu lại hoàn tất; số node hiện hành, batch/API outcomes, bảo toàn analyses và reviews.
- Sao lưu trước crawl: `sessions/backups/facebook-missing-recrawl-20261011-recover_6413d165579b42be9050726c20992e28.sqlite3`.

Manifest có checkpoint từng item. Nếu hết time budget 20 phút, chạy lại với `--resume` để tiếp tục PENDING, không quét lại các item đã có kết quả. Không tự lặp vô hạn những nội dung vẫn thiếu chữ.

```powershell
Set-Location 'D:\task\social_listening\social_media_scraping'
.\.venv\audit\Scripts\python.exe -X utf8 reports/facebook-missing-recrawl-20261011.py --resume

# Chỉ chạy sau khi manifest thu lại có trạng thái FINISHED.
.\.venv\audit\Scripts\python.exe -X utf8 reports/facebook-recovery-classify-20261011.py --prepared-only
# Nếu phiên phân loại bị ngắt, dùng --resume để giữ thống kê/checkpoint.
```

Lượt xử lý hữu hạn dùng hàng chờ đã chuẩn bị để tránh đối soát toàn kho ở mỗi batch. Claim/resolve vẫn xác minh phiên bản target, context và OCR cho từng item. Khi không còn job sẵn sàng, đối soát toàn kho lại trước khi kết luận hoàn tất; backoff chưa đến hạn không bị coi là hàng chờ rỗng. Chế độ worker nền thông thường không đổi.

## Kết quả thu lại đã xác nhận

Hoàn tất 306/306 target, phục hồi 195 nội dung: 17 POST, 5 COMMENT và 173 REPLY. 100 target vẫn thiếu chữ (95 COMMENT, 4 POST, 1 REPLY); 11 target báo CONTENT_UNAVAILABLE. Tổng đầu vào chưa đủ text/OCR sau thu lại là 111.

Trong 17 POST phục hồi, 9 bài có caption và 8 bài có chữ OCR để làm input. OCR được lưu thành evidence riêng, không biến thành caption. OCR ảnh COMMENT/REPLY vẫn chưa có runtime resolver.

Một reply ban đầu bị chặn lỗi kiểm tra identity/parent. Hai lần đối chứng lại có đúng native ID/parent và 21 ký tự; phép lưu thử luôn rollback đạt, nên thu lại riêng một lần và đã lưu thành công vào đúng ID. Không đổi parent hoặc nới validator; nguyên nhân lỗi lần đầu chưa tái hiện. [Đối chứng và phục hồi](../../reports/facebook-recovery-conflict-20261011.json).

Kho vẫn có 2.969 node, không thêm identity trùng hoặc thay parent. SQLite quick_check đạt, foreign key violations = 0; analyses lịch sử và cả hai bảng reviews được giữ nguyên. [Đối chiếu backup](../../reports/facebook-recovery-integrity-20261011.json).

Bộ lọc trên 195 nội dung phục hồi: 182 PASS, 10 REVIEW, 3 DROP. PASS cho phép xử lý tiếp, không khẳng định có phản ánh. Bước thu lại chính không gọi Gemini (581 API observations trước và sau); lần phục hồi riêng cũng không gọi model. Đối soát giữ 1.052 DONE hợp lệ; một số kết quả cũ cần phân loại lại vì caption/ngữ cảnh bài cha vừa phục hồi làm input binding thay đổi. Gemini tiếp tục hàng chờ ban đầu 1.572 PENDING và 67 FAILED hiện hành đã được thử lại có giới hạn, cùng reply mới phục hồi.

Đã xác nhận 67 job lỗi cũ đều chuyển DONE: 66 UNCERTAIN_OCR_REQUIRES_REVIEW và 1 INVALID_RESPONSE_ENVELOPE. DONE đo bằng node hiện hành, không cộng job/analysis lịch sử hoặc mọi response HTTP 200.

## Kết quả phân loại đã lưu

Chốt ngày 11/10/2026 sau khi xử lý hàng chờ bằng `ag/gemini-3.8-flash-low`:

| Trạng thái node hiện hành | Số lượng |
| --- | ---: |
| DONE | 2.692 |
| FILTER_DROP, không gọi model | 166 |
| MISSING_TEXT | 111 |
| PENDING / RUNNING / FAILED | 0 |
| Tổng node | 2.969 |

Tỷ lệ DONE là 90,67% toàn kho, không phải accuracy. Kết quả DONE gồm 13 KEEP, 424 REVIEW và 2.255 DROP. 90 kết quả có intent UNKNOWN; 417 REVIEW chưa có nhóm vấn đề. Đây là các kết luận cần xem xét đã vượt schema, không phải job chưa chạy. Không tự gán nhóm vấn đề hoặc COMPLAINT khi thiếu bằng chứng.

Trong 195 nội dung phục hồi: 192 DONE (173 DROP, 19 REVIEW), 3 FILTER_DROP. Không ghi nhận KEEP mới trong tập này. Toàn bộ DONE có content_intents; số phản ánh được giữ và chất lượng taxonomy cần đối chứng nghiệp vụ riêng.

Lượt chính dùng batch 6 + 4 cho các lần claim 10 items; quota output/input có thể tạo batch nhỏ hơn. 342 request, tất cả HTTP 200, gồm retry/kiểm tra lỗi. Có 3 response lỗi DUPLICATE_JSON_KEY và 8 lượt item chưa qua validator; retry đã xử lý. Một batch 6 items hai lần gặp PROVIDER_PROTOCOL_MISMATCH; lần thử cuối tách riêng từng item đạt 6/6, giữ tổng ba attempts/job, không nới validator. [Metadata response, không lưu body](../../reports/classifier-protocol-diagnostic-20261011.json). Không chứng minh nguyên nhân gốc của response lỗi hoặc bảo đảm lỗi này không tái diễn trong tương lai.

SQLite quick_check đạt, foreign key violations = 0, analyses/reviews lịch sử bảo toàn. Có 1.644 analyses mới trong lịch sử, trong khi số node DONE tăng 1.640; tiến độ dùng node hiện hành thay vì số analyses. [Kết quả cuối](../../reports/facebook-recovery-classify-20261011.json).

## Worker và lịch sau lượt này

Hàng chờ hiện tại đã xử lý xong. Sau khi người dùng trả lời “Cho phép chạy liên tục”, worker nền đã được bật bằng `--serve --poll-seconds 15` và kiểm chứng ACTIVE ngày 11/10. Quyền bao phủ caption/comment, OCR và ngữ cảnh mới hoặc thay đổi từ các lượt crawl sau này đến Gemini đang cấu hình. Lượt đối soát giữ 2.692 DONE hợp lệ, không tạo job mới và không gọi API (`NO_PENDING_JOBS`, `api_calls=0`; tổng request đã lưu vẫn 923). PID launcher 36832, worker 30540; stderr rỗng. Việc từ chối auto-review trước đó đã được giải quyết bằng quyền mới này.

Dashboard vẫn chạy, lịch crawl enabled: 05:00–08:30 và 17:00–18:30 giờ Việt Nam, chu kỳ 45 phút; lượt kế tiếp tại thời điểm kiểm tra là 17:00 ngày 11/10. Lịch thu raw trước, worker nhận dữ liệu đủ điều kiện để filter/classify sau commit. Worker chưa đăng ký tự khởi động cùng Windows. [Bằng chứng bật liên tục](../../reports/classifier-continuous-enabled-20261011.json), [report cycle gần nhất](../../reports/classifier-recovery-20261011-worker-latest.json); log `reports/classifier-recovery-20261011.out.log` và `.err.log`.

## Điều kiện nghiệm thu

- Mọi target trong manifest có outcome; không còn PENDING thu lại.
- Nội dung phục hồi vẫn dùng node ID cũ; thời gian không đọc được không tự suy diễn.
- Hàng chờ phân loại không còn PENDING/RUNNING hiện hành hoặc có lý do dừng API rõ ràng; lỗi còn lại được đếm riêng.
- SQLite quick_check đạt, không có foreign key violations; analyses lịch sử và reviews được bảo toàn.
- Tỷ lệ DONE dùng số node hiện hành làm mẫu số; FILTER_DROP và MISSING_TEXT không được tính là đã phân loại bằng model.

Coverage Facebook vẫn PARTIAL/UNKNOWN. Bình luận chỉ có ảnh chưa có media resolver/OCR; một permalink còn truy cập được không chứng minh toàn bộ reply đã tải. Phân loại vượt schema không đồng nghĩa đạt accuracy nghiệp vụ; KEEP/REVIEW cần người dùng đối chứng.
