# P0: taxonomy baseline, bộ mẫu và API decision

> **Snapshot lịch sử theo ngày trong tài liệu.** Các trạng thái “chưa triển khai”, disabled hoặc lỗi probe chỉ áp dụng cho lượt kiểm tra đó. Đối chiếu code/config hiện hành ngày 11/10/2026 tại [trạng thái dự án](../current-state.md); không dùng snapshot này để kết luận runtime hiện tại.

Ngày 09/10/2026. P0 **IN_PROGRESS**, chưa ACCEPTED toàn phase.

## Quyết định đã có

Người dùng xác nhận taxonomy draft v1 khá đầy đủ và yêu cầu triển khai tiếp. Ghi nhận **USER_ACCEPTED_SCOPE** cho baseline 1.0.0-draft.1; không tự ghi mentor đã approved hoặc bật runtime. Các vấn đề bổ sung lao động/an toàn và projection chi tiết còn review.

Người dùng chọn **API Gemini đang cấu hình**. Kiểm tra offline chỉ metadata: `.env` có GEMINI_API_KEY, GEMINI_API_BASE_URL và GEMINI_MODEL; key có giá trị, không xuất/log giá trị. Model identifier cấu hình `ag/gemini-3.7-flash-low`, base host `9router.cool.khokey.com`. Đây là gateway cấu hình, chưa xác minh route/API protocol hoặc model thực phía sau; không giả đây là endpoint Google trực tiếp hoặc tự thay model. Không gọi API trong bước P0 này.

Trước P4 live cần capability probe nhỏ, chốt request/response protocol, JSON/schema support, usage/token/RPM/TPM limits và ngân sách. Key present không chứng minh key valid. Không dùng quota Gemini public để suy quota của gateway này. Provider implementation chờ phần API phase; không làm lộ credential qua client.

## Bàn giao đã thực hiện

- [Taxonomy v1](../../specs/taxonomy/v1/README.md): 17 definitions, hai profiles 16 issues/group mapping, draft chưa runtime-enabled.
- [26 golden cases](../../tests/fixtures/taxonomy_v1/README.md): synthetic, đủ target/context/expected labels/evidence cho development; held-out template rỗng, không claimed human labels.
- `src.analysis.taxonomy`: đọc YAML reject duplicate keys, validate definitions/profiles/version/legacy/source references; runtime guard yêu cầu cả approved và enabled.
- `src.analysis.taxonomy_fixtures`: kiểm tra development labels/evidence references/window, không predict labels.
- `engine.taxonomy_cli`: CLI offline lặp được, report counts/versions và giới hạn verification; không network/crawl/DB/scheduler.
- `tests.contract.test_taxonomy`: mutation tests cho wrong issue/source/priority/mapping/evidence, duplicate YAML, runtime guard và old-parent/new-reply window.

Evidence: [fixture validation report](../../reports/p0-taxonomy-fixtures-validation.json). Cấu trúc kiểm tra offline không là LIVE_VERIFIED hoặc bằng chứng classifier accuracy.

Kiểm thử thực tế: **14 pass** (8 taxonomy + 6 architecture), chạy bằng `.venv/audit/Scripts/python.exe -m unittest tests.contract.test_taxonomy tests.contract.test_architecture -v`. Lượt đầu dùng Python hệ thống thiếu dependencies legacy; chạy lại trong venv dự án pass toàn bộ. Không cài thêm packages vào Python hệ thống. Report ghi riêng phạm vi loader/fixture checks và chưa hoàn tất P0.

## Công việc còn lại

1. Reviewer xác nhận expected labels và phạm vi mở rộng, tạo approved taxonomy snapshot khi đủ điều kiện; không phải hỏi lại quyền triển khai người dùng đã cấp.
2. Đã triển khai [input/output schema v2 và request-bound validator](classification-contract-v2.md), pass 20 tests validation; worker/provider integration P4 chưa triển khai. Không dùng validator như bằng chứng classification accuracy.
3. Thu held-out thật sau P2, có người duyệt; không lấy synthetic cases làm quality gate pilot.
4. Probe protocol/capability và token limits trong provider phase. Ngân sách API **DEFERRED_BY_USER**, chưa triển khai và không chặn task schema/P1. P1 raw storage có thể tiếp tục từ contracts hiện có, không cần đợi API live.

Không thay `.env`, config/projects.yaml, database đang chạy, dashboard backend hoặc lịch crawl trong bàn giao P0 này.
