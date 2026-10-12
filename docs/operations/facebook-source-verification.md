# Kiểm tra metadata của bảy Facebook group

> **Snapshot lịch sử theo ngày trong tài liệu.** Các trạng thái “chưa triển khai”, disabled hoặc lỗi probe chỉ áp dụng cho lượt kiểm tra đó. Đối chiếu code/config hiện hành ngày 11/10/2026 tại [trạng thái dự án](../current-state.md); không dùng snapshot này để kết luận runtime hiện tại.

**Kết quả mới nhất 08/10/2026:** Playwright/Chromium của acquisition engine truy cập được **7/7 group**, đọc native post ID và thời gian đăng gốc cho một mẫu mỗi group. Không dùng SerpApi/Google/Facebook Graph API, 0 API requests. Kết quả sau đối chiếu: 3 DROP, 1 sau cutoff, 3 giữ trong window 7 ngày (2 mới, 1 đã tồn tại). Registry ghi VERIFIED cho access/native ID/time; enabled flags giữ nguyên. Chưa xác nhận thứ tự mới nhất, anonymous access hoặc coverage đầy đủ. Xem [báo cáo bảy group](../../reports/facebook-seven-groups-20261008/README.md) và [evidence JSON](../../reports/facebook-seven-groups-20261008/report.json). Các kết quả bên dưới là lịch sử trước pilot này.

Ngày kiểm tra: **08/10/2026**, theo yêu cầu người dùng mở từng group và bổ sung thông tin vào Source Registry.

## Kết quả truy cập thực tế

Browser runtime khởi tạo được nhưng chọn browser trả `No browser is available`; danh sách browser kết nối là `[]`. Không có phiên browser để đọc nội dung hiển thị hoặc sử dụng Facebook login hiện có.

Đã thử mở riêng trang `/about` của cả bảy URL bằng công cụ web: tất cả trả lỗi fetch `Cache miss`. Search không cung cấp kết quả matching đúng group đủ để xác minh; không lấy thông tin của group có ID khác hoặc bài Help Center làm metadata của những nguồn này.

| Source reference | Trang đã thử kiểm tra | Tên/mô tả/quyền truy cập |
| --- | --- | --- |
| 139108668844789 | https://www.facebook.com/groups/139108668844789/about | Chưa đọc được, chưa xác minh |
| 880263084346112 | https://www.facebook.com/groups/880263084346112/about | Chưa đọc được, chưa xác minh |
| 2249052912495339 | https://www.facebook.com/groups/2249052912495339/about | Chưa đọc được, chưa xác minh |
| 669205626514948 | https://www.facebook.com/groups/669205626514948/about | Chưa đọc được, chưa xác minh |
| suanhathuduc | https://www.facebook.com/groups/suanhathuduc/about | Chưa đọc được, chưa xác minh |
| 144732306144575 | https://www.facebook.com/groups/144732306144575/about | Chưa đọc được, chưa xác minh |
| 1675953926771851 | https://www.facebook.com/groups/1675953926771851/about | Chưa đọc được, chưa xác minh |

Không kết luận từ lỗi fetch rằng group private, cần đăng nhập, không tồn tại hoặc không liên quan VinCons. Tại thời điểm kiểm tra browser/web, registry giữ name placeholder, project/location null, access_type UNKNOWN, requires_login null, access_verified/name_verified false và disabled. Phần bổ sung dưới đây ghi nhận sáu tên người dùng cung cấp sau đó.

## Tiếp tục kiểm tra khi có browser

Người dùng kết nối Chrome/Edge với phiên làm việc qua tiện ích ChatGPT Browser, đăng nhập Facebook tại browser đó và báo đã sẵn sàng. Không gửi mật khẩu, OTP, cookie hoặc session token vào chat.

Sau khi browser có thể đọc group, đối chiếu URL/ID rồi ghi:

- Tên group thật và mô tả hiển thị.
- Public/private/visible/access observations dựa trên màn hình đã đọc; trạng thái login của một phiên không đủ chứng minh truy cập ẩn danh cần hay không cần login.
- Project/location context nếu mô tả có bằng chứng; context không tự chứng minh từng post liên quan.
- Reference numeric của slug nếu URL/visible identity thực sự cung cấp; kiểm tra alias trùng với các group còn lại.
- Evidence URL, thời điểm kiểm tra và những field còn thiếu.

Đọc metadata trong phiên Facebook không tự chứng minh khả năng automation/crawl của adapter. Xác nhận truy cập thủ công được ghi access_verified với method/date rõ ràng; verification_status=VERIFIED và bật source cần kiểm chứng phương thức acquisition của dự án. Không tự request join, post hoặc thay đổi group settings trong nhiệm vụ đọc này.

## Bổ sung sau khi người dùng tra cứu thủ công

Ngày 08/10/2026, người dùng cung cấp sáu cặp URL/tên group; đã nhập chính xác vào registry, đặt name_verified=true và name_verification_method=USER_MANUAL_CONFIRMATION kèm name_verified_on. Không ghi nhận là browser verification.

| Reference | Tên người dùng xác nhận |
| --- | --- |
| 1675953926771851 | HỘI CÔNG NHÂN VINCONS |
| 144732306144575 | CÔNG TY VINCONS (TẬP ĐOÀN VINGROUP ) |
| 669205626514948 | Hội công nhân Vincons Suối Khoáng Mỹ Lâm |
| suanhathuduc | HỘI CÔNG NHÂN XÂY DỰNG VINCONS |
| 139108668844789 | Hội Nhóm Công Nhân Vincons Xây Dựng Nam Bắc |
| 880263084346112 | TUYỂN DỤNG CÔNG NHÂN CƠ HỮU VINCONS |

Group 2249052912495339 chưa có tên được cung cấp. Không thay original URL/source IDs, priority hoặc enabled flag. Các fields privacy/login/access/project/location vẫn chưa xác minh; metadata source-level chưa được auto-accept đầy đủ.

Registry: [sources.yaml](../../config/sources.yaml). Hướng dẫn: [config README](../../config/README.md).

## Xác nhận public/access thủ công mới nhất

Ngày 08/10/2026, người dùng xác nhận: “tất cả các group tôi tìm đều là công khai và có thể vào đó”. Áp dụng cho cả bảy URL seed: access_type=PUBLIC, access_verified=true, access_verification_method=USER_MANUAL_CONFIRMATION và access_verified_on=2026-10-08. Các kết quả công cụ ở trên là lịch sử, chưa phải kiểm chứng browser của dự án.

Hiện có 7 nguồn public/truy cập thủ công đã xác nhận, 0 enabled. Tất cả vẫn PENDING_VERIFICATION và requires_login=null: chưa kiểm chứng đọc bài bằng phiên Facebook của Chromium dự án, giữ phiên sau khi mở lại hoặc extraction của adapter. Chưa LIVE_VERIFIED/ACP. Tên hiển thị group 2249052912495339 hiện là “Cộng Đồng Công Nhân Vincons”, name_verified=false. Bước tiếp theo: đăng nhập theo [browser bootstrap](browser-bootstrap.md), mở một group trong profile dự án và kiểm tra giữ phiên.
