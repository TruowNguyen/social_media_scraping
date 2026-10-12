# Kế hoạch triển khai tối ưu dashboard

Ngày lập **10/10/2026**. Đồng bộ trạng thái **11/10/2026: UXR đã triển khai, UAT_PENDING**. Contracts/workspace/draft/review/export đã có implementation và verification theo [runbook workspace](operations/dashboard-workspace.md). Nội dung dưới đây giữ kế hoạch/acceptance gốc; đề xuất IndexedDB đã được triển khai bằng localStorage, API names cuối cùng theo runbook/code.

Nguồn yêu cầu: [đánh giá UX độc lập](operations/dashboard-ux-audit-2026-10-10.md), [bằng chứng browser](../reports/ux-audit-B-evidence.json), workflow scheduled crawl → raw storage → filter → classify đã thống nhất. Baseline UX đạt 21/40 theo heuristic, có lỗi mất nháp và sai phạm vi kết quả đã tái hiện.

## 1. Mục tiêu và hướng thiết kế

Người vận hành cần biết hệ thống có đang theo dõi đúng lịch, tìm được nội dung đáng chú ý, đọc đủ ngữ cảnh, lưu đánh giá và xuất đúng tập dữ liệu.

Hướng đề xuất để lập kế hoạch:

- Trang mở đầu **Phản ánh**, kèm trạng thái lịch/crawl/phân loại.
- Desktop giữ **bảng từng nội dung + panel hội thoại**; mobile dùng danh sách + chi tiết toàn màn hình, có thể chuyển sang bảng khi cần so sánh.
- Bốn điểm đến: **Phản ánh / Kho dữ liệu / Thu thập / Tìm link Google**. Thu thập có các phần riêng **Chạy ngay / Lịch hằng ngày / Lịch sử**.
- Giữ ngôn ngữ hình ảnh hiện có; tập trung thay đổi bố cục và hành vi.

Hai lựa chọn trang mở đầu và panel là **đề xuất chưa được người dùng chọn riêng**, không ghi thành quyết định đã duyệt. Có thể điều chỉnh trước phase bố cục mà không trì hoãn sửa lỗi dữ liệu/draft.

Phạm vi dùng database hiện tại `sessions/acquisition/acquisition.sqlite3`, node POST/COMMENT/REPLY, taxonomy và Gemini đã cấu hình. Review của người dùng tách khỏi kết quả model. Dữ liệu gốc trước lọc, identity/dedup và kết quả phân loại còn hiệu lực được giữ theo contract hiện có. Kế hoạch UX hiển thị rõ giới hạn crawler, không nghiệm thu “đã lấy mọi bài/comment trong window” bằng thay đổi UI.

## 2. Đầu vào phải kiểm tra trước khi sửa

| Đầu vào | Nội dung cần ghi nhận | Kết quả bàn giao |
| --- | --- | --- |
| Code/UI baseline | HTML/JS/CSS, routes hiện tại, cấu hình lịch, chế độ xem và export | Manifest file/route + capture desktop/mobile + phiên bản baseline |
| Dữ liệu | Node/revision/root/parent, observations, node_reviews/history, filter decisions, jobs/analyses | Danh sách trường thực có, trường thiếu và cách fallback; số lượng trước migration |
| Vận hành | Hai khung 05:00–08:30 và 17:00–18:30, 45 phút, lượt chốt; trạng thái nguồn/session/worker | Bản cấu hình lưu lại và cách kiểm tra sau rollout |
| Acceptance nghiệp vụ | Phản ánh dự án, phân biệt nội dung gốc/model/người, thống kê đúng đơn vị | Bộ tác vụ thử và dữ liệu đối chứng |
| Môi trường | Venv/dashboard/browser hiện có; phiên Facebook chỉ cần cho pilot collection nếu phải chạy | Lệnh chạy và bằng chứng môi trường; không cần cấp thêm API key cho việc viết UI/tests offline |

Lấy backup SQLite bằng backup API trước migration, đọc kiểm tra backup. Snapshot database/config và revision code được ghi thời điểm. Không dừng dashboard để triển khai khi còn job crawl; nếu chưa có điểm nghỉ an toàn, giữ trạng thái triển khai chờ và báo rõ.

## 3. Quy tắc dữ liệu/interaction cần khóa

### 3.1 Phạm vi kết quả và export

UI có hai state riêng: `editing_filters` (đang chọn) và `applied_view` (kết quả đã đọc thành công). Request lỗi/pending không sửa scope của bảng cũ. Kết quả crawl có `run_id`, project/source IDs, window và thời điểm riêng; đổi input chỉ chỉnh lượt tiếp theo.

Một view dùng `view_id`, `view_kind`, normalized filters, sort, `as_of`, ordered identity/revision references, total/facet counts và projection phục vụ export. Bảng, phân trang, count và export đọc cùng view. Không chỉ giữ hash bộ lọc: hash không khóa dữ liệu khi crawl/review đang cập nhật.

Đề xuất triển khai snapshot projection bất biến trong cùng SQLite, đọc một phiên dữ liệu nhất quán; cache/reuse nếu filter và versions không đổi. TTL mặc định 24 giờ, cấu hình được; cleanup và giới hạn lưu trữ được khóa ở UXR-02. Snapshot chứa dữ liệu báo cáo cần thiết, không chứa browser session/API credentials. Không chạy DDL trong mỗi request đọc.

Snapshot hết hạn trả lỗi có mã và hướng dẫn tạo view mới; không tự đổi sang dữ liệu mới rồi giữ count cũ. Bản export có sheet metadata ghi view/window/date basis/as_of/count và saved-review-only. Nếu lưu review sau khi tạo view, UI làm mới snapshot trước export hoặc cho người dùng chọn rõ snapshot cũ; không tự trộn hai thời điểm.

### 3.2 Bản nháp và concurrency

Draft map theo `node_id`, gồm status/note, base review version, saved fields và `dirty`. Lưu nháp qua reload bằng storage tại browser; chọn store và TTL ở UXR-02, đề xuất IndexedDB với TTL 7 ngày và xóa sau Save/Discard. Không đặt note vào URL. Storage không khả dụng thì hiển thị trạng thái không thể recovery và dùng cảnh báo rời trang.

Đổi filter/page/tab được phép nếu draft đã giữ an toàn; có chỉ báo các draft ngoài view. Reload khôi phục draft. Đóng tab có cảnh báo khi persistence chưa đảm bảo. Clear/Discard phải do người dùng chọn. Save thất bại giữ nguyên draft.

Review hiện có `node_review_history` được tái sử dụng. Bổ sung review version/expected version và lưu nguyên tử. Hai tab lưu trên cùng node: tab dùng version cũ nhận 409, không ghi đè im lặng; UI cho so sánh phiên đã lưu với nháp và chọn thao tác tiếp. Nháp gắn revision: caption đổi phải báo nội dung đã thay đổi, không âm thầm áp nháp vào một bản khác.

### 3.3 Thời gian, dự án và bốn tầng trạng thái

- Timestamp UTC; UI giờ Việt Nam. Ngày kết thúc bao gồm cả ngày, truy vấn nội bộ `[start, end)`.
- `PUBLISHED`: thời gian của chính POST/COMMENT/REPLY. Thiếu/mơ hồ không tính là xác minh trong window.
- `OBSERVED_ANY`: có observation trong khoảng; hiển thị `matched_observed_at` bên cạnh `last_seen_at`.
- `OBSERVED_LATEST`: lần thu thập gần nhất trong khoảng.
- Project scope có tên rõ: nguồn/dấu hiệu ở kho, model xác định ở phản ánh. Với pending không có model project, hỗ trợ xem theo nguồn/dấu hiệu có nhãn chưa xác nhận; không giả lập một project match của model.
- Tách extraction quality, processing state, filter/model decision, human review. `FILTER_DROP` khác model `DROP`; `PASS` không đồng nghĩa model `KEEP`; human review không overwrite model.
- Count nội dung khác count hội thoại; mọi aggregate có tên đơn vị và scope. Không suy số phản ánh nghiệp vụ chỉ từ tổng số comment.

### 3.4 Hội thoại và background refresh

Record detail dùng identity chuẩn, root/parent thật, một nhánh tổ tiên và danh sách comment/reply phân trang. Giữ node riêng khi phân loại. Thiếu parent/root/caption phải đánh dấu; không crawl thêm vì người dùng chỉ mở panel. URL post-level không được trình bày như deeplink comment đã xác minh.

Refresh theo node ID + revision/review version, giữ expanded/focus/scroll/selection/drafts. Nội dung đang đọc đổi thì thông báo có phiên mới để người dùng chọn cập nhật; không thay âm thầm. Có pause; timer/request dọn khi đổi tab hoặc document hidden. Dữ liệu mới không tự nhảy người dùng về trang 1.

## 4. Kiến trúc thay đổi

| Khu vực | Thành phần đề xuất | Trách nhiệm |
| --- | --- | --- |
| UI | Application shell/navigation/status strip | Current view, URL, trạng thái vận hành, điểm đến theo tác vụ |
| UI | Shared filter/view controller | Editing/applied state, chips, date basis, snapshot/paging, debounce/abort |
| UI | Record detail/review controller | Hội thoại, model/quality/provenance, drafts/version conflict, điều hướng trước–sau |
| UI | Desktop table/mobile list | Cùng dữ liệu, stable identity; tránh hai logic lọc khác nhau |
| engine | Query/view service | Normalize/validate/filter/snapshot/facets/sort/export scope |
| engine | Detail/health/review/report services | Compose storage + registry + job data, không giả lập metric |
| src/storage | Snapshot/review persistence nếu cần | Migration, version checks, transaction/history, retention |

Tái sử dụng `dashboard.py`, `dashboard.js`, `dashboard_classification.js`, `dashboard.css`, `conversation_library.py`, `classification_view.py`, `classification_service.py`, `library_export.py` và `ConversationStore`. Tách module theo trách nhiệm khi sửa; dependency vẫn `engine → src`. Không thay schema raw/model để phục vụ layout.

Các routes dưới đây là **đề xuất**, cần khóa tên/schema tại UXR-02; endpoints hiện tại vẫn giữ tương thích cho callers cũ.

| Contract | Nội dung | Acceptance bắt buộc |
| --- | --- | --- |
| View library/classifications + pagination `view_id` | Filters, sort, counts, snapshot; classifications join human review | Không đổi scope giữa trang/count/export; read không gọi model/crawler |
| `GET /api/records/{node_id}` | Node, quality, parent/root references, current analysis/provenance, filter decision, human review/version | Thiếu context trả missing reason; identity đúng |
| `GET /api/threads/{root_id}` | Ancestors và children phân trang/cursor, missing/truncated markers | Không tải mọi comment một lượt; không gộp các node khác identity |
| `GET /api/health` | Registry readiness vs last access/crawl outcome; schedule last/next; worker jobs/lease/heartbeat | Không có heartbeat thì UNKNOWN, không tự báo worker healthy |
| `GET /api/runs/{run_id}` | Immutable scope, source progress, stage, elapsed, last activity, outcome/coverage | PARTIAL/FAILED tách khỏi completed; stale heartbeat có nhãn |
| Review save/bulk review | Version preconditions, history, idempotency; reuse review API | Conflict không mất nháp; model/raw nguyên vẹn |
| Classification preview/run/retry | Eligible count + selection scope, current binding, limits | Nút ghi đúng phạm vi; DONE còn hiệu lực không reclassify; OVERSIZED không retry vô nghĩa |
| Library/classification export by `view_id` | Frozen projection + metadata, all pages, Vietnamese labels | Đúng ordered set/as_of; hết hạn/lỗi có phản hồi; ô text chống formula injection |

Phase đầu chỉ ghi rõ lệnh classifier hiện xử lý queue toàn hệ thống. Scoped run theo node/source/project chỉ bật ở UI sau khi backend preview/run và tests tương ứng đã có. Không gửi filter để tạo cảm giác scoped trong khi worker bỏ qua.

## 5. Backlog theo phase

Mọi task mới bên dưới: **PLANNED**, owner là role đề xuất, chưa gán người cụ thể. `FE`: frontend, `BE`: backend/data, `QA`: kiểm thử.

### Phase 0 — Khóa baseline, contract và thiết kế tác vụ

**Đầu vào:** audit 26 vấn đề, code/data/config hiện tại. **Mục tiêu:** có bản thiết kế đủ cụ thể để triển khai, không lặp sửa theo cảm giác.

| Task | Công việc / output | Owner | Phụ thuộc |
| --- | --- | --- | --- |
| UXR-01 | Reproduce baseline, kiểm tra data fields/identity, backup/migration manifest, ghi trạng thái 4 tab | BE/QA | Audit |
| UXR-02 | Khóa view snapshot/date/project/status/detail/health/review/export contracts, error codes, TTL/migrations | BE/FE | 01 |
| UXR-03 | Wireframe desktop/mobile: navigation, main filters, panel, health, empty/error/loading, drafts/conflicts | FE/Product | 01–02 |

**Gate:** 26 AUD IDs có task/test; choice chưa chốt ghi đề xuất; payload mẫu gồm POST/COMMENT/REPLY, missing context, DROP/FAILED, stale view và dirty draft. Product xác nhận hướng bố cục trước Phase 4; sửa lỗi Phase 1 không cần đợi màu hoặc chi tiết hình ảnh.

### Phase 1 — Sửa lỗi mất công việc và scope sai

**Đầu vào:** baseline + state contracts. **Mục tiêu:** thao tác thông thường không mất note/phiên đọc hoặc tạo kết quả sai ngày.

| Task | Công việc / output | Owner | Phụ thuộc |
| --- | --- | --- | --- |
| UXR-04 | Draft map/persistence/recovery, dirty badge, Save/Discard, unsaved-outside-view | FE | 02 |
| UXR-05 | Stable row reconciliation; giữ expanded/focus/scroll, pause/document visibility, stale-request protection | FE | 02 |
| UXR-06 | Tách tham số next run khỏi scope last run; lời giải thích phạm vi classifier hiện tại | FE/BE | 02 |
| UXR-07 | Snapshot/read projection, stable sorting/paging/facet counts, expiry/reuse/cleanup | BE | 02 |
| UXR-08 | Bảng/export dùng applied view; pending/invalid/error không đổi scope; preview saved-only/dirty state | FE/BE | 04,07 |

**Output nghiệm thu:** bản vá chạy với layout hiện có, report các case UR-01–05 và UR-14. **Gate:** mất nháp và sai ngày không còn tái hiện; ba lượt refresh giữ trạng thái; data thay đổi giữa pages/export vẫn đúng snapshot; hết hạn không xuất dữ liệu khác im lặng.

### Phase 2 — Nối evidence, model và đánh giá người

**Đầu vào:** identity/context contracts và stable view. **Mục tiêu:** duyệt một nội dung không phải tìm lại nó ở tab khác.

| Task | Công việc / output | Owner | Phụ thuộc |
| --- | --- | --- | --- |
| UXR-09 | Record/thread read endpoints; ancestor chain, children paging, missing/fallback-link markers | BE | 02 |
| UXR-10 | Panel detail từ cả raw và classification; trước/sau; mở đúng node, model/filter/quality/context riêng | FE | 05,09 |
| UXR-11 | Review optimistic version, reuse review_history, conflict resolution, identity shared giữa 2 views | BE/FE | 04,09 |
| UXR-12 | Join human review vào view model; tách trạng thái/pending scopes và provenance | BE/FE | 07,11 |

**Output:** luồng xem bình luận → parent → đánh giá → lưu → sang mục tiếp theo. **Gate:** ≤2 thao tác tới context và đánh giá đúng node; missing parent không được dựng lại; conflicting saves không overwrite; không sửa analysis/raw vì human review; model và người hiển thị riêng.

### Phase 3 — Vận hành, lịch và phục hồi lỗi

**Đầu vào:** runs/tasks/jobs/checkpoints/registry/schedule. **Mục tiêu:** nhận biết hoạt động và phần bị lỗi ngay khi vào app.

| Task | Công việc / output | Owner | Phụ thuộc |
| --- | --- | --- | --- |
| UXR-13 | Health/run APIs, heartbeat/activity, source progress/coverage, queue counts; thêm metric nếu hiện thiếu | BE | 02 |
| UXR-14 | Status strip; Thu thập tách Chạy ngay/Lịch/Lịch sử; hiện run scope và lịch giờ thực | FE | 06,13 |
| UXR-15 | Error recovery tiếng Việt; classifier preview/scoped run hoặc retry nếu được triển khai; session-block guidance | BE/FE | 12–13 |

**Gate:** người thử nhận biết lịch/last/next/errors trong 5 giây; registry ready không bằng health live; heartbeat thiếu/stale không báo healthy; lỗi một nguồn giữ dữ liệu nguồn khác; schedule windows/45 phút/lượt chốt giữ đúng cấu hình. Chưa có cancel an toàn thì không đưa nút Abort giả lên UI.

### Phase 4 — Tổ chức lại workspace và bộ lọc

**Đầu vào:** wireframe đã chốt + detail/view/health APIs. **Mục tiêu:** nội dung là trọng tâm, filter có cùng ngôn ngữ và hành vi.

| Task | Công việc / output | Owner | Phụ thuộc |
| --- | --- | --- | --- |
| UXR-16 | Shared filter component: date bases/unknown notices/project scopes/advanced counts/chips/preset semantics | FE/BE | 07,12 |
| UXR-17 | URL view/filter/sort/page/node; restore/back-forward; saved view metadata, không chứa notes | FE | 16 |
| UXR-18 | Shell 4 điểm đến; Phản ánh mặc định hoặc phương án đã chốt; desktop compact table + panel | FE | 03,10,14,16 |
| UXR-19 | Mobile navigation/list/detail/filter drawer; keyboard/focus/labels; touch targets ~44 px | FE/QA | 18 |

**Gate:** 390×844 có đường tới nội dung mà không cuộn qua tám ô input; đọc/duyệt dùng một chiều cuộn chính; chọn/grouping đúng POST/COMMENT/REPLY; same filter nghĩa rõ; back/reload khôi phục view; keyboard không mất focus, Ctrl+Home không kích hoạt Home tab.

### Phase 5 — Hiệu quả duyệt và báo cáo

**Đầu vào:** record review/version + view snapshot. **Mục tiêu:** xử lý nhiều nội dung và xuất kết quả có thể đối chiếu.

| Task | Công việc / output | Owner | Phụ thuộc |
| --- | --- | --- | --- |
| UXR-20 | Sort/page size và bulk human review; selection explicit, count và scope; transaction/history/idempotency | FE/BE | 11,17 |
| UXR-21 | Báo cáo classification Excel theo view; raw report riêng; model/human/provenance/quality tách cột | BE/FE | 08,12 |
| UXR-22 | Nhãn tiếng Việt, task help, metadata/title, unit counts, provenance; polish theo identity hiện có | FE/Product | 18–21 |

Bulk v1 mặc định chỉ **IDs đã chọn rõ**, tối đa 100/request; chọn tất cả filtered results phải xác nhận explicit và dùng snapshot sau. Conflict version làm transaction v1 thất bại toàn bộ, trả node conflicts, không ghi một phần rồi báo thành công. Review history hiện có được giữ; idempotency key ngăn ghi lặp khi retry mạng.

**Gate:** số hàng/ordered IDs/versions của workbook khớp view; saved-only rõ; chống formula injection với text bắt đầu `=,+,-,@`; UID dạng text và timezone rõ; review model không bị overwrite; bulk retry không tạo history trùng.

### Phase 6 — Regression, UAT và rollout

| Task | Công việc / output | Owner | Phụ thuộc |
| --- | --- | --- | --- |
| UXR-23 | Contract/SQLite, Chromium tasks, responsive/performance/concurrency; report matrix UR | QA/FE/BE | Theo từng phase; final sau 22 |
| UXR-24 | Pilot saved-data thật + người vận hành/mentor, migration rollout/health/rollback, docs/TODO bằng chứng | Product/QA/BE | Gate 1–5 |

**Gate cuối:** các lỗi P1 tái hiện đã đóng; tests pass với evidence; tác vụ live-read và manual-save/export được kiểm tra sau khi bố cục chốt; người vận hành duyệt/report đúng scope. Save/retry/bulk/crawl live là hành động riêng, không thực hiện chỉ để chụp screenshot audit.

## 6. Ma trận test/nghiệm thu

| Case | Input/thao tác | Expected output | Task |
| --- | --- | --- | --- |
| UR-01 | Note chưa lưu → filter/page/tab/reload | Draft còn hoặc Save/Discard rõ; restore đúng node/revision | 04,11 |
| UR-02 | Review save 500/offline; hai tab cùng node | Giữ nháp; stale save 409; không overwrite | 04,11 |
| UR-03 | Mở caption/focus/scroll qua 3 refresh 15s | Trạng thái giữ; phiên mới được thông báo; không nhảy trang | 05 |
| UR-04 | Kết quả 10/10 → sửa input 9/10, không chạy | Scope bảng vẫn 10/10, input ghi next-run; không nói đúng 9/10 | 06 |
| UR-05 | Đổi filter liên tục/delay response/date invalid | Response cũ không ghi đè; bảng và export dùng applied view | 05,07,08 |
| UR-06 | Bài cũ ngoài window, comment/reply mới trong window | Lọc theo ngày node; parent làm context; không bỏ comment vì ngày post | 09,16 |
| UR-07 | Missing parent hoặc link chỉ post | Nhãn missing/fallback; không hứa mở tới comment | 09,10 |
| UR-08 | Một node observed 9/10 và 10/10; timestamp unknown | ANY/LATEST/PUBLISHED đúng nghĩa, matched date rõ, unknown không được xác nhận trong window | 07,16 |
| UR-09 | FILTER_DROP/model DROP/KEEP/REVIEW/pending/failed/human review | Nhãn/filter riêng, quyết định gắn nguồn; human không sửa model | 12,16 |
| UR-10 | Chọn project, node pending chưa có model match | Có scope nguồn/dấu hiệu có nhãn; không fake model match | 12,16 |
| UR-11 | PROFILE_IN_USE/login/CAPTCHA/parser lỗi/partial/worker stale | Health UNKNOWN/blocked/partial rõ; nguồn khác giữ dữ liệu; guidance đúng | 13–15 |
| UR-12 | Lịch 05–08:30 / 17–18:30, 45 phút, final tick | Giữ schedule; preview next times đúng; tắt lịch không nói đã hủy job | 14 |
| UR-13 | Classifier run trong view đã lọc; DONE hiện hành/oversized | Scope/eligible preview đúng; không reclassify DONE vì filter; retry chỉ case đủ điều kiện | 06,15 |
| UR-14 | Export all-pages; crawl/review đổi trong lúc đó; token hết hạn | Exact snapshot/count/order/versions, saved-only; expiry báo rõ không silently fallback | 07,08,21 |
| UR-15 | Text công thức Excel, UID dài, Unicode Việt, dates UTC | Không execute formula; UID nguyên dạng; nhãn/timezone đúng | 21 |
| UR-16 | Bulk selectedIDs có version conflict + retry same key | Không partial overwrite, conflict list rõ; idempotent history | 20 |
| UR-17 | 390×844, desktop 1366×768, zoom 200%, keyboard tabs/panel | Nội dung/control không bị che; close panel trả focus; navigation tiếp cận được | 18,19 |
| UR-18 | URL share/reload/back/forward; view expired | Restore filters/node có tồn tại; stale/expired được giải thích; note không trong URL | 17 |
| UR-19 | Không dữ liệu, không khớp, loading, API lỗi | Bốn state khác nhau; không suy “không có phản ánh” từ fetch error | 16,22 |
| UR-20 | Dataset ≥2.000 nodes + concurrent writer | p95 view read mục tiêu ≤2s local, cached ≤0,5s; detail/paging bounded; không DB-lock/unbounded response | 07,09,13,23 |
| UR-21 | Người thử check health → tìm signal → context → lưu → next → report | Hoàn thành không tìm lại record; báo cáo đúng scope; ghi thời gian và vướng mắc thực | 24 |

UR-20 là **mục tiêu nghiệm thu**, chưa là kết quả đo; export chạy riêng, trạng thái tạo file không khóa UI. Nếu cơ sở máy/dataset đổi phải ghi lại benchmark. Browser visual QA của mỗi increment: build đầy đủ, một lượt desktop/mobile, sửa batch, tối đa một lượt xác nhận. Functional regression chạy theo lỗi/phạm vi, tránh vòng polish không giới hạn.

Test fixture không gọi Google/Gemini/Facebook. Pilot saved-data không cần crawl lại. Chạy model/crawl live khi cần chứng minh integration phải ghi nguồn/window/count/outcome và không coi đó là chứng minh full coverage.

## 7. Traceability từ audit

| Audit | Task sửa chính |
| --- | --- |
| AUD-01 | UXR-04,11 |
| AUD-02 | UXR-06,07 |
| AUD-03 | UXR-09,10 |
| AUD-04 | UXR-10,11,12 |
| AUD-05 | UXR-05 |
| AUD-06 | UXR-06,15 |
| AUD-07 | UXR-13,14 |
| AUD-08 | UXR-18,19 |
| AUD-09 | UXR-10,18,19 |
| AUD-10 | UXR-13,15 |
| AUD-11 | UXR-07,16 |
| AUD-12 | UXR-16 |
| AUD-13 | UXR-12,16 |
| AUD-14 | UXR-12,16 |
| AUD-15 | UXR-07,22 |
| AUD-16 | UXR-16 |
| AUD-17 | UXR-09,10,22 |
| AUD-18 | UXR-13,14,15 |
| AUD-19 | UXR-07,08,21 |
| AUD-20 | UXR-14,22 |
| AUD-21 | UXR-16,22 |
| AUD-22 | UXR-17 |
| AUD-23 | UXR-17,20 |
| AUD-24 | UXR-05,19 |
| AUD-25 | UXR-10,12,22 |
| AUD-26 | UXR-19,22 |

## 8. Trình tự triển khai và kiểm soát trạng thái

Chuỗi chính: **01–03 → 04–08 → 09–12 → 13–15 → 16–19 → 20–22 → 23–24**. QA bắt đầu từ từng phase, không đợi cuối. Backend contracts/fixtures có thể chuẩn bị trước UI của phase tương ứng sau khi đã khóa schema.

Mỗi increment ghi: task IDs, đầu vào, code/contracts đổi, regression evidence, hạn chế, migration/rollout status và người duyệt. Trạng thái dùng **PLANNED → IN_PROGRESS → OFFLINE_VERIFIED → LIVE_READ_VERIFIED/UAT_VERIFIED → ACCEPTED**; stage không áp dụng ghi N/A. Không lấy lần tests pass trước làm evidence cho code mới; không đổi PLANNED chỉ vì mockup/payload đã viết.

Output bàn giao cuối: dashboard mới, API/storage migrations tương thích, report UR matrix, snapshot mẫu/Excel đối chứng, runbook và backlog còn lại. Pilot visual không chứa credentials; bộ test/report dùng fixture cho dữ liệu nhạy cảm khi chia sẻ.

Rollout: backup/validate → migration idempotent → deploy backend contracts tương thích → deploy UI → smoke health/read/detail/review/export → nghiệm thu. Chờ điểm nghỉ crawl, giữ cấu hình/profile/DB. Rollback code về baseline, giữ review/data mới; migration ưu tiên additive để baseline tiếp tục đọc được. Chỉ restore backup nếu đã đánh giá và hòa giải phần dữ liệu phát sinh, không restore mù làm mất crawl/review sau backup.

Đầu việc nên bắt đầu ngay khi triển khai: **UXR-01/02 rồi UXR-04/05/06**. Chốt layout chi tiết sau đó; không để việc chọn hình thức trì hoãn sửa mất nháp và sai phạm vi ngày.

## Kết quả triển khai — 10/10/2026

Kế hoạch đã được thực thi trên dashboard. UXR-01…23 có implementation và bằng chứng tự động/live-read; UXR-24 đã rollout, phần nghiệm thu người vận hành/mentor còn UAT_PENDING. Xem [runbook và lựa chọn thực tế](operations/dashboard-workspace.md), [validation](../reports/workspace-validation.json). Phần đầu tài liệu giữ nội dung kế hoạch tại thời điểm lập; trạng thái hiện hành ở mục này và TODO.MD.
