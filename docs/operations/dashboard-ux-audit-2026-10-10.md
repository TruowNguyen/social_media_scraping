Method: dual-agent (A: /root/ux_design_review · B: /root/ux_evidence_review)

# Đánh giá giao diện và phương án tối ưu — 10/10/2026

> **Snapshot lịch sử theo ngày trong tài liệu.** Các trạng thái “chưa triển khai”, disabled hoặc lỗi probe chỉ áp dụng cho lượt kiểm tra đó. Đối chiếu code/config hiện hành ngày 11/10/2026 tại [trạng thái dự án](../current-state.md); không dùng snapshot này để kết luận runtime hiện tại.

Lần sửa trước tập trung vào bộ lọc, tốc độ và responsive, chưa kiểm chứng đủ tác vụ đọc–đánh giá–báo cáo. Test pass không chứng minh giao diện dễ sử dụng. Đánh giá này dùng hai bên độc lập, đọc code và thao tác trên cả bốn tab của dashboard thật ở desktop và mobile; không chạy crawl, gọi model, sửa lịch hoặc lưu đánh giá.

**Kết luận:** giao diện có nền tảng hiển thị tốt nhưng còn làm người dùng khó xác định phạm vi kết quả, ngữ cảnh phản ánh và trạng thái công việc. Ưu tiên sửa tính đúng và bảo vệ công việc đang làm, sau đó tổ chức lại luồng duyệt; màu sắc là bước cuối. Không tìm thấy lỗi P0 chặn hoàn toàn tác vụ trong phạm vi đã kiểm tra; có nhiều lỗi P1 gây khó khăn hoặc nhầm lẫn đáng kể.

## 1. Điểm đánh giá

Điểm là đánh giá heuristic về khả năng sử dụng, không phải tỷ lệ độ chính xác của crawler/model hay chứng nhận accessibility.

| Tiêu chí | Điểm / 4 | Điểm yếu chính |
| --- | ---: | --- |
| Nhận biết trạng thái hệ thống | 3 | Trạng thái thu thập, phân loại và lịch còn rời rạc |
| Ngôn ngữ phù hợp người dùng | 2 | Nhiều tên gọi kỹ thuật và trạng thái gần nghĩa |
| Quyền kiểm soát | 2 | Chưa bảo vệ bản nháp và trạng thái đang đọc |
| Nhất quán | 2 | Ý nghĩa thời gian, dự án và cách áp dụng bộ lọc khác nhau |
| Ngăn ngừa sai sót | 1 | Mất ghi chú chưa lưu; kết quả cũ mang phạm vi ngày mới |
| Dễ nhận biết, ít phải nhớ | 2 | Thiếu bài cha, phải tìm lại cùng nội dung giữa hai tab |
| Hiệu quả thao tác | 2 | Thiếu luồng duyệt liên tục và chế độ xem đã lưu |
| Bố cục và tính gọn | 3 | Giao diện bình tĩnh nhưng bộ lọc/bảng chiếm quá nhiều chỗ |
| Nhận biết và khắc phục lỗi | 2 | Chưa giải thích lỗi từng nội dung/nguồn và cách xử lý |
| Hướng dẫn đúng lúc | 2 | Giải thích quan trọng xa nơi quyết định |
| **Tổng** | **21 / 40** | **Cần cải thiện đáng kể luồng sử dụng** |

Điểm tốt cần giữ: dữ liệu gốc được giữ trước lọc; giao diện thừa nhận thời gian/coverage chưa xác minh; bộ lọc phân loại chỉ đọc kết quả đã lưu; màu và control nhất quán; tab hỗ trợ bàn phím; có phân trang và khả năng tắt tự cập nhật.

## 2. Năm vấn đề cần xử lý trước

1. **Bảo vệ ghi chú và việc đang đọc.** Đã nhập ghi chú nháp, đổi loại nội dung, đổi lại: ghi chú biến mất, không cảnh báo. Mở caption trong tab phân loại: sau lượt tự cập nhật khoảng 15 giây, caption đóng lại. Cần bản nháp theo identity, trạng thái chưa lưu và cập nhật hàng mà giữ focus/scroll/chi tiết đang mở.
2. **Kết quả phải có phạm vi riêng, đúng với lượt đã chạy.** Đổi ngày crawl từ 10/10 sang 9/10 mà không chạy mới: vẫn 45 kết quả, hàng đầu ngày 10/10, trạng thái vẫn nói đúng khoảng ngày. Cần tách “kết quả của lượt trước” khỏi “tham số lượt tiếp theo”, không gắn kết quả cũ vào input mới.
3. **Đọc phản ánh cần đủ hội thoại.** Comment/reply đang nằm riêng, không có bài gốc hoặc bình luận cha. Trong mẫu 9 bình luận, 3 URL không có `comment_id`; chưa kiểm tra nơi Facebook thực sự mở tới. Cần panel hội thoại và đánh dấu link chỉ tới bài gốc khi thiếu deeplink.
4. **Model và người duyệt cần gặp nhau trên cùng một nội dung.** Kết quả model ở một tab, đánh giá/ghi chú ở tab khác; chưa có đường đi tới đúng bản ghi. Cần cùng identity và panel hiển thị riêng quyết định bộ lọc, model và người đánh giá.
5. **Trạng thái vận hành và phạm vi lệnh phải rõ.** Trang mở đầu là Google dù có hơn 2.000 nội dung trong kho. Trạng thái lịch bị đặt sau form. Nút phân loại gửi request rỗng, không gửi bộ lọc đang chọn: cần ghi rõ phạm vi thực thi, số nội dung đủ điều kiện và tiến độ thay vì tạo cảm giác chỉ xử lý bảng đang nhìn.

## 3. Danh sách vấn đề đầy đủ

“Tái hiện” là đã thao tác thấy hành vi; “Quan sát” là đã thấy UI; “Code/rủi ro” là cơ chế thấy từ code, chưa thử hành động ghi hoặc tình huống tương ứng. P1: sửa trước nghiệm thu; P2: sửa ở đợt tiếp theo; P3: hoàn thiện.

| ID | Mức | Bất tiện / nhầm lẫn và bằng chứng | Phương án |
| --- | --- | --- | --- |
| AUD-01 | P1 | **Tái hiện:** đổi bộ lọc làm mất ghi chú chưa lưu | Giữ bản nháp theo record; cảnh báo lưu/bỏ; đổi tên nút thành “Lưu đánh giá và ghi chú” |
| AUD-02 | P1 | **Tái hiện:** thay ngày crawl nhưng 45 kết quả 10/10 vẫn được nói đúng khoảng 9/10 | Hiện phạm vi kết quả đã chạy; đánh dấu tham số đang sửa; không đổi nhãn kết quả theo input mới |
| AUD-03 | P1 | **Quan sát:** comment/reply thiếu bài cha; mẫu 3/9 link comment không có comment_id | Panel hội thoại, điều hướng bài cha/root; ghi rõ link fallback và phần context chưa thu được |
| AUD-04 | P1 | **Quan sát:** không chuyển thẳng từ kết quả model sang đánh giá đúng bản ghi | Dùng panel và identity chung; mở dữ liệu gốc bằng một thao tác |
| AUD-05 | P1 | **Tái hiện:** tự cập nhật đóng caption đang đọc | Giữ expanded/focus/scroll theo identity; báo có dữ liệu mới hoặc cập nhật hàng không phá phiên đọc |
| AUD-06 | P1 | **Code/rủi ro:** nút phân loại cạnh bộ lọc không gửi project/date/filter đang chọn | Tách lệnh khỏi toolbar lọc; ghi rõ hàng chờ toàn hệ thống hay phạm vi đã chọn; nếu cần scoped run phải bổ sung backend |
| AUD-07 | P1 | **Quan sát:** trạng thái lịch/nguồn/worker nằm ở nhiều chỗ; lịch mobile ở khoảng 1.602 px từ đầu trang | Thanh trạng thái chung; đưa trạng thái lịch lên trước cấu hình; hiển thị lượt gần nhất và lần hoạt động cuối |
| AUD-08 | P1 | **Quan sát:** bảng phân loại mobile xuất hiện khoảng 1.852 px từ đầu, tab phân loại ngoài mép phải | Bộ lọc thu gọn; navigation có đủ điểm đến; mobile dùng danh sách và màn hình chi tiết |
| AUD-09 | P1 | **Quan sát:** bảng kho 1.600 px, cột ghi chú/dự án xa nội dung | Giữ bảng để so sánh; chỉnh sửa ở panel có nội dung đang duyệt, không đặt editor ở các cột ngoài màn hình |
| AUD-10 | P1 | **Quan sát/code:** “Phân loại lỗi” thiếu nguyên nhân riêng, thời điểm và đường phục hồi | Hiện lỗi dễ hiểu, lần thử gần nhất và hành động phù hợp; retry thật cần hỗ trợ backend |
| AUD-11 | P2 | **Tái hiện/giải thích:** lọc kho ngày thu thập 9/10 có 773 mục, cột lần gần nhất lại là 10/10 | Đây là any-observation đối chiếu last-seen, không chứng minh query sai. Đổi nhãn thành “Có lần thu thập trong khoảng”; hiện lần khớp, phân biệt lần gần nhất |
| AUD-12 | P2 | **Quan sát/code:** lọc ngày đăng bỏ nội dung chưa rõ thời gian nhưng giải thích xa bộ lọc | Hiện số mục chưa xác minh và lựa chọn tra theo ngày thu thập; không tính chúng là đã xác nhận đúng ngày |
| AUD-13 | P2 | **Code/rủi ro:** kho gắn dự án theo nguồn/dấu hiệu, model gắn theo kết quả phân loại | Giữ hai tiêu chí riêng; nhắc lại trong tiêu đề kết quả; không làm nội dung đang chờ model biến mất mà không giải thích |
| AUD-14 | P2 | **Quan sát/code:** “Cần xem xét”, “Chưa phân loại”, “Đã loại” trộn các tầng quyết định | Tách xử lý / bộ lọc / model / người duyệt. Hiện “Bộ lọc loại” khác “Model loại”; không đổi đánh giá người thành kết quả model |
| AUD-15 | P2 | **Quan sát:** một hàng là post/comment/reply; dễ gọi tất cả là bài hay phản ánh, đếm trùng cuộc hội thoại | Ghi đơn vị nội dung; có count bài/comment/reply và hội thoại riêng khi backend hỗ trợ; không tự gộp mọi comment thành một phản ánh |
| AUD-16 | P2 | **Quan sát/code:** kho auto-filter nhưng nút “Lọc / làm mới”; advanced thiếu nhãn bộ lọc đang áp dụng | Thống nhất chọn là áp dụng; nút riêng làm mới; chips ở cả hai nơi; ẩn nâng cao phải hiện số điều kiện |
| AUD-17 | P2 | **Quan sát:** dữ liệu trống chỉ hiện số thông tin thiếu và trace ID khó hiểu | Chỉ rõ thiếu caption, thời gian, parent hay comments; hiện lượt crawl bằng thời gian/trạng thái, ID ở phần kỹ thuật |
| AUD-18 | P2 | **Quan sát:** “Profile Facebook đang được sử dụng” nằm trong câu dài, 14/14 sẵn sàng dễ bị hiểu đã crawl tốt | Tách nguồn đủ điều kiện khỏi truy cập/crawl thành công; cảnh báo phần bị chặn, hướng dẫn đóng phiên đang dùng và kiểm tra lại an toàn |
| AUD-19 | P2 | **Code/rủi ro:** Excel lấy input hiện tại, chỉ ghi chú đã lưu; chưa có xuất trực tiếp kết quả phân loại | Xuất theo snapshot bộ lọc thành công; hiển thị count/all-pages/saved-only; báo nháp chưa lưu; tách export raw khỏi báo cáo phân loại |
| AUD-20 | P2 | **Quan sát:** Google/hashtag có thể bị hiểu là quét đủ dữ liệu nền tảng trong ngày | Gọi là tìm link Google, hiển thị provider và phạm vi; hashtag Google là truy vấn, không phải native hashtag crawl; không hứa coverage đầy đủ |
| AUD-21 | P2 | **Quan sát/code:** empty state crawl dùng hướng dẫn nhập keyword/hashtag của form search | Empty/loading/failed/no-match cần thông điệp đúng tác vụ, không cùng một “chưa có dữ liệu” |
| AUD-22 | P2 | **Code/rủi ro:** reload quay về Search và không giữ view/filter/page | URL hoặc chế độ xem đã lưu cho bộ lọc; khôi phục tab/vị trí; ghi chú nháp không đặt vào URL |
| AUD-23 | P2 | **Quan sát:** duyệt từng hàng qua nhiều trang, thiếu sort/bulk/saved view | Luồng trước–sau trong panel, lưu bộ lọc, sort; duyệt hàng loạt phải xác nhận phạm vi và có log |
| AUD-24 | P2 | **Quan sát/code:** links và nút ghi chú/đánh giá có tên lặp; cập nhật thay DOM | Accessible name có identity/nội dung; giữ focus. Sửa Ctrl+Home bị bắt như Home thường; test bàn phím, không tuyên bố đã đạt WCAG |
| AUD-25 | P2 | **Quan sát/code:** khó truy nguyên model/taxonomy/thời điểm, thiếu trợ giúp theo tác vụ | Đưa provenance vào panel; hướng dẫn ngắn ngay nơi chọn thời gian, xem nguồn và chạy lệnh |
| AUD-26 | P3 | **Quan sát:** title chỉ VinCons/search, thuật ngữ English lẫn Việt; chip search ~29,6 px | Title theo trang, nhãn tiếng Việt nhất quán; touch target gần 44 px, giữ palette và typography hiện có |

## 4. Cách tổ chức giao diện đề xuất

Giữ nền màu và control quen thuộc, đổi thứ tự theo tác vụ:

1. **Phản ánh** — điểm mở đầu: xem tín hiệu, đọc evidence, duyệt và ghi chú trên cùng bản ghi.
2. **Kho dữ liệu** — tra toàn bộ dữ liệu gốc, cả nội dung đã loại, chưa phân loại hoặc trích xuất thiếu.
3. **Thu thập** — trạng thái trước, rồi tách Chạy ngay / Lịch hằng ngày / Lịch sử lượt chạy; lịch và tham số crawl thủ công không được nhìn như cùng phạm vi.
4. **Tìm link Google** — công cụ bổ sung nguồn/link, nói rõ khác việc đọc bài và bình luận Facebook.

Thanh chung: lịch bật/tắt, lượt gần nhất, lượt tiếp theo, số nội dung đang chờ/lỗi và cảnh báo truy cập. Không dùng trạng thái registry “ready” thay cho health live.

Desktop: bảng gọn ưu tiên thời gian, nội dung, group, dự án/vấn đề và trạng thái duyệt; click hàng mở panel. Panel gồm bài gốc → bình luận cha → nội dung đang xem; thông tin chưa có phải ghi thiếu. Sau đó là chất lượng evidence, quyết định bộ lọc, kết quả model và đánh giá người, mỗi phần có nguồn riêng. Mobile: danh sách nội dung + chi tiết toàn màn hình; không ép bảng 1.600 px làm giao diện duyệt chính. Bảng vẫn là chế độ cần giữ để so sánh và xuất.

## 5. Bộ lọc đề xuất

- Chính: nội dung, dự án, khoảng thời gian có ghi rõ cơ sở, vấn đề. Group và loại nội dung là lựa chọn tiếp cận nhanh; các trạng thái/metadata nằm trong nhóm nâng cao.
- Tách bốn trục: **thu thập/trích xuất**, **xử lý phân loại**, **quyết định model/bộ lọc**, **đánh giá người**. Không dùng một “Đã loại” cho tất cả.
- Lựa chọn time rõ: “Đăng trong khoảng”, “Có lần thu thập trong khoảng”, “Thu thập gần nhất trong khoảng”. Ngày giờ Việt Nam, ngày kết thúc inclusive theo UI. Nếu thiếu timestamp, cho biết không thể xác nhận trong window.
- Giữ project theo nguồn/dấu hiệu ở kho và project do model xác định ở phản ánh; chọn project không tự khẳng định pending nodes không thuộc dự án.
- Preset count ghi rõ là count theo các điều kiện khác đang áp dụng, không phải kết quả chỉ của trang hiện tại.
- Header kết quả ghi scope đã áp dụng + count + lần cập nhật. Tham số đang sửa/pending không thay đổi header snapshot. Export và pagination dùng cùng snapshot.
- Lọc chỉ đọc dữ liệu. Chạy crawl/phân loại là lệnh riêng có scope và trạng thái; không bắt đầu vì thay filter.

## 6. Thứ tự sửa và nghiệm thu

| Đợt | Mục tiêu / output | Điều kiện chấp nhận |
| --- | --- | --- |
| 1 — Tính đúng và bảo vệ công việc | Draft protection, giữ phiên đọc, snapshot phạm vi kết quả/export, scope lệnh rõ; tập trung AUD-01/02/05/06/19 | Nhập note rồi đổi filter/page/tab/reload không mất im lặng; qua 3 lượt refresh giữ mở/focus/scroll; đổi ngày không khiến dữ liệu cũ nhận scope mới; Excel khớp snapshot và ghi chú đã lưu |
| 2 — Evidence và luồng duyệt | Panel hội thoại, mở đúng raw record từ model, human review chung identity, health và lỗi; AUD-03/04/07/10/14/17/18/25 | Từ COMMENT/REPLY tới context và đánh giá đúng bản ghi ≤2 thao tác; model/người/bộ lọc hiển thị riêng; biết trạng thái lịch/last/next/error trong 5 giây ở test người dùng; thiếu parent được ghi rõ |
| 3 — Bố cục và bộ lọc | Điều hướng theo nhiệm vụ, filter language/date semantics chung, mobile list/detail, saved view và accessibility | 390×844 có đường vào nội dung mà không đi qua 8 ô input; đọc/duyệt trên mobile chỉ cần một chiều cuộn chính; cùng điều kiện cho count, bảng và Excel nhất quán; khôi phục view; bàn phím giữ focus |
| 4 — Hiệu quả và hoàn thiện | Sort/bulk human review, báo cáo kết quả model, provenance, copy/targets/visual polish | Đánh giá hàng loạt có scope/log, không overwrite model; report đúng model + human fields; pilot end-to-end từ tín hiệu đến báo cáo với người vận hành và mentor |

UI-only có thể sửa snapshot, draft, refresh, nhãn, phân nhóm, navigation và responsive. Cần nối/bổ sung backend cho context hội thoại, health/progress thực, scoped run hoặc retry, human-review filter trong view model và report phân loại. Không thay frontend để giả lập những thông tin chưa có.

Kịch bản kiểm thử bắt buộc: lịch đang chạy; nguồn bị chặn/partial; bài cũ có comment mới đúng ngày; reply cần parent; thiếu thời gian/caption; model KEEP/REVIEW/DROP và prefilter DROP; pending/failed; bản nháp chưa lưu; ngày đổi trong lúc request pending; 0 kết quả; export mọi trang đúng scope; mở lại view trên desktop/mobile. Offline/browser fixture là regression; nghiệm thu có phiên dùng thử thực tế, không chỉ đếm số test.

## 7. Tải nhận thức, hành trình và người dùng

Tải nhận thức cao: tám filter chính, nhiều preset, bốn loại trạng thái và hai cách suy ra dự án. Cần nhớ nội dung khi qua tab khác để đánh giá. Điểm có ích là tìm được tín hiệu; sự tự tin giảm khi thiếu parent, không rõ parser lấy thiếu gì, caption đóng khi đọc, hoặc mất note. Kết thúc tốt cần xác nhận “đánh giá đã lưu” và “file này chứa đúng dữ liệu nào”.

- **Người vận hành thường xuyên:** mất thời gian tìm lại cùng record và lưu từng hàng; cần panel, saved views và thao tác liên tục.
- **Người dùng mobile/bị gián đoạn:** đi qua bộ lọc dài, cuộn ngang bảng, khó giữ nháp/view; cần list/detail và recovery.
- **Người dùng bàn phím:** tab hiện hỗ trợ tốt, nhưng cần identity rõ trên link/editor và giữ focus khi cập nhật. Chưa chạy đầy đủ NVDA.

## 8. Câu hỏi chốt thiết kế

1. Trang mở đầu: **Phản ánh + trạng thái lịch (đề xuất)** / Kho dữ liệu / Thu thập?
2. Xem bình luận: **Bảng từng nội dung + panel hội thoại (đề xuất)** / Cây hội thoại bài → bình luận → trả lời?

Chỉ hỏi lựa chọn ảnh hưởng thiết kế; không yêu cầu chọn màu/CSS hoặc xác nhận lại dữ liệu đã thống nhất.
