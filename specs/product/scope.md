# Scope và provenance

Trạng thái tài liệu: **DOC_VERIFIED**, 2026-10-08. Snapshot [prd.md](prd.md) được copy nguyên byte từ `D:\task\social_listening\PRD_SmartCity_Operational_Social_Listening_VinCons_v0.1.md`; SHA256 `92a23ae94549cd4b94c7d5b2b215121a3e760ed7c03f4c0285fb539e4219efb7`. Không sửa nội dung, BOM hoặc newline của snapshot. Các quyết định sau PRD nằm trong [specs index](../README.md), không ghi đè lịch sử PRD.

Scope acquisition v1: public Facebook groups, TikTok keyword/hashtag, SerpApi Facebook/TikTok/YouTube discovery và queue review. Config hiện 14 Facebook groups VERIFIED/enabled, Google bật, TikTok search tắt; watchlist seed vẫn DRAFT. Comments và lịch/OCR/classifier là increment raw v2 riêng đã triển khai, không gán vào contract acquisition v1. Page/private group/Web/News ngoài scope; legacy giữ schema riêng.

Business: SITE_ACCESS_CONGESTION P0, CUSTOMER_COMPLAINT P1; KEEP/DROP/REVIEW theo PRD, social signal vẫn là claim chưa xác minh. PASS heuristic không tự là KEEP. V1 clear commercial intent chặn trước fetch/persist; raw v2 lưu POST/COMMENT/REPLY trước filter/classify, giữ raw DROP và xét child độc lập.

Đồng bộ 11/10/2026: raw storage/tasks/scheduler, taxonomy 1.0.0, Gemini, OCR POST và workspace/reviews/Excel đã có implementation. Full canonical/unified-evidence/social-signal/Excel PRD v1 cùng product KPI/ACP vẫn chưa hoàn tất. [Trạng thái hiện hành](../../docs/current-state.md) và runbooks tách evidence khỏi target scope. Timestamp UTC; lịch dùng giờ Việt Nam UTC+7, hai khung 05:00–08:30/17:00–18:30 với closing tick. Reviewer/SLA/retention và held-out quality vẫn pending.

Traceability và trạng thái từng FR: [requirements matrix](../traceability/requirements-matrix.md). Kết quả triển khai thực: [TODO](../../TODO.MD).
