# Acquisition v1: vận hành pilot

Đồng bộ 11/10/2026. Runbook này dành cho **acquisition v1/post-only**, gồm Facebook/TikTok/SerpApi/queue/YouTube bridge. Dashboard Facebook đã dùng [raw v2](dashboard-raw-v2.md), policy lưu trước filter khác CLI v1. Offline suites và live pilots có evidence theo ngày; full acquisition/coverage/ACP chưa nghiệm thu.

## Cấu hình hiện hành và probe lịch sử

Registry hiện có 14 Facebook group enabled/VERIFIED, Google enabled/VERIFIED, TikTok search disabled/PENDING_VERIFICATION; watchlist `vincons_acquisition_v1` ACTIVE, lookback v1 10.080 phút. Facebook đã có mẫu native ID/time và [backfill raw v2](unified-database-backfill.md); Google đã có Account/Search pilot thành công. Bảng dưới là snapshot config/evidence, không kiểm tra lại access/key/quota trong lượt đồng bộ tài liệu.

| Nguồn | Cần cung cấp | Kết quả quan sát trên máy |
| --- | --- | --- |
| Chung | Venv acquisition và Chromium | Đã cài; parser DOM giả lập và tái sử dụng profile local được kiểm tra |
| Facebook | Profile dự án, đăng nhập thủ công khi yêu cầu | 14 groups bật/xác minh mẫu; LOGIN_REQUIRED là probe ban đầu, coverage vẫn PARTIAL |
| TikTok | Profile đọc được cả giao diện keyword và hashtag | Keyword: ACCESS_DENIED / CAPTCHA. Hashtag: EXTRACTION_FAILED / LISTING_SELECTOR_MISMATCH; chưa đủ thông tin kết luận access hay layout |
| Google | SERPAPI_API_KEY hợp lệ và quota tài khoản | Config enabled/VERIFIED, successful Account/Search pilot theo ngày; INVALID_KEY là lịch sử |
| Registry | Public/access/source-watchlist gates | 14 Facebook + Google ready trong config, TikTok disabled; seed watchlist vẫn DRAFT/disabled |

Không cần LLM/GPU/ASR/Excel cho acquisition pilot. Nếu chưa đăng nhập mà đọc đủ dữ liệu thì có thể dùng profile anonymous. Public group vẫn có thể gặp login wall ở lượt khác; probe là kết quả tại thời điểm kiểm tra.

## Cài và kiểm tra offline

```powershell
cd "D:\task\social_listening\social_media_scraping"
uv pip install --python .\.venv\audit\Scripts\python.exe -r requirements-acquisition.txt
uv pip install --python .\.venv\audit\Scripts\python.exe --no-deps -e .
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli validate
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli sources list
```

Đã thực hiện cài đặt trên workspace này. `social-acquire` là console entry point tương đương module CLI. Profile và DB nằm dưới repository `sessions/`, đã ignore; mặc định DB `sessions/acquisition/acquisition.sqlite3`, tách hoàn toàn legacy dedup.

## Chuẩn bị phiên và xác minh nguồn

```powershell
.\.venv\audit\Scripts\python.exe -m engine.browser_session --platform facebook --login
.\.venv\audit\Scripts\python.exe -m engine.browser_session --platform tiktok --login
```

Thực hiện từng lệnh; thao tác đăng nhập trong cửa sổ nếu cần, mở thử group/search, đóng cửa sổ và đợi command kết thúc trước khi chạy probe/crawl. CAPTCHA cần thao tác thủ công trong cửa sổ tương tác; crawler sẽ dừng khi gặp block. Không gửi password/OTP/cookie/API key vào chat.

```powershell
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli sources probe fb_group_1675953926771851
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli sources probe tt_search_vincons --mode KEYWORD_SEARCH --query VinCons
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli sources probe tt_search_vincons --mode HASHTAG_SEARCH --query '#VinCons'
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli sources probe google_social_vincons
```

Google probe là **một request thật**, có reserve trước call và tính cả lỗi/retry vào ledger 20/run, 200/tháng UTC. Xem key trong tài khoản [SerpApi](https://serpapi.com/manage-api-key), cập nhật local `.env` rồi chạy lại bằng process mới. Không tự tăng gói hay reset ledger khi đổi key; lịch sử attempted requests được giữ.

Probe không enable hay cập nhật verification_status. Khi đã xác nhận public và nhu cầu login, dùng verify để probe lại và ghi metadata; source vẫn disabled. Ví dụ dùng `true` khi bạn đang dùng phiên đã đăng nhập:

```powershell
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli sources verify fb_group_1675953926771851 --public --requires-login true
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli sources enable fb_group_1675953926771851
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli watchlists enable vincons_acquisition_v1
```

Nếu đã xác nhận profile anonymous truy cập được thì dùng `--requires-login false`. TikTok query scope verify kiểm tra cả keyword và hashtag; Google verify kiểm tra API thật. Chỉ dùng enable sau verify thành công. Enabled source có metadata không đạt gate bị validator từ chối trước network. Các nguồn khác không bật theo watchlist inheritance.

## Chạy acquisition giới hạn

```powershell
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli run --watchlist vincons_acquisition_v1 --source-id fb_group_1675953926771851 --max-candidates 5
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli run --watchlist vincons_acquisition_v1 --source-id tt_search_vincons --max-candidates 5
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli run --watchlist vincons_acquisition_v1 --source-id google_social_vincons
```

TikTok scope phải verify/enable trước lệnh tương ứng; Google đã ready theo probe/search thành công. TikTok dùng discovery_terms/hashtags; Google sinh hai seed × ba platform = sáu query jobs. Registry/query additions ở `config/acquisition.yaml`; vocabulary ở `config/keywords.yaml`. Source cap 100 Facebook/50 TikTok, lookback hiện tại **7 ngày (10.080 phút)**, 120 giây/job, 1.200 giây/run. CLI cho phép giảm cap/time budget; không bật scheduler.

Không truyền `--start/--end`: engine chốt một window UTC `[now - 7 ngày, now)` cho cả lượt chạy. Google `search_date_filter: WINDOW` gửi `tbs=cdr:1,cd_min:MM/DD/YYYY,cd_max:MM/DD/YYYY` từ ngày UTC của window, kể cả rerun lịch sử. Bộ lọc search theo ngày/index không chứng minh thời gian đăng thực; vẫn giữ published_at=null và UNKNOWN khi thiếu evidence. Google tbs: [tài liệu SerpApi](https://serpapi.com/blog/filtering-google-search-and-google-news-results/).

Rerun cùng window: thêm `--start '2026-10-08T00:00:00Z' --end '2026-10-08T03:00:00Z'`. Window `[start,end)`; bài không có thời gian chính xác giữ UNKNOWN/REVIEW, không tính fresh. Không break sau một bài cũ hoặc pinned. Coverage giới hạn vào kết quả quan sát được và cap/time budget.

Code đọc caption vào bộ nhớ, prefilter, rồi mới fetch permalink/video. DROP chỉ giữ bảy audit fields, không raw text/snippet/title/queue/media/LLM. Prefilter là heuristic bảo thủ theo intent; complaint/mixed/truncated/ambiguous chuyển REVIEW, chưa phải relevance KEEP. Không thu comments hoặc tải file media. Browser có thể request thumbnail khi render, video/audio bị chặn. Không tạo transcript từ yt-dlp trong bridge; YouTube chỉ lấy metadata của đúng item thuộc nguồn đã xác minh.

## Discovery Queue

```powershell
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli discoveries list --status PENDING
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli discoveries approve dq_ID --source-id SOURCE_ID --reviewer ops --note 'Đã đối chiếu đúng nguồn'
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli discoveries reject dq_ID --reviewer ops --note 'Ngoài scope'
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli discoveries reopen dq_ID --reviewer ops --note 'Kiểm tra lại nguồn'
```

`dq_ID`/`SOURCE_ID` là placeholders; lấy ID thật từ list. Duyệt nguồn mới: thêm `--create-source`; chỉ tạo draft disabled trong SQLite, APPROVED vẫn NOT_READY. Nguồn phải có identity group/account/channel xác định; không suy YouTube channel từ snippet. Với YouTube đã được operator đối chiếu, có thể cung cấp `--origin-source-ref UC...` kèm review note; đây là xác nhận thủ công được ghi trong history.

```powershell
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli sources register-draft SOURCE_ID
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli watchlists add-source vincons_acquisition_v1 SOURCE_ID
```

Sau đăng ký, verify/enable riêng. TikTok account/YouTube channel verify cần `--item-url` của một video đã đối chiếu đúng nguồn. Nguồn private/Page/profile không được bind vào Facebook group adapter. Hashtag container tạo draft TIKTOK_SEARCH giới hạn đúng hashtag; không tạo account source từ hashtag. Registry/query membership và enable vẫn riêng với review.

```powershell
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli discoveries process dq_ID --watchlist vincons_acquisition_v1 --start '2026-10-08T00:00:00Z' --end '2026-10-08T03:00:00Z'
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli export --output .\reports\acquisition.json
```

Process chỉ item APPROVED có nguồn ready/in-watchlist; container không trở thành bài. Google source/query lineage được giữ khi fetch bằng adapter đích. Item đã có được attach observation, không auto-approve creator. JSON export là acquisition records + observations; chưa phải canonical enrichment, Excel hoặc báo cáo vận hành VinCons.

## Dashboard local

```powershell
.\.venv\audit\Scripts\python.exe -m engine.dashboard
```

Mở `http://127.0.0.1:8765`. Giao diện hiện tại theo yêu cầu: keyword/hashtag có gợi ý và tự nhập; khoảng ngày mặc định hôm nay theo giờ Việt Nam. Mỗi nhóm tối đa 3 truy vấn, cách nhau bằng dấu phẩy. Bấm **Tìm video** mới gọi Google/SerpApi; mở trang không gọi search. Một trang/query, tối đa 10 candidate/query, budget 20 request/run và 200/tháng local, retry vẫn tính quota. Query form chỉ thay registry trong bộ nhớ của lượt chạy, không ghi đè vocabulary mặc định.

Kết quả chỉ hiển thị content item (bài/video), không biến group/account thành bài. Bốn cột: Link URL, dự án/vị trí, tóm tắt description, vấn đề gặp phải. Ba trường optional dùng dữ liệu enrichment đã có nếu có; hiện acquisition chưa sinh chúng nên để dấu “—”, không suy từ keyword/snippet. Title/snippet Google không phải nội dung đã xác minh; hashtag Google không phải pilot hashtag native TikTok. Window `[00:00 ngày đầu, 00:00 ngày sau ngày cuối)` Asia/Saigon, ngày hôm nay chốt end tại lúc chạy. Google date filter vẫn chỉ theo ngày, bài chưa xác minh timestamp không vào kết quả mới.

Search chạy nền và giao diện chờ kết quả, giữ outcome partial/error rõ ràng. Rule exclusion áp dụng trước queue/full fetch và raw retention; không auto-approve nguồn mới. Dữ liệu run/queue/observations được lưu SQLite; trạng thái job giao diện giữ trong process hiện tại. Dừng bằng Ctrl+C; có thể chọn `--port 8766`, `--db PATH`, `--config-dir PATH`. Không tự bật scheduler.

### Điều kiện bắt buộc về dữ liệu mới

Output hiện chỉ nhận content item có `published_at` timezone-aware, `publication_precision=INSTANT` và timestamp thực nằm trong fixed window của yêu cầu. Không dùng discovered_at, Google date/snippet, timestamp comment hoặc IN_WINDOW từ run cũ. Sắp xếp theo publication instant giảm dần. Timestamp thiếu/mơ hồ, link Google chưa xác minh và bài cũ giữ trong storage/queue nếu đủ điều kiện, nhưng không đưa vào kết quả “mới”. UI hiển thị số mục cần xác minh và thời gian đăng dưới link. Khi mở trang, chỉ đọc dữ liệu đã lưu trong window hôm nay; chỉ bấm Tìm kiếm mới crawl.

Facebook group đã enabled/verified trong watchlist được chạy trước Google discovery. Google tìm nguồn/link bổ sung, không tự chứng minh recency. Output Link URL gồm post hoặc video; keyword lọc từ nội dung/nguồn đã khai báo, hashtag cần evidence trong nội dung. `fb_group_1675953926771851` đã có pilot live đọc được public Story metadata: đúng post_id + creation_time, caption, window hôm nay. Bài `1819342645766311` đăng `2026-10-08T12:26:03Z` (19:26:03 giờ Việt Nam), 1 candidate persist, unknown_time=0. [Bằng chứng pilot](../../reports/facebook-native-time-pilot/report.json). Không chứng minh coverage đủ cả group hoặc cả bảy seeds; TikTok chưa được xác nhận live.

Parser Facebook đọc Story metadata công khai trong trang, không replay API riêng. Chỉ nhận timestamp từ Story của đúng native post ID; comment_id/reply_comment_id và timestamps từ nested comment bị loại; timestamp xung đột không được nhận. Google date filter chỉ hỗ trợ discovery. Bộ kiểm thử freshness/parser: 8 dashboard + 51 acquisition + 5 Chromium fixture; live pilot là evidence riêng, không dùng fixture để chứng minh crawl live.

## Kiểm thử acquisition

```powershell
.\.venv\audit\Scripts\python.exe -m unittest discover -s tests -v
$env:ACQUISITION_BROWSER_TESTS='1'
.\.venv\audit\Scripts\python.exe -m unittest tests.integration.test_acquisition_browser -v
Remove-Item Env:\ACQUISITION_BROWSER_TESTS
```

Browser tests dùng profile tạm và HTML giả lập được intercept toàn bộ, không gọi Facebook/TikTok live. Không lấy kết quả đó làm live acceptance. Khi probe yêu cầu auth, CAPTCHA, parser mismatch hoặc invalid key, giữ outcome thật; nguồn khác vẫn tiếp tục. Operator sửa tài nguyên/config rồi rerun, không xóa DB để che lỗi hay reset quota.
