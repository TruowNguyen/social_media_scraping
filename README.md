# Social Listening VinCons

Repository độc lập: [TruowNguyen/social_media_scraping](https://github.com/TruowNguyen/social_media_scraping), public, branch mặc định `dev`. Ngày 12/10/2026 khởi tạo lịch sử Git mới từ snapshot code hiện hành; `main` và `dev` bắt đầu cùng snapshot. [Nguồn gốc code](docs/code-origin.md) được ghi riêng trong tài liệu.

Tài liệu hiện hành: [bàn giao dev 12/10](docs/development-handoff-20261012.md), [trạng thái code/config](docs/current-state.md), [Dashboard workspace](docs/operations/dashboard-workspace.md) và [đồng bộ đa nền tảng](docs/operations/workspace-platforms-20261012.md).

Ngày 14/10: [sửa theo dõi Facebook Chạy ngay](docs/operations/facebook-direct-reconnect-20261014.md), tiến độ từng group/bài/bình luận, đọc trạng thái độc lập và giữ kết quả khi kết nối lỗi tạm thời.

Thu thập nội dung Facebook, tìm kiếm Threads theo dự án và tìm link mạng xã hội qua Google để theo dõi phản ánh liên quan VinCons và VinWonders Vũ Yên. Dự án có giao diện local, acquisition engine, Source Registry, exclusion rules, SQLite lưu nội dung/lineage và lịch crawl hằng ngày riêng từng nền tảng.

Hướng dẫn dành cho workspace Windows `D:\task\social_listening\social_media_scraping`, đồng bộ với code/config ngày **12/10/2026**. Trạng thái và bằng chứng chi tiết: [TODO.MD](TODO.MD). Các báo cáo có ngày là snapshot của lượt kiểm tra đó.

Dashboard dùng [luồng crawl raw v2](docs/operations/dashboard-raw-v2.md): bài viết → bình luận/phản hồi → lưu raw → OCR ảnh bài → filter từng nội dung → [worker phân loại Gemini](docs/operations/classification-worker.md). Nút crawl và lịch không còn chạy crawler Facebook v1. Kho dữ liệu hỗ trợ loại nội dung, đánh giá/ghi chú và Excel; tab Phản ánh có bộ lọc group, dự án, vấn đề, intent và ngày riêng của từng nội dung. Worker hỗ trợ chế độ nền `--serve`, mặc định poll 15 giây; trạng thái tiến trình xem trên dashboard. Từ 13/10/2026 có [supervisor local và chạy bù](docs/operations/local-runtime-recovery.md), tự bật dashboard/classifier khi đăng nhập Windows.

Đã hợp nhất vào **một DB hoạt động**: `sessions/acquisition/acquisition.sqlite3`. Raw, phân loại, đánh giá, lịch sử v1 và Google discovery dùng chung file; các bảng có chức năng riêng. File `sessions/conversations-v2.sqlite3` cũ đã bỏ sau backup và kiểm tra integrity/FK. Xem [hợp nhất và crawl 14 ngày](docs/operations/unified-database-backfill.md).

Phạm vi lựa chọn gồm **VinCons (tổ chức)** và **VinWonders Vũ Yên**. Chọn phạm vi trong lịch để giới hạn group; lựa chọn trống chạy tất cả group đang bật (hiện 14 group). Group chỉ là ngữ cảnh, không chứng minh nội dung phản ánh thuộc dự án. Pilot raw v2 thật ngày 09/10 đã lưu 6 bình luận; chưa xác nhận coverage toàn group hoặc đầy đủ replies.

## 1. Chạy nhanh trên máy hiện tại

Để tự chạy khi đăng nhập Windows, cài một lần:

```powershell
Set-Location 'D:\task\social_listening\social_media_scraping'
.\scripts\Install-LocalRuntime.ps1
```

Tác vụ `SocialListeningRuntime` chạy nền, giữ dashboard và classifier độc lập, tự thay worker đã kết thúc và chạy bù ca đã đóng trong tối đa 7 ngày có lịch sử cấu hình. Lần cài đầu chỉ đối soát hôm nay. Không cần mở riêng hai terminal. Máy tắt/ngủ không crawl được; khi hoạt động lại sẽ đối soát lịch và dữ liệu đang chờ. Xem [hướng dẫn vận hành](docs/operations/local-runtime-recovery.md) để kiểm tra trạng thái, tắt tự khởi động hoặc chạy thủ công.

Mở PowerShell, dùng venv `.venv\audit` đã cài sẵn:

```powershell
Set-Location 'D:\task\social_listening\social_media_scraping'
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.acquisition_cli validate
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.dashboard
```

Mở **[http://127.0.0.1:8765](http://127.0.0.1:8765)**. Giữ cửa sổ PowerShell chạy; `Ctrl+C` dừng backend. Không cần activate venv khi dùng đường dẫn Python như trên.

Chỉ chạy **một backend** cho cùng database/profile. Nếu giao diện đang mở được, dùng server hiện tại. Sau khi cập nhật code, khởi động lại backend rồi nhấn `Ctrl+F5` trên trình duyệt.

## 2. Chức năng hiện có

| Chức năng | Cách lấy dữ liệu | Phạm vi hiện tại |
| --- | --- | --- |
| Facebook group | Raw v2 + Playwright/Chromium, profile Facebook riêng | 14 group VERIFIED/enabled, 7 VinCons + 7 Vũ Yên; chưa xác nhận coverage đầy đủ |
| Tìm kiếm Google | Engine + **SerpApi API**, keyword/hashtag | Tìm link Facebook/TikTok/YouTube; nguồn mới vào discovery queue |
| Thu thập Threads | **Playwright + Chrome**, query theo dự án | POST/REPLY, kho chung, lịch nhiều dự án; LIVE_PARTIAL |
| TikTok keyword/hashtag | Adapter browser riêng | Có runtime/offline tests; chưa đạt live acceptance, chưa có tab TikTok trực tiếp |
| Lịch Facebook | Scheduler trong tiến trình dashboard | Hai khung hằng ngày, tránh chạy chồng, lưu lịch để khôi phục |
| Collector legacy | Runtime riêng của sáu nền tảng | [Tài liệu legacy](docs/legacy-collectors.md), schema/cấu hình riêng |

Dashboard raw v2 đã thu POST/COMMENT/REPLY, OCR ảnh bài, nối classifier và xuất Excel theo phiên kết quả. Acquisition CLI v1/Google discovery vẫn không tự chạy comments, ASR hoặc LLM. Export workspace chưa thay exporter bốn sheets theo PRD v1. Không suy dự án/vị trí hoặc vấn đề từ tên group hay Google snippet.

## 3. Cài đặt trên môi trường mới

Dùng Python **3.12 hoặc 3.13**; workspace hiện tại dùng 3.13.13. Facebook/Google acquisition không cần GPU hoặc model NLP.

### Tạo venv và cài dependency

```powershell
Set-Location 'D:\task\social_listening\social_media_scraping'
py -3.13 -m venv .venv\audit
.\.venv\audit\Scripts\python.exe -m pip install -r requirements-acquisition.txt
.\.venv\audit\Scripts\python.exe -m pip install --no-deps -e .
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Get-Location) '.venv\playwright-browsers'
.\.venv\audit\Scripts\python.exe -m playwright install chromium
```

Chỉ tạo venv nếu chưa có. `requirements-acquisition.txt` bao gồm core và browser requirements. Nếu chưa có Python 3.13, dùng bản Python 3.12/3.13 có sẵn thay cho `py -3.13`.

**Venv hiện tại được tạo bằng uv, không có module pip.** Khi cần cài lại dependency trong venv này:

```powershell
uv pip install --python .\.venv\audit\Scripts\python.exe -r requirements-acquisition.txt
uv pip install --python .\.venv\audit\Scripts\python.exe --no-deps -e .
```

YouTube bridge/collector legacy cần thêm dependency từ `requirements.txt`:

```powershell
uv pip install --python .\.venv\audit\Scripts\python.exe -r requirements.txt
```

NLP/Whisper là phần tùy chọn trong `requirements-models.txt`; FFmpeg/models có hướng dẫn ở [legacy collectors](docs/legacy-collectors.md). Không cần cài phần này chỉ để crawl Facebook. OCR ảnh bài cần thêm `requirements-ocr.txt` và binary/traineddata Tesseract theo [runbook OCR](docs/operations/facebook-image-ocr.md).

### Cấu hình môi trường

Tạo `.env` từ template nếu chưa có, giữ nguyên file hiện hữu:

```powershell
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
```

Đặt key trong `.env` nếu dùng tab Google:

```dotenv
SERPAPI_API_KEY=your_local_key
```

Facebook crawl/lịch không cần SerpApi key. Worker phân loại cần `GEMINI_API_KEY`, `GEMINI_API_BASE_URL`, `GEMINI_MODEL` trong `.env`/environment; OCR local không cần key. `.env`, `sessions/`, database và runtime reports được ignore; không đưa key/cookies/session vào source config hoặc Git. Biến môi trường của tiến trình có thể ghi đè `.env`; sau khi thay key, kiểm tra nguồn cấu hình và khởi động lại backend.

## 4. Chuẩn bị phiên Facebook

Mở Chromium riêng của dự án để đăng nhập thủ công:

```powershell
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.browser_session --platform facebook --login
```

Đăng nhập, kiểm tra vào được group, **đóng browser và chờ lệnh kết thúc** trước khi crawl. Phiên lưu tại `sessions/browser/facebook/`, được tái sử dụng ở các lượt sau. Login command mở lại trang Facebook đầu tiên không đồng nghĩa bị đăng xuất.

Không mở login command khi job Facebook đang giữ profile. Nếu gặp login/CAPTCHA/access denied, xử lý thủ công rồi chạy lại; adapter không bypass. Chưa kiểm chứng anonymous access cho toàn bộ group, nên cấu hình hiện tại dùng phiên đã đăng nhập.

Smoke test sau chỉ kiểm tra Chromium trên trang local, không chứng minh truy cập Facebook:

```powershell
.\.venv\audit\Scripts\python.exe -m engine.browser_session --platform facebook --smoke
```

Chi tiết: [browser bootstrap](docs/operations/browser-bootstrap.md), [runbook acquisition](docs/operations/acquisition-runbook.md).

## 5. Sử dụng giao diện

Giao diện mở ở **Phản ánh**. Bốn tab là **Phản ánh / Kho dữ liệu / Thu thập / Tìm link Google**. Hướng dẫn và giới hạn nghiệm thu: [Dashboard workspace](docs/operations/dashboard-workspace.md).

- **Phản ánh:** chọn bộ lọc, bấm **Áp dụng bộ lọc**; có lựa chọn nhanh Giữ / Cần xem xét / Loại / Chưa phân loại. Mở một nội dung để đọc bài gốc, bình luận/trả lời và lưu đánh giá riêng với model. Nút xử lý hàng chờ chạy một lượt tối đa 10 nội dung **toàn hệ thống**, không giới hạn theo bộ lọc bảng.
- **Kho dữ liệu:** raw được lưu trước khi filter/classify, có POST/COMMENT/REPLY, kể cả nội dung bị loại. Bộ lọc theo ngày đăng riêng của node, có lần thu trong khoảng hoặc lần thu mới nhất; ngày hiển thị theo giờ Việt Nam. Không suy bài thuộc window khi chưa xác minh thời gian.
- **Đánh giá / ghi chú:** có nháp theo nội dung trên máy, danh sách mở lại nháp, kiểm tra xung đột giữa các phiên và đánh giá hàng loạt tối đa 100 mục. Lưu rồi **Làm mới dữ liệu** để nhận đánh giá mới vào phiên bảng.
- **Xuất Excel:** xuất mọi trang của đúng phiên kết quả đã áp dụng, giữ số dòng/thứ tự/thời điểm chốt. Không đưa bộ lọc chưa áp dụng hoặc nháp vào Excel. Tách kết quả model, đánh giá, ghi chú, nguồn và metadata; có sheet Phạm vi.
- **Thu thập:** Chạy ngay / Lịch hằng ngày / Lịch sử / Nguồn theo dõi. Dùng Playwright và phiên Facebook; không dùng SerpApi. Đổi input không thay đổi phạm vi kết quả lượt đã chạy.
- **Tìm link Google:** keyword/hashtag gợi ý hoặc tự nhập, tối đa ba giá trị mỗi nhóm, mặc định hôm nay; dùng SerpApi. Nguồn mới phải qua duyệt, search không chứng minh đã thu mọi bài trong ngày.

Desktop dùng bảng; mobile mặc định danh sách, có bộ lọc thu gọn và chi tiết toàn màn hình. Bảng giữ phiên trong lúc đọc; kiểm tra dữ liệu mới chỉ thông báo, không xóa editor/nháp đang dùng. Bộ lọc và xem dữ liệu không gọi crawler hoặc model.

## 6. Lịch crawl hằng ngày

Trong tab **Thu thập**, mục **Lịch hằng ngày** có hai khung giờ và chu kỳ. Lịch raw v2 đã lưu trên workspace, đọc lại ngày 11/10/2026:

| Khung giờ Việt Nam | Mốc chạy với chu kỳ 45 phút |
| --- | --- |
| 05:00–08:30 | 05:00:01, 05:45, 06:30, 07:15, 08:00, **08:30 (chốt)** |
| 17:00–18:30 | 17:00:01, 17:45, **18:30 (chốt)** |

- **Bật / cập nhật lịch** lưu khung/chu kỳ; **Tắt lịch** ngăn lượt tiếp theo, lượt đang chạy được hoàn tất.
- Lặp mỗi ngày, ngoài khung không bắt đầu lượt mới. Backend mở lại ngoài khung chờ khung tiếp theo, không replay lượt bỏ lỡ.
- Mỗi job lấy bài từ đầu khung đến thời điểm chạy theo `[start,end)`; lưu UTC, hiển thị giờ Việt Nam. Window không mở rộng khi browser chạy lâu.
- Lịch v2 thêm lượt chốt cuối khung, kể cả 08:30 không nằm trên grid 45 phút. Mốc mở chờ 1 giây để window không rỗng.
- Crawl dashboard giới hạn **100 candidate inventory/group, 20 thread/group, tối đa 120 giây/group, 1.200 giây/run**; budget nguồn được chia theo thời gian còn lại, chưa đảm bảo thu hết feed/comments/replies.

**Giữ máy và backend chạy để lịch hoạt động.** Scheduler này chưa phải Windows service và không đánh thức máy sleep. Chỉ chạy một backend cho cùng database/profile. Lịch lưu ở `sessions/acquisition/dashboard-schedule.json`; xem trạng thái thực tế trên UI hoặc:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/schedule'
```

Chi tiết và giới hạn: [dashboard schedule](docs/operations/dashboard-crawl-schedule.md).

## 7. Rule loại nội dung

Rule `NO_SALES_RECRUITMENT_BUY_SELL_EXCHANGE` loại intent rõ ràng: **tuyển dụng, bán hàng, mua bán, bất động sản, thuê, vay nợ và trao đổi hàng hóa**.

**Dashboard raw v2** lưu raw trước filter/classify, kể cả DROP. Intent bài cha không loại comments/replies; OCR ảnh bài có evidence riêng. **Acquisition v1/Google routing** áp dụng rule trước deep fetch, kiểm tra lại sau fetch và trước reuse/output; clear DROP chỉ giữ bảy trường rejection audit, không lưu raw. Complaint, cảnh báo lừa đảo, nợ lương, trao đổi ca làm hoặc intent mơ hồ giữ REVIEW. Tên group chứa “tuyển dụng” không loại toàn bộ nguồn. PASS/REVIEW không phải kết luận relevance nghiệp vụ.

Đây là heuristics, có thể bỏ sót cách diễn đạt mới; không tuyên bố nhận hết mọi bài tuyển dụng. Cấu hình: [exclusions.yaml](config/exclusions.yaml); implementation: [prefilter.py](src/acquisition/prefilter.py).

## 8. Chạy CLI và xuất dữ liệu

Kiểm tra cấu hình/nguồn, không crawl:

```powershell
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli validate
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli sources list
```

Ví dụ raw v2 quét một thread đã duyệt trong **09/10/2026 05:00–08:30 VN**, với UTC tương ứng; post cha có thể cũ hơn window:

```powershell
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.conversation_cli --db sessions/acquisition/acquisition.sqlite3 scan-thread --source-id fb_group_139108668844789 --post-url 'https://www.facebook.com/groups/139108668844789/posts/987006180721696' --start '2026-10-08T22:00:00Z' --end '2026-10-09T01:30:00Z' --seconds 120
```

Lệnh trên lưu raw v2, không tự gọi Gemini nếu không thêm `--classify`. Không chứng minh đủ coverage của thread/window. Tắt lịch trước khi vận hành browser thủ công nếu lịch có thể đến hạn. `acquisition_cli run` vẫn là CLI **v1/post-only**; truyền `--source-id` để giới hạn provider, vì bỏ tùy chọn này có thể chạy cả Google và tiêu thụ API quota.

Xuất **toàn bộ acquisition v1 records/observations hiện lưu**, không giới hạn riêng run hay khoảng ngày; đây không phải export raw conversation/classification v2. Xuất Excel v2 từ phiên kết quả đã áp dụng trên dashboard:

```powershell
New-Item -ItemType Directory -Force -Path reports | Out-Null
.\.venv\audit\Scripts\python.exe -m engine.acquisition_cli export --output reports\acquisition-export.json
```

Lệnh probe/verify/enable/disable nguồn, duyệt queue và dispatch: [runbook acquisition](docs/operations/acquisition-runbook.md). `social-acquire` là entry point tương đương sau khi cài package; xem `--help`.

## 9. Cấu trúc và dữ liệu

```text
engine/                       Điều phối, CLI, Registry, dashboard và scheduler
src/acquisition/              Adapter, browser, identity, models và prefilter
src/storage/                  SQLite acquisition/raw v2, revisions, evidence, observations
src/analysis/                 Taxonomy, classification contract, gateway và intent
src/media/                    OCR và media helpers
src/collectors/               Sáu collector legacy
config/                       Sources, watchlists, projects, acquisition, taxonomy runtime
specs/                        Feature specs, contracts, traceability PRD
tests/                        Contract, integration, architecture checks
docs/                         Runbooks, thiết kế và bằng chứng
sessions/browser/facebook/    Profile Facebook local
sessions/browser/tiktok/      Profile TikTok local
sessions/acquisition/         acquisition.sqlite3 và dashboard-schedule.json
reports/                      Export, report, preview local (gitignored)
```

Dependency đi từ `engine` đến `src`; acquisition không thay schema/output legacy. Identity dùng platform + native ID, fallback URL chuẩn hóa; nhiều lần phát hiện lưu thành observations. Nội dung rỗng không được dùng để gộp bài khác nhau. Database/profile được giữ qua các lần chạy; không xóa để “reset” nếu cần giữ dữ liệu và phiên đăng nhập.

## 10. Kiểm tra và xử lý lỗi

Chạy suites offline theo CI (browser fixtures opt-in mặc định skip):

```powershell
.\.venv\audit\Scripts\python.exe -X utf8 -m unittest discover -s tests -q
```

Browser fixtures là nhóm opt-in qua `ACQUISITION_BROWSER_TESTS=1`. Offline tests không chứng minh live coverage, model accuracy hoặc scheduler đã ổn định nhiều ngày.

| Hiện tượng | Cách xử lý |
| --- | --- |
| Không mở được localhost | Kiểm tra terminal/dashboard và đúng cổng; đọc lỗi bind trước khi mở thêm server |
| Chưa thấy UI mới | Restart backend sau cập nhật code, rồi `Ctrl+F5` |
| `No module named pip` | Venv hiện tại dùng `uv pip install --python ...` ở mục 3 |
| Chromium executable thiếu | Cài Chromium vào đúng `PLAYWRIGHT_BROWSERS_PATH` như mục 3 |
| Profile đang được sử dụng | Đóng login browser/job giữ profile; không xóa profile hoặc mở đồng thời |
| Facebook login/CAPTCHA | Tắt lịch nếu cần, xác minh thủ công, đóng browser rồi chạy lại |
| Google key/quota lỗi | Kiểm tra `.env`/process environment và quota provider; Facebook không phụ thuộc key này |
| Không có kết quả | Đối chiếu ngày, exclusion, source enabled và outcome; không đồng nghĩa group không có bài |
| Lịch không chạy | Kiểm tra enabled/next_run, giờ Việt Nam, máy sleep, backend đã dừng hoặc service bận |

Tham khảo: [chỉ mục tài liệu](docs/README.md), [config](config/README.md), [specs](specs/README.md), [TODO](TODO.MD), [refactor lịch sử](docs/refactor-summary.md), [legacy collectors](docs/legacy-collectors.md). Report trong `reports/` là artifact của workspace local, không được cam kết có trong checkout mới.

## Duyệt phản ánh

Tab **Phản ánh** có các bộ lọc chính: từ khóa, dự án theo dõi, group, nhóm vấn đề, kết quả và khoảng ngày. Bảng tách riêng taxonomy, ý định, kết quả phân loại và trạng thái xử lý; bộ lọc kỹ thuật OCR/chất lượng nằm trong **Kho dữ liệu**. Xem [ánh xạ bộ lọc với backend và hướng dẫn sử dụng](docs/operations/reflections-workspace.md). Sau khi cập nhật giao diện, tải lại trang và bấm **Làm mới dữ liệu** để tạo phiên kết quả mới.

## Thu thập Threads

Threads đã triển khai tìm kiếm theo truy vấn dự án bằng **Playwright + Chrome**, thu bài viết/trả lời, lưu raw vào kho chung trước filter/classify và dùng Gemini theo batch. Trong tab **Thu thập**, chọn Facebook hoặc Threads; nguồn/query, lượt chạy và lịch độc lập. Kho dữ liệu/Phản ánh có bộ lọc nền tảng, nguồn/truy vấn và export Excel.

**VinCons 13/10:** ưu tiên `"VinCons"` và truy vấn theo kẹt cổng/tan ca/chấm công/nhận diện khuôn mặt; giữ query rộng để đối chiếu. Parser xác minh truy vấn/vùng kết quả; raw được lưu trước khi hoãn fetch/rescan bài không có evidence dự án. Tối đa hai hội thoại thiếu evidence/query; alias đúng chưa đồng nghĩa là phản ánh. [Luồng, pilot và giới hạn](docs/operations/threads-vincons-scope-20261013.md).

**Giao diện 12/10:** trạng thái đầu trang và nguồn/chi tiết ghi rõ Facebook/Threads. **Thu thập → Threads → Lịch hằng ngày** chọn nhiều dự án; hiện đã lưu VinCons và VinWonders Vũ Yên, hai ca 05:00–08:30 và 17:00–18:30, 45 phút. **Nguồn theo dõi** cho biết số nội dung/lượt gần nhất từng truy vấn; Snapshot mới đã có dữ liệu qua truy vấn VinCons; chưa nghiệm thu tính liên quan/coverage. [Kiểm chứng](docs/operations/workspace-platforms-20261012.md).

Pilot thật theo `VinWonders Vũ Yên` đã lưu 43 nội dung (4 bài viết, 39 trả lời), trạng thái **LIVE_PARTIAL**: chưa chứng minh thu hết khoảng thời gian hoặc toàn bộ trả lời lồng nhau. Xem [hướng dẫn chạy và bằng chứng](docs/operations/threads-acquisition.md), [TODO](TODO.MD), [plan P0–P7](docs/implementation-plan-threads.md). Provider API và OCR Threads chưa nghiệm thu. Tên `RAW_V2_THREADS` vẫn chỉ chế độ hội thoại Facebook cũ.

## Đọc chữ trong ảnh Facebook

Dashboard tách cột **Nguồn** và **Nội dung**, đồng thời phân biệt thiếu văn bản/OCR, đang chờ và kết quả cần phân loại lại. Có thể chuẩn bị hàng chờ mà không gọi model bằng `python -m engine.classification_worker --prepare-only`; xem [kiểm tra hàng chờ và các nội dung chưa phân loại](docs/operations/classification-miss-audit-20261010.md).

Từ 11/10/2026, classifier dùng model cấu hình `ag/gemini-3.8-flash-low`; worker nền kiểm tra hàng chờ mỗi 15 giây. Đổi model mặc định giữ các kết quả đã được chấp nhận nếu đầu vào và taxonomy/prompt/rule còn khớp, đồng thời giữ model gốc trong lịch sử. [Triển khai và kiểm chứng chuyển model](docs/operations/classification-worker.md#chuyển-model-và-giữ-kết-quả--11102026).

Crawler đã nối OCR ảnh đính kèm bài vào kho raw v2. Caption và chữ trong ảnh được lưu riêng; classifier nhận evidence OCR có nguồn gốc và chất lượng. Chưa OCR ảnh bình luận/phản hồi hoặc video. Chi tiết nội dung có **Chữ trong ảnh**, bộ lọc OCR và export Excel sheet evidence.

```powershell
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.image_ocr_cli --probe
```

Hướng dẫn cài engine, thu lại ảnh từng bài và giới hạn pilot tại [runbook OCR](docs/operations/facebook-image-ocr.md). Pilot Facebook thật đã đọc ảnh; phân loại live chỉ đạt khi Gemini trả kết quả qua validation, không tính HTTP 503 là thành công.
