# Đối chiếu và đồng bộ tài liệu — 11/10/2026

**Kết luận: có documentation drift trước lượt rà soát; các sai lệch ghi trong bảng dưới đã được sửa.** README, config/specs indexes, traceability, TODO và runbooks đã được đồng bộ với code/config hiện hành. [Trạng thái dự án](current-state.md) là điểm đọc implementation; [chỉ mục tài liệu](README.md) phân biệt runbooks với plans/snapshots.

Phạm vi: 60 Markdown files ban đầu trong README/TODO/template, docs, specs, config và fixture docs; đọc code trong engine/src, YAML, executable schemas, CLI/CI và reports liên quan. **47 tài liệu hiện có được cập nhật, thêm 3 tài liệu**, tổng 63 files được kiểm tra. PRD snapshot giữ nguyên byte/hash. Báo cáo local không được xem là evidence của mọi nguồn/window hoặc quality KPI.

## Sai lệch đã xử lý

| ID | Mô tả trước đồng bộ | Kết quả đối chiếu / sửa |
| --- | --- | --- |
| DOC-01 | README/config/specs còn mô tả 7 Facebook groups hoặc nguồn disabled | [sources.yaml](../config/sources.yaml) có 14 groups VERIFIED/enabled; hai project scopes, mỗi scope 7 nguồn |
| DOC-02 | Watchlist seed và watchlist vận hành bị mô tả như một | `watchlists.yaml` seed DRAFT/disabled; [acquisition.yaml](../config/acquisition.yaml) ACTIVE/enabled, 16 references, Google bật/TikTok tắt |
| DOC-03 | README/lịch nói không có lượt 08:30 | [dashboard scheduler](../engine/dashboard.py) có closing tick; runbook ghi 08:30/18:30 và dashboard opening +1 giây |
| DOC-04 | Route/budget dashboard còn theo acquisition v1, 10 candidates/600 giây | [raw bridge](../engine/dashboard_conversations.py) dùng RAW_V2_THREADS, 1.200 giây/run, tối đa 120 giây/nguồn, [inventory 100 / threads 20](../engine/conversation_worker.py) |
| DOC-05 | Policy clear-DROP không lưu raw bị áp chung cho dashboard | Tách v1 prefilter/rejection audit với [raw v2](operations/dashboard-raw-v2.md): lưu-before-filter, giữ DROP, xét child độc lập |
| DOC-06 | Conversation/group tracing/classification consumer/UI còn bị ghi chưa implement | Core storage/tasks/rescan/worker/workspace đã có; full GT acceptance/coverage vẫn PARTIAL/pending |
| DOC-07 | Taxonomy draft disabled bị hiểu là runtime chưa bật | [config taxonomy](../config/taxonomy/v1/common.yaml) 1.0.0 APPROVED/enabled khác [review draft](../specs/taxonomy/v1/README.md) 1.0.0-draft.1 |
| DOC-08 | Project entry VinCons, classifier/comments/OCR còn ghi chưa có | Registry có VinCons ORGANIZATION_PORTFOLIO/Vũ Yên; [project filter](operations/project-filter.md) ghi Source scope khác model attribution |
| DOC-09 | Schema/worker docs còn ghi OCR chưa vào input, KEEP luôn cần caption | [Executable validator](../src/analysis/classification_contract.py) hỗ trợ image_evidence/TARGET OCR; quality chưa chắc yêu cầu review, không cho DROP |
| DOC-10 | Gateway/worker chỉ là plan hoặc probe lỗi ban đầu được coi hiện tại | Có gateway/jobs/batching/analyses; giữ các probe 08–09/10 là lịch sử, dẫn [worker evidence mới](operations/classification-worker.md) |
| DOC-11 | UXR còn PLANNED, UI hai tab hoặc thiếu hội thoại/reviews | [Workspace](operations/dashboard-workspace.md) bốn tab, snapshot/draft/versioned review/Excel đã implement; UAT vẫn pending |
| DOC-12 | Excel/review/monitoring vẫn toàn PLANNED hoặc bị coi hoàn tất toàn PRD | [Matrix 17 FR](../specs/traceability/requirements-matrix.md) ghi implementation subset, giữ exact canonical/evidence/social-signal/Excel v1 và ACP chưa hoàn tất |
| DOC-13 | Audit/refactor/P0/P1/feasibility cũ có trạng thái “hiện tại” gây hiểu nhầm | Gắn banner snapshot theo ngày và link current-state; giữ kết quả lịch sử, không nâng quality/coverage gates |
| DOC-14 | Một link skill tuyệt đối đã hỏng; PRD links phụ thuộc thư mục cha | Bỏ link cache skill riêng trên máy, đổi 7 PRD links sang snapshot trong repository; không sửa nội dung PRD |
| DOC-15 | Tài liệu cũ chưa phản ánh model switch/reuse và multi-item pilot ngày 11/10 | Giữ bổ sung model mới của workspace, đối chiếu [worker/jobs](../engine/classification_worker.py) và reports: reuse DONE còn binding hợp lệ, giữ provenance; pilot 10 native targets/2 request accepted |

Các status PLANNED còn lại trong target contracts/acceptance hoặc snapshot có ngày được giữ có chủ đích. Implementation v2 không tự là exact contract PRD v1, mentor approval, full Facebook coverage hoặc classifier accuracy.

## Kiểm tra và bằng chứng

- Offline regression: **258 tests được discover, 237 pass / 21 browser opt-in skip**, 0 failures/errors. [Kết quả máy đọc](../reports/documentation-sync-tests-20261011.json), [log](../reports/documentation-sync-unittest-verified-20261011.log). Browser opt-in bị tắt; không gọi nền tảng/model thật.
- Hai lượt đầu gặp `PermissionError / WinError 5` khi unittest sử dụng temp directories trong sandbox, gồm cả thư mục tạm chuyển vào workspace. Lượt xác minh ngoài sandbox với fixtures/DB tạm trong reports pass; không thay production database/profile/lịch.
- `engine.acquisition_cli validate`: VALID, 16 sources / 2 watchlists. Taxonomy CLI: 17 issues / 2 profiles / 26 synthetic development cases, draft disabled; runtime snapshot 1.0.0 vượt approval/enabled guard.
- `--help` của dashboard, conversation CLI, classification worker, image OCR CLI, acquisition CLI, taxonomy CLI và legacy runtime đều exit 0. Request/result examples vượt executable validation, 1 accepted synthetic result, complete=true.
- PRD SHA256 vẫn `92a23ae94549cd4b94c7d5b2b215121a3e760ed7c03f4c0285fb539e4219efb7`.
- Markdown: **629 local links được kiểm tra, 0 link/anchor hỏng, 0 link target nằm ngoài repository, 0 trailing whitespace trong docs đã sửa**; có 65 links đến artifact local. Kết quả trong [validation tổng hợp](../reports/documentation-sync-validation-20261011.json). [Diff trước/sau](../reports/documentation-sync-20261011.patch) có cả docs vốn chưa tracked; `git diff` riêng không thể hiện đầy đủ các file đó.

Lượt đồng bộ này chỉnh Markdown và tạo artifacts kiểm tra local. Các thay đổi code/config/model đã có trong workspace được giữ nguyên và dùng để đối chiếu. Không commit, restart service, crawl hoặc gọi API trong công việc đồng bộ tài liệu.

## Phần còn cần acceptance

Full configured-watchlist/window/post/comment/reply coverage, TikTok live, held-out precision/recall, OCR benchmark, UAT người vận hành/mentor, scheduling nhiều ngày, exact PRD v1 downstream và product ACP vẫn pending. Đây là khoảng cách implementation/acceptance được ghi rõ, không phải documentation drift còn bị che bởi trạng thái PLANNED cũ.

Reports/ảnh trong `reports/`, DB/profile trong `sessions/` là artifacts local được ignore; checkout mới có thể không chứa chúng. Dùng code/config/contracts trong repository làm nguồn kỹ thuật, rồi thu evidence mới khi nghiệm thu live.
