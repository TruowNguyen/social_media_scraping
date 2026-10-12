# Bộ mẫu phát triển taxonomy v1

[golden.yaml](golden.yaml): **26 synthetic development cases**, 10 VinCons và 16 VinWonders Vũ Yên; 18 KEEP, 4 DROP, 4 REVIEW theo nhãn đề xuất. Không phải output LLM, dữ liệu Facebook thật hoặc held-out labels đã duyệt.

Mỗi case có target item/type/text, context root/parent, project profile và expected relevance/issues/project basis/evidence. Case giả lập group mapping theo project profile (`source_context_policy`), không chứng minh location hay người viết thật. Window test ngày 08/10 dùng UTC `[2026-10-07T17:00:00Z, 2026-10-08T17:00:00Z)`.

Cases quan trọng: VC-03 kẹt cổng chưa rõ chiều; VC-08 nợ lương ngoài phạm vi chốt; VC-10 reply mới dưới post cũ; VW-01 complaint dưới quảng cáo đại lý; VW-03 QR + hàng chờ; VW-05 hàng chờ trò chơi; VW-09 endorsement thiếu claim; VW-10 explicit other project; VW-13 missing text; VW-14 missing timestamp; VW-16 prompt injection.

```powershell
python -m unittest tests.contract.test_taxonomy -v
python -m engine.taxonomy_cli --report reports/p0-taxonomy-fixtures-validation.json
```

Validator chỉ kiểm tra cấu trúc, versions, issue/source references, ràng buộc nhãn và quote tồn tại đúng origin. **Không** xác nhận expected labels là đúng nghiệp vụ, kiểm tra entailment của model, hay đo classifier precision/recall. Không có model call, DB write hoặc kích hoạt scheduler trong CLI này.

Held-out: thu samples thật sau parser pilot, người duyệt gán nhãn riêng, không copy golden vào tập đánh giá. Dùng [template rỗng](held-out.template.json) làm hướng dẫn; hiện chưa có held-out sample. Khi taxonomy đổi nghĩa phải tăng version và cập nhật label provenance. Các label trong golden vẫn cần reviewer xác nhận.
