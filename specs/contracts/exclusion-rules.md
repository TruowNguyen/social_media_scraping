# Rule loại nội dung thương mại/tuyển dụng/trao đổi

## Policy hiện hành: group tracing raw v2 / acquisition v1

Đồng bộ 11/10/2026: dashboard và conversation CLI đã dùng [truy vết raw v2](../features/facebook-group-tracing.md), lưu bài/comment/reply trước rồi phân loại. Các intent loại khỏi **view phản ánh** không chặn fetch và không purge kho raw v2; bài cha tuyển dụng/bán hàng không loại comment khiếu nại. Raw, analysis và review tách theo [conversation-record-v2](conversation-record.md). Acquisition CLI v1/Google routing vẫn dùng prefilter audit-only bên dưới; legacy collectors không đọc YAML. Không áp dụng purge v1 cho raw v2.

Ngày: **08/10/2026**. Requirement: người dùng yêu cầu không crawl dữ liệu bán hàng, tin tuyển dụng, tin mua bán, tin trao đổi. Đã có prefilter runtime trong acquisition engine và tests xác nhận prefilter DROP không fetch/queue/persist raw; heuristic bảo thủ giữ complaint/mixed/ambiguous để REVIEW. [Implementation/evidence](../../docs/acquisition-implementation.md). Legacy collectors không đọc rule YAML; live acceptance còn pending.

## Rule contract

Runtime 11/10: `commercial-context-v3` thu hẹp bảo vệ theo ngữ cảnh. “Không phải trung gian” trong tin tuyển dụng hoặc “không phải xếp hàng” trong quảng cáo không tự chứng minh complaint. OCR target/context được phân biệt; raw v2 giữ nguyên và chỉ enqueue lại đầu vào chịu ảnh hưởng. [Triển khai và acceptance](../../docs/operations/filter-policy-v3-20261011.md).

`NO_SALES_RECRUITMENT_BUY_SELL_EXCHANGE` trong `config/exclusions.yaml` (`exclusion-config-v2`) được watchlist tham chiếu qua `prefilter_rule_ids`. Version v1 chỉ SIGNALS_ONLY; v2 thêm explicit action policy, không thay top-level taxonomy. Không có runtime v1 đã release cần migration DB trong bước này.

Loại các bài có **mục đích chính rõ ràng**: SALES_MARKETING, RECRUITMENT, REAL_ESTATE_LISTING, BUY_SELL, GOODS_EXCHANGE, RENTAL, LOAN_DEBT. RENTAL gồm chào cho thuê và tìm thuê; LOAN_DEBT gồm chào vay, tìm vay, đáo hạn và mua bán nợ. “Trao đổi” trong rule nghĩa là giao dịch trao đổi hàng hóa; không mặc định là trao đổi ca làm hoặc thảo luận vận hành. GENERAL_PR chưa thuộc rule mới.

Tiêu đề chào tuyển dụng/thuê/mua bán/vay nợ rõ ràng đủ để DROP, không bắt buộc có số điện thoại, “liên hệ” hoặc mức lương. Chuẩn hóa Unicode compatibility để nhận diện chữ cách điệu. Snippet nhắc tên group tuyển dụng không tự chứng minh intent của bài; vẫn giữ REVIEW nếu chưa rõ. Khiếu nại nợ lương, cảnh báo lừa đảo và trao đổi ca làm được bảo vệ. Rule ID hiện có được giữ để các watchlist tiếp tục tham chiếu.

Caption/metadata candidate được đọc tạm để xác định intent, trước full-post/comment/media acquisition. Keyword là tín hiệu, không là điều kiện sufficient để DROP. Không dùng riêng tên group để DROP cả nguồn. Bài có complaint/congestion vận hành phù hợp scope hoặc mixed/ambiguous intent phải giữ để review/classification; không tự gộp thành IRRELEVANT.

Match bị loại phải: dừng deep fetch/comments/media/LLM; không lưu raw content/media; không export Signals; lưu rejection metadata tối thiểu cùng rule/drop_reason. Allowed audit fields: platform_item_id, source_id, source_url, crawl_run_id, collected_at, rule_id, drop_reason. Drop reason không chép lại raw nội dung bị loại.

Khi chỉ có caption không đủ để nhận biết, không giả định video là tuyển dụng/bán hàng; chuyển REVIEW. Nếu một caption chứa cả chào hàng và phản ánh, xem operational exception trước khi drop. Không tạo confidence giả từ một từ khóa.

## Integration với adapter và discovery queue

[Source Adapter](source-adapter.md) định nghĩa prefilter_decision `PASS|DROP|REVIEW`, tách relevance `KEEP|DROP|REVIEW` downstream. PASS chỉ cho phép tiếp tục acquisition; chưa kết luận relevant. Adapter discovery đọc caption/metadata tối thiểu vào bộ nhớ, engine gọi filter trước permalink/full-content fetch và trước persist raw. Media/ASR/LLM không chạy ngầm khi gọi discovery.

Áp dụng cùng rule cho [Facebook](../features/facebook-adapter.md), [TikTok search](../features/tiktok-search.md) và [Google social discovery](../features/google-social-discovery.md). Google snippet là SEARCH_SNIPPET, không platform text; khi intent bài rõ có thể DROP trước queue. Snippet không đủ/mixed/complaint thì REVIEW; eligible link ngoài approved sources đi [Discovery Queue](discovery-queue.md), không full-fetch để vượt approval gate.

Container link/group/account/channel không có post intent: tên TUYỂN DỤNG không làm container DROP. Keyword “trao đổi” riêng không chứng minh giao dịch hàng hóa. GENERAL_PR vẫn là signal trong config, chưa thêm vào hard-drop user rule; full PRD FR-06 còn cần downstream filtering riêng.

Rejection metadata vẫn chỉ gồm platform_item_id, source_id, source_url, crawl_run_id, collected_at, rule_id, drop_reason; native ID có thể null nếu URL chưa resolve. Không lưu candidate caption/title/search_snippet/raw DOM/response/media hoặc queue payload cho clear DROP. Counters source/run được phép giữ aggregate DROP count, không nội dung bị loại. Retry/resume/debug logging phải giữ cùng retention rule.

Browser ban đầu có thể hiển thị asset/thumbnail do page load; “không download media” là dừng tác vụ tải/lưu media và deep processing sau DROP, không hứa không có network request ban đầu. Screenshot/HTML/trace tự động tắt trong pilot để không vô tình retain raw nội dung bị loại.

## Acceptance cần enforce khi implementation

Runtime cập nhật 09/10/2026: nhận diện thêm “tiếp nhận thông tin nhân sự”, “tìm kiếm ứng viên”, “việc làm hấp dẫn”, “tuyển dụng khối văn phòng” trong title/caption và search snippet. Snippet chỉ nêu tên group tuyển dụng hoặc nội dung sau “Other posts” không đủ để loại bài. Phản ánh nợ lương/lừa đảo vẫn được giữ để review. Snapshot giao diện cũng tái kiểm tra rule hiện tại trước khi hiển thị record/queue cũ. Các kiểm thử regression nằm trong `tests.contract.test_content_cleanup`, `test_acquisition`, `test_dashboard`; không suy ra đã kiểm chứng mọi bài live, nhất là bài chưa lấy được nội dung.

| Case | Expected |
| --- | --- |
| “Bán căn hộ, liên hệ để nhận bảng giá” | DROP / REAL_ESTATE_LISTING |
| “Tuyển công nhân cơ hữu, nhận hồ sơ ứng tuyển” | DROP / RECRUITMENT |
| “Cần mua xe máy, ai thanh lý liên hệ” | DROP / BUY_SELL |
| “Đổi xe lấy máy tính, bù tiền theo thỏa thuận” | DROP / GOODS_EXCHANGE |
| “Nhân viên bán hàng không phản hồi phản ánh của tôi” | Không auto-drop; classify/review complaint |
| “Cổng công trường ùn, công nhân chờ vào trong buổi tuyển dụng” | Không auto-drop; classify/review congestion |
| “Trao đổi ca làm ngày mai” | Không auto-drop bởi keyword trao đổi |
| “Tôi đã trao đổi với quản lý nhưng chưa xử lý” | Không auto-drop; classify/review complaint nếu phù hợp scope |
| Video không caption hoặc không rõ intent | REVIEW, không fabricate nhãn |
| Bài operational trong group có tên TUYỂN DỤNG | Không auto-drop theo tên group |
| Rule match | Full fetch/comments/media/LLM không được gọi; raw content không lưu; rejection metadata có rule/reason |

Các case trên là acceptance spec, **chưa phải runtime tests đã pass**. Bộ YAML chỉ đã được kiểm tra parsing, types và reference consistency. Không tuyên bố crawler hiện lọc được dữ liệu này trước khi adapter/filter được triển khai và test observable behavior.

Traceability integration: AD-AC-05/06, DQ-AC-09, FB-004 → FB-AC-05/06, TT-004 → TT-AC-05/06, GG-006 → GG-AC-05/06. Behavioral assertions phải xác nhận full-fetch/media/ASR/LLM/raw-persistence/queue calls không xảy ra khi DROP, không chỉ kiểm tra nhãn. Các case này vẫn PLANNED.
