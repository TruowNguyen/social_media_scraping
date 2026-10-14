# Worker phân loại Gemini và intent quảng cáo/bán hàng

Ngày 09/10/2026. Phạm vi: raw conversation v2 đã lưu → filter → jobs/batching → Gemini gateway → validator → analysis → tab kết quả. Không xác nhận Facebook đã thu hết comments hoặc classifier đạt metric nghiệp vụ trên held-out.

## Đầu vào, mục tiêu, output nghiệm thu

- Đầu vào: `sessions/acquisition/acquisition.sqlite3` hoặc DB v2 chỉ định; POST/COMMENT/REPLY có text, context/revisions; runtime taxonomy `config/taxonomy/v1`; `.env` chứa GEMINI_API_KEY, GEMINI_API_BASE_URL, GEMINI_MODEL hiện có.
- Mục tiêu: tự nhận raw mới/context thay đổi, phân loại từng node độc lập, chống duplicate/retry vô hạn; phân biệt intent thương mại với vấn đề dự án.
- Output: filter audit có nhãn intent; jobs/leases/backoff; `node_analyses` chỉ chứa result hợp lệ; telemetry không key/cookie; UI table lọc relevance/intent và đọc lý do. Raw/reviews không bị xóa khi DROP hoặc API lỗi.

## Quảng cáo khác bán hàng

[Intent taxonomy riêng](../../specs/taxonomy/content-intents-v1.yaml) tách khỏi taxonomy vấn đề dự án:

| Intent | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| ADVERTISING | Quảng bá thương hiệu/sản phẩm/dịch vụ/chiến dịch | Giới thiệu dịch vụ mới, ưu đãi khai trương, trải nghiệm ngay |
| SALES | Chào bán/đặt hàng/đặt vé cụ thể | Bán vé 300k, inbox đặt vé |
| COMPLAINT | Phản ánh thực tế, có thể nhắc nội dung thương mại | Quảng cáo nói vào nhanh nhưng tôi chờ 40 phút chưa vào được |

Một node có thể có nhiều nhãn ADVERTISING + SALES + COMPLAINT. Pure ads/sales/recruitment/rental/trade/loan/exchange bị loại khỏi phản ánh; raw vẫn giữ. Mention đơn lẻ, phủ định, hỏi/cảnh báo hoặc complaint được giữ REVIEW để đánh giá tiếp. Intent của cha không quyết định con. Filter deterministic không tự xác nhận complaint từ keyword; LLM phải đưa issue/evidence thật.

`content_intents` là trường additive của `classification-result-v2`: optional để đọc output v2 cũ, bắt buộc đối với worker live mới. Validator từ chối DROP + COMPLAINT và KEEP thương mại không có COMPLAINT. OCR POST nối vào `image_evidence` riêng, có quality/provenance; không gộp caption. OCR TARGET chưa chắc chắn yêu cầu review; OCR cha có ngoại lệ DROP thương mại độc lập theo [chính sách v3](filter-policy-v3-20261011.md). [Contract hiện hành](classification-contract-v2.md), [runbook OCR](facebook-image-ocr.md).

## Runtime và API

Runtime taxonomy 1.0.0 được tạo từ baseline người dùng đã chấp nhận, ghi approval provenance; bản review draft dưới specs giữ nguyên. Đây là cho phép dùng scope để triển khai, không thay acceptance chất lượng của mentor/held-out.

Gateway đang cấu hình dùng `/v1/chat/completions`, model `ag/gemini-3.8-flash-low` từ 11/10/2026, thay tuyến `ag/gemini-3.7-flash-low` từng trả HTTP 503. Shape giao thức tương thích tham chiếu [Google Gemini OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai); không tuyên bố gateway bên thứ ba là API Google trực tiếp hoặc mọi giới hạn model đã được xác nhận.

API timeout 45 giây; tối đa 3 attempts/job với backoff 30/60 giây; auth/config/protocol lỗi không retry vô hạn. Input batch dùng byte bound thận trọng, tối đa 10 items nhưng giữ output reserve nên có thể ít hơn. Output cutoff/invalid JSON/schema/evidence không được accepted. Các item partial hợp lệ lưu riêng; missing/invalid retry riêng. Oversized giữ raw và trạng thái OVERSIZED. Money budgets vẫn deferred theo yêu cầu; usage được lưu telemetry.

## Chuyển model và giữ kết quả — 11/10/2026

**Cập nhật 14/10/2026:** metadata-only revision không còn khiến mất kết quả accepted hoặc gọi model lại khi caption/context/OCR và binding phân loại không đổi. Queue so bằng chứng riêng với revision lưu trữ, giữ provenance thật; dashboard ưu tiên accepted còn hợp lệ thay vì PENDING trùng. Worker vẫn đối soát toàn kho local. [Chẩn đoán, bản sửa và nghiệm thu 18 → 17 → 18](classification-keep-count-20261014.md).

Đối soát tự động giữ kết quả DONE đã được chấp nhận khi target, context, OCR, taxonomy, prompt và rule binding vẫn khớp, dù model mặc định thay đổi. Kết quả giữ nguyên model thực tế đã tạo ra nó; không sao chép hoặc đổi tên model trong provenance. Thay đổi đầu vào hoặc binding vẫn tạo job mới. Các đầu vào chưa có kết quả hợp lệ được đưa vào hàng chờ của model mới; các job/model cũ vẫn giữ lịch sử. `enqueue` trực tiếp vẫn tạo binding riêng nếu chủ động làm thử nghiệm so sánh model.

Đã sao lưu tại `sessions/backups/model-switch-20261011.sqlite3`. Đối soát giữ 961 kết quả hợp lệ, tạo 1.539 job mới; 306 nội dung thiếu text/OCR và 163 nội dung bị bộ lọc loại không được gửi model. Đây là số liệu tại thời điểm đối soát, không phải tổng số phản ánh.

Kiểm chứng offline theo [audit đồng bộ tài liệu](../documentation-drift-audit-2026-10-11.md). Pilot ngày 11/10: batch synthetic 2 nội dung được chấp nhận; một lượt dữ liệu thật 10 nội dung chia 2 request (6 + 4), đều HTTP 200, 10 kết quả vượt validator, không item lỗi. [Synthetic probe](../../reports/classifier-api-recheck-20261011.json), [queue reconciliation](../../reports/model-switch-20261011-queue.json), [live cycle](../../reports/model-switch-20261011-live-cycle.json). Mẫu này không xác nhận accuracy hoặc full batch/provider acceptance.

Dashboard đã khởi động lại để đọc cấu hình mới; worker nền dùng `--serve --poll-seconds 15`, tự nhận dữ liệu đủ điều kiện. Khoảng 15 giây là nhịp kiểm tra hàng chờ, không phải thời gian hoàn thành mỗi lượt. Tiến trình chưa đăng ký tự khởi động cùng Windows. Xem trạng thái hiện tại ở `/api/health`, log `reports/classifier-model-20261011.out.log` và `.err.log`; report gần nhất là `reports/model-switch-20261011-worker-latest.json`. Sau bản sửa ngày 11/10, `classification.counts` trong health đếm trạng thái hiện hành của từng node; `job_counts` đếm cả lịch sử.

**Cập nhật sau phục hồi ngày 11/10:** người dùng cho phép Gemini phân loại toàn hàng chờ. Đã phục hồi 195 đầu vào, xử lý hết hàng chờ: 2.692 DONE / 2.969 node (90,67%), 166 FILTER_DROP và 111 MISSING_TEXT; không còn PENDING/RUNNING/FAILED hiện hành. Cả 67 job lỗi cũ đã DONE. 342 request HTTP 200, gồm xử lý các response JSON/protocol lỗi và kiểm tra riêng 6 item đạt ở lần thử cuối. DONE hợp lệ và reviews được giữ; không coi completion là accuracy. Người dùng sau đó cho phép chạy liên tục, gửi caption/comment, OCR và ngữ cảnh mới/thay đổi từ các lượt crawl sau này. Worker đã khởi động lại, health ACTIVE; đối soát giữ 2.692 DONE, `NO_PENDING_JOBS`, không gọi API khi không có đầu vào mới. Chưa đăng ký tự khởi động cùng Windows. Log hiện hành: `reports/classifier-recovery-20261011.out.log` và `.err.log`; report: `reports/classifier-recovery-20261011-worker-latest.json`. [Bằng chứng chạy liên tục](../../reports/classifier-continuous-enabled-20261011.json), [biên bản, scope và kết quả](facebook-recovery-classification-20261011.md), [nguyên nhân OCR](classification-diagnosis-20261011.md).

## Lệnh chạy

```powershell
Set-Location 'D:\task\social_listening\social_media_scraping'

# Phân loại một lượt tối đa 10 nội dung đủ điều kiện; giữ DONE còn hợp lệ
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.classification_worker

# Xem kết quả đã lưu, không gọi model
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.classification_worker --results

# Worker tự nhận raw mới; terminal còn mở thì tiếp tục chạy
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.classification_worker --serve --poll-seconds 15

# Luồng crawl v2 theo hai khung mỗi ngày, classify sau khi commit raw
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.conversation_cli --db sessions/acquisition/acquisition.sqlite3 serve --source-id fb_group_139108668844789 --first-day 2026-10-09 --classify

# Dashboard đọc cùng DB; tab Phản ánh có nút chạy một lượt toàn hệ thống
.\.venv\audit\Scripts\python.exe -X utf8 -m engine.dashboard --conversation-db sessions/acquisition/acquisition.sqlite3
```

Chỉ dùng một kiểu vận hành worker: serve của crawler có `--classify`, worker độc lập, hoặc nút một lượt. Lease/idempotency bảo vệ trùng job, nhưng không cần bật nhiều dispatcher. Ctrl+C dừng service; raw/jobs/checkpoints giữ trong SQLite. Chưa đăng ký tự khởi động cùng Windows.

**DB mặc định đã hợp nhất** vào `sessions/acquisition/acquisition.sqlite3`; [migration](unified-database-backfill.md) giữ raw/observations/reviews/job-analysis history và map record Facebook cũ. Worker nhận raw khi đủ caption hoặc OCR evidence; identity không nhân raw. Nút crawl/lịch dashboard dùng raw-first v2; [workspace](dashboard-workspace.md) đã có hội thoại phân trang và reviews. Coverage toàn watchlist/UAT chưa nghiệm thu; trạng thái worker thực xem health.

## Bằng chứng và trạng thái nạp chạy

- Offline cuối: **180 contract tests pass**; 1 Chromium UI fixture test sau sửa layout pass (table/relevance/intent filters). [Report tổng](../../reports/classification-integration-validation.json).
- API thật: [pilot](../../reports/classification-gemini-live-pilot.json) và [kho dùng chung](../../reports/classification-shared-live-validation.json): HTTP 200, 1 accepted item mỗi lượt; không phải test batching nhiều items live hoặc đánh giá accuracy.
- Bài native có caption 54 ký tự, model trả INFORMATIONAL / DROP vì target text không chứa phản ánh. Hình ảnh quảng cáo khoản vay chưa OCR, nên không gán LOAN_DEBT từ ảnh.
- [Rerun](../../reports/classification-rerun-validation.json): 0 jobs mới, 0 API calls. Hai analysis histories do thay binding phiên bản; UI chọn một analysis hiện hành, không nhân raw.
- [Browser UI validation](../../reports/classification-dashboard-validation.json): server tạm scheduler tắt, tab/table/filter pass, không gọi model trong UI test.
- Người dùng đã cho phép restart dashboard và bật worker nền. Ngày 09/10/2026 đã triển khai dashboard tại `http://127.0.0.1:8765` và worker `--serve` kiểm tra job mỗi 15 giây trên kho raw v2 dùng chung. Kiểm tra giao diện sau triển khai: 4 tab, 1 bản ghi phân loại hiện tại; worker báo `NO_PENDING_JOBS`, không gọi lại API cho job đã hoàn thành. Biên bản: `reports/classification-integration-validation.json`. Chưa đăng ký tự khởi động cùng Windows.
# Ngôn ngữ lý do trên giao diện — 10/10/2026

Gateway yêu cầu phần giải thích của model (drop_reason, review_reason, issue summary) bằng tiếng Việt có dấu; keys/enums/IDs và evidence nguyên văn vẫn giữ theo contract. Dashboard hiển thị `reason_vi` chuẩn hóa từ relevance và content_intents, áp dụng cả kết quả lịch sử dùng tiếng Anh và FILTER_DROP. Đây là mô tả tiếng Việt của quyết định đã lưu, không phải bản dịch nguyên văn lý do gốc. Không thay đổi relevance, intent, raw hoặc payload analysis lịch sử; không cần phân loại lại dữ liệu cũ chỉ để đổi ngôn ngữ hiển thị.

Cập nhật bộ lọc v3 ngày 11/10: `reason_vi` giữ lý do tiếng Việt có dấu thực tế từ model, dùng fallback nhãn tiếng Việt cho lịch sử tiếng Anh. Provider/validator phân biệt OCR target và context. 2.254 DONE được giữ, 416 đầu vào được đưa vào hàng chờ mới và 22 nội dung chuyển sang FILTER_DROP; đây là snapshot đối soát trước pilot, không phải trạng thái hàng chờ hiện tại. Worker đang chạy liên tục với log `reports/filter-policy-v3-worker.out.log` / `.err.log`, report `reports/filter-policy-v3-worker-latest.json`. [Runbook và kiểm chứng v3](filter-policy-v3-20261011.md).

Lượt v3/v3.1 đã hoàn tất: 2.674 DONE, 184 FILTER_DROP, 111 MISSING_TEXT; không chờ/lỗi hiện hành. V3.1 siết ngoại lệ OCR context cho đúng một case nhắc bảng giá, giữ 2.673 DONE khác. Worker ACTIVE, scheduler thread sống; cycle không có đầu vào mới gọi 0 API. Các số liệu 2.692 DONE hoặc worker STOPPED phía trên là snapshot lịch sử trước bản sửa filter.
# Vận hành local từ 13/10/2026

[Supervisor local](local-runtime-recovery.md) đã bổ sung để tự khởi động/nhận quản lý dashboard và classifier độc lập khi đăng nhập Windows, thay worker đã kết thúc và đối soát ca bỏ lỡ. Các ghi chú “chưa đăng ký tự khởi động” trong bằng chứng ngày 09–11/10 bên dưới là trạng thái lịch sử tại thời điểm kiểm tra. Task `SocialListeningRuntime` đã được đăng ký và chạy thật ngày 13/10; chưa thử reboot/logoff máy người dùng. Máy tắt/ngủ không xử lý được, mở lại tiếp tục hàng chờ và giữ DONE hợp lệ.
