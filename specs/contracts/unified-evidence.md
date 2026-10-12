# Unified evidence v1 — PLANNED

FR-07/11; SC-02. Full unified-evidence-v1 envelope/resolver chưa hoàn tất. [OCR POST resolver/evidence](../../docs/operations/facebook-image-ocr.md) đã implement trong raw v2 và classifier, khác envelope v1 bên dưới. Caption/transcript legacy theo [legacy contract](legacy-record.md); discovery không tự gọi ASR.

Envelope: schema_version=`unified-evidence-v1`, record_id string, evidence_items array, evidence_level enum, media_status theo [canonical](canonical-record.md), missing_reasons array reason codes. Evidence item có evidence_id string, type, text string/null, media_ref string/null, method string, provider/model string/null, language string/null, original_language string/null, translated boolean, extracted_at UTC instant, status `AVAILABLE|EMPTY|UNAVAILABLE|FAILED`, error_code string/null. transcript/OCR có segments array `{start_seconds,end_seconds,text}` nullable; số finite không âm, end≥start. Không giữ error response có credentials.

Types: `caption`, `description`, `hashtags`, `transcript`, `ocr`, `visual_summary`, `metadata`, `search_snippet`. Evidence level: `METADATA_ONLY|TEXT_ONLY|AUDIO_TEXT|VISUAL_TEXT|MULTIMODAL|NONE`. Level phản ánh extraction thành công thật, không dựa vào media_refs hoặc URL. evidence_used của LLM chỉ chứa subset items thực đưa vào prompt; shorthand type phải đối chiếu được item IDs trong enrichment audit. Google search_snippet chưa là caption/raw verified text và không tự chứng minh claim trên platform.

Hierarchy v1 khi SC-02 triển khai: caption/description/metadata trước; nếu không đủ evidence thì ASR theo duration/download budget; OCR/sampled frames/vision khi còn cần. Mỗi bước đắt phải explicit/configured. Ngôn ngữ ưu tiên vi, transcription/translations giữ provenance; không dịch rồi ghi là lời nói gốc. Bản refactor không đổi WHISPER_TASK translate cũ.

Media unavailable giữ record/metadata với status UNAVAILABLE hoặc PARTIAL khi vẫn có caption. Text-only không gọi audio/vision. Missing text ghi missing_reasons, không thay bằng description invented. Clear prefilter DROP không tạo evidence hoặc tải media. Screenshots/traces platform mặc định tắt để tránh lưu content loại bỏ. Giới hạn media cost/duration được chốt ở SC-02; chưa chọn số giả định.

Acceptance EVD-01: caption đủ thì audio/vision không được gọi. EVD-02: accessible video transcript có time/provenance, unavailable giữ metadata. EVD-03: type/level tương ứng extraction thực. EVD-04: vi original/translation phân biệt. EVD-05: DROP không resolver/raw persist. EVD-06: URL-only hoặc snippet-only không được nhận như verified visual/audio evidence. Tất cả runtime acceptance PLANNED.

## Increment OCR ảnh bài Facebook ngày 09/10/2026

[Spec OCR](../features/facebook-image-ocr.md) bổ sung kế hoạch đọc chữ trong ảnh đính kèm bài, tách khỏi audio/LLM vision. Khi OCR được bật theo cấu hình/budget, caption PASS/REVIEW có text vẫn có thể đọc ảnh để bổ sung evidence; caption rõ DROP vẫn không resolver/OCR. EVD-01 không dùng để tắt OCR ảnh đã được cấu hình trong increment này; các luồng audio/vision giữ acceptance riêng.

OCR evidence dùng `type=ocr`, text gốc, media reference, engine/data/config version, UTC extracted_at và quality/status. Word boxes của ảnh không được gán audio start/end timestamps; geometry/schema và migration sẽ chốt ở OCR-T04. Tách trạng thái extraction thành công khỏi chất lượng/độ liên quan. OCR_AUTO_DROP mặc định tắt ở pilot, chỉ bật khi có đối chứng và review; DROP được xác nhận vẫn purge raw/OCR/cache/staging theo exclusion retention. Tính năng tiếp tục PLANNED.
