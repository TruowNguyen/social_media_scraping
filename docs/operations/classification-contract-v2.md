# Input/output batch classification v2

Schema/validator khởi tạo 09/10/2026, đồng bộ 11/10/2026. **IMPLEMENTED + OFFLINE_VERIFIED**, đã nối batch builder/jobs/Gemini/analyses và dashboard theo [runbook worker](classification-worker.md). Input hỗ trợ OCR image evidence, output có intent labels. Pilot model có accepted output riêng; schema tests không chứng minh accuracy. Ngân sách tiền API DEFERRED_BY_USER.

## 1. Files và cách sử dụng

Schema là JSON Schema draft 2020-12, ship cùng package dưới `src.analysis/schemas`:

- [classification-request-v2.json](../../src/analysis/schemas/classification-request-v2.json)
- [classification-result-v2.json](../../src/analysis/schemas/classification-result-v2.json)
- [validator](../../src/analysis/classification_contract.py)
- [input đầy đủ](../../examples/classification-v2/request.json) và [output mẫu](../../examples/classification-v2/result.json), dữ liệu tổng hợp không phải model output.

Validator dùng `Draft202012Validator.check_schema` và `iter_errors` theo [tài liệu jsonschema](https://python-jsonschema.readthedocs.io/en/stable/validate/). Structural schema không thay cross-field validation: request-bound IDs, profile definitions và evidence được kiểm tra bằng code riêng.

```python
import json
from pathlib import Path
from src.analysis.taxonomy import load_snapshot
from src.analysis.classification_contract import validate_request, validate_response

snapshot = load_snapshot('specs/taxonomy/v1')
request = validate_request(Path('examples/classification-v2/request.json').read_text(encoding='utf-8'), snapshot)
result = validate_response(
    Path('examples/classification-v2/result.json').read_text(encoding='utf-8'),
    request, snapshot, allow_partial=True,
)
print(len(result['accepted']), result['rejected'], result['complete'])
```

Không gọi `require_runtime_ready` trong validation offline: có thể kiểm tra draft để phát triển. Worker live đã dùng runtime snapshot `config/taxonomy/v1` và vẫn yêu cầu approval/enabled; schema check không tự duyệt taxonomy hoặc kích hoạt worker.

## 2. Input bắt buộc

| Cấp | Fields / quy tắc |
| --- | --- |
| Batch | schema_version, batch_id, taxonomy_version, taxonomy_profiles, items |
| Taxonomy profile | project_id, toàn bộ enabled issues; mỗi issue có ID/family/name/definition/include/exclude/required_evidence/priority |
| Item | item_id, revision_id, node_type POST/COMMENT/REPLY, source_id, target, context, project_candidates, context_truncated |
| Target | text string/null và evidence_id; thiếu caption không tự có complaint, nhưng OCR TARGET có text có thể bổ sung bằng chứng |
| Context | item_id/revision_id/role ROOT_POST hoặc PARENT_COMMENT/text/evidence_id; không ghép vào text target |
| Image evidence (optional) | image_evidence tối đa 60 entries/item; evidence_id/item_id/revision_id/role/text/quality_status. Role TARGET/ROOT_POST/PARENT_COMMENT, quality ACCEPTABLE/NEEDS_REVIEW/UNKNOWN; gắn đúng node/revision |
| Project candidate | project_id, basis CONTENT_EXPLICIT/PARENT_CONTEXT/GROUP_CONTEXT/UNRESOLVED và evidence_ids |

Taxonomy definitions phải khớp trusted snapshot về version/content/priority; không cho payload đổi định nghĩa thành “always KEEP”. GROUP_CONTEXT phải khớp group mapping của profile, không có text evidence giả; CONTENT_EXPLICIT phải dẫn evidence target, PARENT_CONTEXT dẫn context. Validator kiểm tra provenance/references, không tự chứng minh alias có ý nghĩa hoặc project fact đúng: resolver và pilot phải làm phần đó.

Giới hạn structural: 100 items/batch, 20 profiles, 100 issues/profile, 20 context nodes/item, 100.000 ký tự/text. Đây là trần hợp đồng, **không là token budget/model context limit**. Builder hiện chia batch tối đa 10 items, byte bound và output reserve có thể làm batch nhỏ hơn; oversized giữ raw/trạng thái riêng.

Không có author UID/key/cookies/URL/timestamps trong schema prompt này; các fields phục vụ UI/day filters lấy từ DB theo item ID. Nếu thêm metadata khác phải version contract explicit.

## 3. Output bắt buộc

Batch: schema_version, batch_id, results. Mỗi result gồm item_id/revision_id, relevance, project_matches, issues, confidence, needs_review, review_reason, drop_reason. Mỗi issue: issue_id, summary, location nullable và evidence[{evidence_id, origin_item_id, quote}].

- KEEP: caption hoặc OCR role TARGET có text, ít nhất một issue và project match resolved/context; mỗi issue cần evidence từ target, có thể thêm cha. Project context không biến thành explicit fact.
- DROP: không issues, drop_reason có nội dung, needs_review=false/review_reason=null. Raw không bị xóa bởi validator hoặc nhãn này.
- REVIEW: needs_review=true và review_reason; có thể chưa có issues/project_matches. Confidence null hoặc finite [0,1], không phải measured accuracy.
- KEEP có thể needs_review=true khi context bị cắt hoặc còn uncertainty; flag phải khớp reason. UNRESOLVED project không được dùng cho confident KEEP.
- Matches chỉ được lấy từ candidates, không nâng GROUP_CONTEXT thành CONTENT_EXPLICIT. Issue phải active trong applicable profile; duplicate issue/match không được chấp nhận.
- Evidence quote phải nguyên văn trong đúng origin đã gửi; không normalize để “sửa” lời model. Location nếu có phải xuất hiện trong input; còn entailment/attribution vẫn cần reviewer, substring check không chứng minh địa điểm vụ việc.
- Cùng quote không gán vừa kẹt cổng chưa rõ chiều vừa specific gate label; hai claims riêng trong cùng node có thể nhiều issues.
- `content_intents` optional để đọc output v2 cũ, bắt buộc với worker live mới. Validator từ chối DROP + COMPLAINT và KEEP thương mại không có COMPLAINT.
- OCR TARGET có quality khác ACCEPTABLE yêu cầu needs_review và không được DROP. OCR context chưa chắc chắn cũng yêu cầu review, ngoại trừ DROP thương mại được text target chứng minh độc lập và không dùng OCR context đó làm bằng chứng dự án/vấn đề. “Tôi cũng bị vậy” không đáp ứng ngoại lệ. Provider và validator dùng chung chính sách; [bản sửa v3](filter-policy-v3-20261011.md). OCR quote phải thuộc đúng evidence/origin đã gửi; text trong ảnh không được biến thành caption hoặc lời tác giả.

Giới hạn output: 20 issues/result, 10 evidence/issue, summary 2.000 ký tự, quote 5.000 ký tự, location 500 ký tự. Không nhận extra keys/unknown enum, duplicate JSON keys, NaN/Infinity hoặc overflow, code fences/JSON hỏng. Errors không in raw input/output/secret.

## 4. Strict và partial modes

`validate_response(..., allow_partial=False)` mặc định reject cả batch nếu bất kỳ item lỗi/thiếu/thừa/trùng. `allow_partial=True` trả:

```json
{
  "accepted": [],
  "rejected": {"comment_002": "MISSING_RESULT"},
  "batch_errors": [],
  "complete": false
}
```

Đây là shape minh họa. Accepted chứa results đã validated; rejected keyed đúng requested item IDs, worker có thể retry riêng. Duplicate ID loại **mọi** copies của ID đó, không nhận copy đầu tiên. Unknown IDs vào batch_errors và không được lưu. JSON/envelope invalid luôn fail toàn bộ, không partial accept text không parse được. Item count/order không dùng để map kết quả.

Validator không retry/gọi API/upsert analysis hoặc filter raw; các thao tác đó đã thuộc worker/service, giữ trách nhiệm riêng.

## 5. Kiểm chứng

```powershell
.\.venv\audit\Scripts\python.exe -m unittest tests.contract.test_classification_contract tests.contract.test_taxonomy tests.contract.test_architecture -v
```

Increment ban đầu ngày 09/10 đã pass **34 tests**: 20 validation + 8 taxonomy + 6 architecture, [report lịch sử](../../reports/p0-classification-contract-validation.json). Coverage hiện còn có [intent tests](../../tests/contract/test_content_intents.py), [OCR tests](../../tests/contract/test_image_ocr.py), gateway/jobs/worker suites. Kết quả kiểm tra toàn bộ offline trong [audit đồng bộ](../documentation-drift-audit-2026-10-11.md).

Đây không là verification model chống prompt injection hoặc accuracy đạt target. Model đã có pilot riêng; money budget vẫn deferred, timeout/retry/technical bounds của worker không phải ngân sách tiền hoặc quota gateway đã xác minh.
