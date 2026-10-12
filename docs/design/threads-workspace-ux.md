# Thiết kế UX/UI đáp ứng luồng adapter Threads

**IMPLEMENTED_SUBSET / OFFLINE_VERIFIED / LIVE_UI_VERIFIED · 12/10/2026**. Áp dụng [Impeccable](../../.agents/skills/impeccable/SKILL.md) để mở rộng surface hiện có theo `new-work`/`operate`, kiểm tra trực tiếp không agent phụ. Design brief bên dưới là mục tiêu; HTML/CSS/JS đã triển khai chọn nền tảng, query/run/schedule riêng và bộ lọc kho chung. Bằng chứng, phạm vi và giới hạn ở [runbook](../operations/threads-acquisition.md).

Người dùng đã chốt: **chung tab Thu thập, chọn nền tảng ở đầu màn hình**, lịch và lượt chạy độc lập. Căn cứ sản phẩm ở [PRODUCT.md](../../PRODUCT.md), backend flow ở [adapter flow](threads-adapter-flow.md), [plan P0–P7](../implementation-plan-threads.md).

## 1. Mục tiêu và visual authority

Mode **Operate**: người dùng chọn phạm vi → chạy/lập lịch → biết đã lưu được gì và phần nào thiếu → mở raw/hội thoại → kiểm tra taxonomy/đánh giá. Thiết kế ưu tiên thao tác và sự rõ ràng, không lấy biểu đồ trang trí hoặc số liệu marketing làm trọng tâm.

Giữ visual system hiện có đã đối chiếu code và Chrome: font hệ thống/Segoe UI, chữ xanh đậm, nền xám nhạt, action xanh, native form controls, bảng dữ liệu và responsive hiện có. Thiếu DESIGN.md không làm surface thành greenfield. Không thay toàn bộ nhận diện hoặc tạo concept tournament cho phần mở rộng tab đã được chốt.

Các bất tiện quan sát trong baseline cần xử lý khi nối Threads:

| Bất tiện | Tác động | Quyết định thiết kế |
| --- | --- | --- |
| Tab Thu thập có tiêu đề Facebook cố định, Nguồn là Group | Threads bị hiểu nhầm cần group | Nền tảng ở đầu; query scope cho Threads, group list cho Facebook |
| Health gộp một lịch/một lượt đang chạy | Khó biết lịch đang nói về nền tảng nào | Summary theo nền tảng; chọn Threads mới hiển thị lịch Threads |
| Màn hình đang tải vẫn giữ bảng/total cũ nhưng disable controls | Có thể hiểu bảng cũ là kết quả vừa refresh | Nhãn phiên đang xem + loading có deadline + lỗi có Retry; giữ bảng rõ “dữ liệu chốt lúc…” |
| Preset Hôm nay chỉ điền ô ngày, chưa apply | Người dùng dễ tưởng bảng đã lọc ngày | Preset date apply ngay; input tùy chỉnh vẫn có Apply/chỉ báo chưa áp dụng |
| Form filter nhiều trường ngang hàng | Khó tách scope, vấn đề và xử lý | Bộ lọc chính ít mục; query/intent/processing/OCR/review trong mở rộng |
| Source query và keyword lọc raw có thể lẫn nhau | Thay ô tìm nội dung bị tưởng đang crawl keyword mới | “Truy vấn theo dõi” nằm Thu thập; “Tìm trong nội dung đã lưu” nằm Kho/Phản ánh |

Quan sát trực tiếp là evidence bố cục/states, không phải audit latency toàn hệ thống. Không tự sửa lỗi production ngoài scope của thiết kế.

## 2. Information architecture

Giữ bốn tabs chính: **Phản ánh | Kho dữ liệu | Thu thập | Tìm link Google**. Không thêm tab Threads thứ năm. Google discovery không đưa vào selector nền tảng crawler Facebook/Threads.

Trong Thu thập:

1. Chọn nền tảng `[Facebook] [Threads]`, trạng thái kết nối/readiness và phương thức thu ngắn gọn.
2. Subsections chung: **Chạy ngay | Lịch hằng ngày | Lịch sử | Nguồn theo dõi**.
3. Chọn Threads: nguồn theo dõi là bộ truy vấn theo dự án. Chọn Facebook: nguồn theo dõi là groups đã lưu.
4. Lượt chạy hiện tại hiển thị rõ platform/project/window và không bị thay khi form hoặc platform selector đổi.

Đổi nền tảng giữ draft cài đặt riêng trên máy, không save/enable schedule hoặc tạo run ngầm. Active jobs vẫn chạy độc lập; summary “Facebook đang chạy” không disable nút chạy Threads nếu Threads sẵn sàng. Unsaved query/schedule có chỉ báo và không bị poll overwrite.

## 3. Màn hình Chạy ngay

Wireframe chức năng desktop; nội dung trong dấu `<>` là dữ liệu backend, không phải metric giả:

```text
Thu thập
Nền tảng: [ Facebook ] [ Threads ✓ ]    Kết nối: <trạng thái> · <API / Browser / Hybrid>
Chạy ngay | Lịch hằng ngày | Lịch sử | Nguồn theo dõi

Dự án [VinWonders Vũ Yên ▾]
Truy vấn theo dõi [x] VinWonders Vũ Yên  [x] VinWonder Vũ Yên
                   [x] Vin Wonders Vũ Yên  [ ] Vũ Yên — phạm vi rộng
<liên kết Chỉnh bộ truy vấn>   Phạm vi: <Bài viết và bình luận / Chỉ bài viết>

Khoảng thu thập · Giờ Việt Nam
[Hôm nay] [7 ngày] [Tùy chọn]
Từ [ngày + giờ]                  Đến [ngày + giờ]
<tóm tắt dự án, số query, khoảng thời gian, phạm vi thực tế>
[Bắt đầu thu thập]

Lượt đang chạy / Lượt gần nhất
<platform> · <project> · <window snapshot> · <phương thức thực tế>
Tìm bài → Đọc bài & bình luận → Lưu dữ liệu
<stage + count có nguồn>   <coverage / chưa đọc được / còn chờ lưu>
[Dừng lượt này] [Xem dữ liệu đã lưu] [Xem kết quả phân loại]
```

- Một CTA chính: Bắt đầu thu thập. Query seed recommend sẵn theo project; sửa query qua Nguồn theo dõi để versioned, không một free-text field làm cả filter và discovery.
- Chọn exact date/time để hỗ trợ backfill, ca sáng/chiều và case reply theo giờ. Default Hôm nay = 00:00 tới hiện tại; end tương lai không được lấy làm coverage đã hoàn tất.
- Scope không mặc định đồng nghĩa all data: khi public replies chưa verified, nút mục tiêu post+replies disabled với lý do; user có thể chọn post-only khi capability đã chứng minh. Không dùng button disabled không giải thích.
- Provider hiển thị read-only ở status/detail; không bắt user chọn framework hoặc điền token vào form crawl.
- User chọn date/query trong lúc chạy không thay active snapshot. Nút chạy khi platform busy dẫn “Xem lượt đang chạy”; không tạo double job.
- Cumulative scheduled window khác manual preset: kết quả luôn ghi window thật đã chạy, không lấy từ form hiện tại.

Mobile ≤760 px: cùng thứ tự, form một cột, date/time xuống hàng, query checkboxes full-width, platform selector và subtabs rõ focus/selected; run details mở rộng inline. Primary action đủ 44 px, không fixed bar che status. Không cuộn ngang toàn trang; chỉ bảng có container riêng.

## 4. Nguồn theo dõi Threads

```text
Nguồn theo dõi · Threads
Dự án [VinWonders Vũ Yên ▾]                       [Thêm truy vấn]
Truy vấn                Loại             Trạng thái       Phạm vi
VinWonders Vũ Yên        Từ khóa          Đang bật         Theo dõi chính
VinWonder Vũ Yên         Từ khóa          Đang bật         Theo dõi chính
#VinWondersVuYen         Chuỗi tag        Chưa bật         Cần kiểm chứng cách tìm
Vũ Yên                  Từ khóa          Chưa bật         Phạm vi rộng

<Lưu thay đổi>    <Chưa lưu / phiên bản đang áp dụng>
```

CRUD tối thiểu: thêm/sửa, bật/tắt; archive thay vì xóa lịch sử lineage. Cùng query text qua projects vẫn có source contexts riêng, dedup theo node ở storage. Tất cả edit server validated với version conflict; ongoing runs giữ snapshot cũ.

Từ khóa không phải filter relevance: tên project dẫn search, taxonomy quyết định vấn đề sau lưu. Query rộng không bị tự bật do recommend. Scope warning ngắn cho “Vũ Yên”; không đổi thành blanket reject mọi kết quả nếu thiếu exact project name.

Source type `THREADS_PROFILE` không hiện như chức năng khả dụng nếu chưa triển khai/pilot; không đưa profile scraping rộng vào v1 dưới nút “Thêm nguồn”.

## 5. Lịch hằng ngày — tách cấu hình và bật lịch

Nền tảng chọn ở đầu màn hình quyết định lịch đang chỉnh. Tiêu đề rõ **Lịch Threads**; Facebook schedule không bị ghi đè khi save.

```text
Lịch Threads                        <Đang tắt / Đang bật / Thiếu điều kiện>
Dự án [VinWonders Vũ Yên ▾]          Bộ query <version và số query enabled>
Ca sáng   [05:00] — [08:30]
Ca chiều  [17:00] — [18:30]
Chu kỳ    [45] phút                  Giờ Việt Nam

Sáng: 05:00 · 05:45 · 06:30 · 07:15 · 08:00 · chốt 08:30
Chiều: 17:00 · 17:45 · chốt 18:30
<Giải thích mở ca chỉ lấy danh sách; các lượt sau thu từ đầu ca đến mốc chạy>

[Lưu cấu hình] [Bật lịch] / [Tắt lịch]
Lịch đã lưu: <snapshot/version> · lượt tiếp: <time> · lượt chốt gần nhất: <outcome>
```

- Lưu cấu hình không tự bật. Bật chỉ khi backend readiness/schema/storage/query/provider gates đủ. Tắt lịch dừng tick mới, không xóa dữ liệu hoặc tự hủy active run.
- Dirty config và enabled schedule là hai trạng thái. Bật dùng cấu hình **đã lưu**, user thấy tóm tắt; tránh bật draft chưa persist. Save conflict giữ draft, cho nạp lại/so sánh.
- Preview ticks tính từ shared scheduler contract hoặc API, không duplicate thuật toán không kiểm chứng trong JS.
- Máy/worker không chạy thì không giả next run đã thực hiện. Hiển thị “Ứng dụng cần hoạt động để chạy lịch”; catch-up history ghi mốc scheduled và actual khác nhau.
- Phạm vi hai ca không là full-day coverage. Link “Thu bổ sung khoảng khác” mở manual window, không âm thầm đổi lịch.

## 6. Lượt chạy và trạng thái

| Backend state | Copy chính | Hành động / không gây nhầm |
| --- | --- | --- |
| NOT_READY / UNVERIFIED | Chưa sẵn sàng thu thập Threads | Lý do cụ thể và “Kiểm tra kết nối”; không nói 0 kết quả |
| QUEUED | Đã nhận yêu cầu, đang chờ xử lý | Run ID/window thật; tránh double click |
| PROBING | Đang kiểm tra truy cập | Bounded timeout; không load skeleton vô hạn |
| COLLECTING | Đang tìm bài / đọc bình luận | Count observed và count đã lưu riêng, không % giả |
| WAITING_RETRY | Tạm dừng, đang chờ thử lại | Mốc retry nếu biết; giữ phần đã lưu |
| DRAINING | Đang lưu phần dữ liệu đã thu | Pending ingest count, chưa báo hoàn tất |
| SUCCEEDED + EMPTY_VERIFIED | Không thấy kết quả trong tập tìm kiếm quan sát được | Có query/window/provider, tránh “không có phản ánh” |
| SUCCEEDED | Đã lưu kết quả lượt chạy | Tổng committed unique và bounds; không “đã lấy toàn bộ Threads” |
| PARTIAL | Đã lưu một phần; còn dữ liệu chưa đọc được | Scope/gaps/deferred và “Thử lại phần chưa hoàn tất” |
| BLOCKED / AUTH_REQUIRED | Cần đăng nhập / kiểm tra quyền truy cập | Chỉ platform này bị chặn; không disable Facebook |
| FAILED | Lượt thu thập chưa hoàn tất do lỗi | Reason tiếng Việt, retry; raw còn lại nếu có |
| CANCELLED | Đã dừng; giữ phần dữ liệu đã lưu | Window/checkpoint và count đã commit |
| Classifier PENDING/FAILED | Đã lưu · Đang chờ phân loại / Phân loại lỗi | Kho vẫn dùng được, không biến thành crawl failed |

Mọi status có timestamp/copy, không chỉ màu. Lịch sử rows: thời gian chạy, platform, dự án/query scope, window, trigger, phương thức, đã lưu post/comment/reply, outcome và thiếu dữ liệu. Detail giải thích các technical errors; overview không dump parser stack/cursor/token.

## 7. Kho dữ liệu và Phản ánh dùng chung

### Bộ lọc

| Field | Vị trí | Backend binding proposal |
| --- | --- | --- |
| Nền tảng | Chính, cả hai tabs | `platform`; allowlist mới từ catalog, không frontend enum riêng |
| Dự án theo dõi | Chính | `project_id`, scope từ nguồn/query; basis explicit khi model filter khác |
| Ngày + tính theo | Chính; dễ thấy Ngày đăng/Ngày thu | `start_date/end_date/date_basis`; UTC/VN conversion chung |
| Tìm trong nội dung đã lưu | Chính | `keyword` raw/OCR, không gọi discovery |
| Nhóm vấn đề/kết quả | Chính ở Phản ánh | `issue_id/relevance`; labels/counters backend |
| Group Facebook | Mở rộng, Facebook | `source_id`; không áp group vào Threads |
| Truy vấn Threads | Mở rộng, Threads | `query_id` với observations; nhiều query không duplicate row |
| Loại nội dung/ý định/xử lý/đánh giá | Mở rộng | `node_type/intent/processing_status/review` |
| OCR/chất lượng trích xuất | Kho dữ liệu, mở rộng | Capability/options của raw/OCR backend |

Chọn all platforms: Nguồn là selector nhóm Facebook/Truy vấn Threads với platform labels; đổi platform loại filter nguồn không tương thích và thông báo “Đã bỏ bộ lọc nguồn của nền tảng trước”. Query/source filters không dựa caption substring. Query version archived vẫn có thể lọc history.

Preset Hôm nay/7 ngày/14 ngày áp ngay, có applied chips/counter; dates tùy nhập giữ Apply. Xóa từng chip và Xóa bộ lọc tạo request mới có abort/sequence guard, không cần Apply lần nữa. Chỉ báo pending filter tách số kết quả đang xem.

### Bảng và chi tiết

Bảng Phản ánh: **Nền tảng | Nguồn | Nội dung | Ngày đăng | Dự án | Nhóm vấn đề | Ý định | Kết quả | Xử lý | Đánh giá | Ghi chú**. Duy trì đánh giá/ghi chú tách cột. Bảng rộng cuộn ngang có caption và headers; có chế độ mobile list kế thừa, không ép cả trang cuộn ngang.

Nguồn Facebook: tên/link group. Nguồn Threads: query phát hiện và tác giả/profile nếu có; multiple queries tóm tắt `+n truy vấn` mở lineage, không nối caption với nguồn. Badge post/comment/reply + platform rõ. Các IDs kỹ thuật nằm detail/Excel diagnostic, không giành diện tích bảng chính.

Chi tiết hội thoại hiển thị:

1. Node đang xem, platform/author/link/time/raw text/OCR riêng.
2. Parent/root với nhãn **Ngữ cảnh ngoài khoảng ngày** nếu cũ; không tính vào total đang lọc.
3. Replies đã lưu, phân trang và nhãn coverage; thiếu parent hoặc replies chưa đọc được nói rõ.
4. Taxonomy/intent/relevance + evidence/lý do tiếng Việt, processing state và model version khi cần truy vết.
5. Đánh giá và ghi chú riêng, nháp/optimistic conflict giữ semantics hiện có.

Không suy “không có bình luận” từ việc storage chưa có comment. Link từ run tới Kho lọc `platform+run_id` theo observations, gồm unknown/out-of-window context; link Phản ánh theo node publication window cho mục tiêu ngày phản ánh. Tên liên kết giải thích khác biệt.

## 8. Loading, error, empty và accessibility

- Trang đọc có skeleton rows cho initial loading; refresh giữ bảng kèm “Đang cập nhật; dữ liệu đang xem chốt lúc…” và aria-busy. Request timeout finite, error có Retry và preserved snapshot; không xóa bảng/chỉ báo source khi health poll lỗi.
- Health polling lightweight, abort stale request, tab hidden không poll; không ghi đè query/schedule draft. Health stale nói “Chưa có cập nhật từ worker” với timestamp thay vì khẳng định worker đã chết.
- Chưa cấu hình Threads: chỉ rõ cần bộ query và connection verification; không nút “crawl” fake hoạt động. Lọc không thấy records: “Không có nội dung đã lưu khớp bộ lọc” + Xóa bộ lọc/Chọn ngày thu; khác provider empty.
- Disabled action luôn có lý do text gần nút; invalid date/end vượt hiện tại, query rỗng, schedule overlap ở control và summary. Error code technical mở qua “Chi tiết lỗi”.
- Native controls, labels/error association, keyboard platform/subtab navigation, focus giữ ở action hoặc result heading đúng chỗ; aria-live polite cho stage, không đọc mọi counter mỗi poll.
- Copy tiếng Việt, giờ Việt Nam, số/ngày locale. Caption Unicode/long usernames/URLs wrap; không truncate evidence detail. Status không chỉ dựa màu, focus-visible và min target 44 px; test 390 px, 1440 px, zoom 200% và reduced motion khi implementation.

## 9. Acceptance UX ↔ backend

| ID | Tác vụ / expected | Backend / feature AC |
| --- | --- | --- |
| THR-UX01 | Chọn Threads trong Thu thập đổi query/schedule/status đúng, không đổi lịch FB | Platform dispatch/schedule; AC09/11 |
| THR-UX02 | Chọn dự án nạp recommend; query rộng tắt; scope post+replies capability gated | Catalog/query readiness; AC01/02/10 |
| THR-UX03 | Run nhận fixed window/query snapshot; form đổi không đổi run | Run contract/idempotency; AC01/09 |
| THR-UX04 | Đang lưu khác đã lưu; LLM lỗi vẫn đọc Kho | ACK/outbox/classification; AC06/07/08/11 |
| THR-UX05 | Parent cũ/reply mới lọc đúng ngày; context ngoài ngày rõ | Node publication + context; AC03/04/11 |
| THR-UX06 | PARTIAL/unknown/replies denied/budget lỗi đều có số/lý do/next action | Outcome/coverage; AC02/10/13 |
| THR-UX07 | Platform/query/source filters backend, Xóa/preset apply, Excel cùng view | Catalog/view snapshot/export; AC05/11 |
| THR-UX08 | Lưu config khác bật lịch; FB/Threads độc lập, restart/chốt ca | Versioned schedules/lease/catch-up; AC09 |
| THR-UX09 | Desktop/mobile/keyboard/loading-timeout/copy; raw/reflections consistent | UI contract/offline browser, AC11 |

Đã kiểm tra desktop/mobile và sửa lỗi project catalog/edit-version/idempotency. Detector trên HTML/CSS/JS không có hard error; hai cảnh báo về bảng full-bleed và CSS border cũ được đối chiếu thủ công, không thay layout chỉ để loại cảnh báo. UI đã đọc 43 Threads raw thật; export theo snapshot, clear filters và draft/review được kiểm thử Chromium. Live quality/coverage và monitoring ba ngày vẫn chưa nghiệm thu. Giữ yêu cầu không dùng agent phụ.

## 10. Handoff cho builder

P0 chọn provider → P1 schema/identity/query contract → P2 storage + ACK → P3 adapter → P4 classify → P5 per-platform scheduler → P6 nối UI. Có thể dựng UI fixture trong lúc backend chưa xong nhưng phải ghi **Mô phỏng**, không trộn data giả vào kho hoặc expose buttons gọi endpoint chưa tồn tại.

Điểm chưa chốt: provider/public-replies capabilities ở P0, held-out labels và taxonomy quality ACP. Bố trí tab/nền tảng đã chốt với người dùng; không cần hỏi lại ở implementation. Design này giữ system hiện hành, không yêu cầu rebrand hoặc thay framework.
