# Legacy JSON record — contract hiện có

Trạng thái: **OFFLINE_VERIFIED** cho baseline/refactor, không có chứng cứ live. Contract này mô tả hiện trạng và cố định compatibility của BASE-03. Không thêm schema_version vào output cũ. [Fixture](../../docs/baseline/demo.json), [selfcheck](../../tests/contract/legacy_schema.py), [characterization](../../tests/characterization/test_collectors.py).

Output là JSON array trong file keyword/account, UTF-8, giữ capitalization chính xác:

| Trường | Kiểu / hiện trạng |
| --- | --- |
| record_id | string `{platform}_{author_id}_{native_item_id}` |
| Source | object: platform, Source_type=`Social_media`, Source_name, Source_id, url, author_name, author_id |
| Content | object: Content_type, title, raw_text, Clean_text, language; Clean_text hiện `""` |
| time_stamps | object: published_at, collected_at, updated_at |
| asset_mention | array: mentioned_text, canonical_name, Symbol, asset_class, asset_id, confidence |
| sentiment | object: label=`positive|neutral|negative|null`, confidence number [0,1] hoặc null |
| Engagement | object: Views, likes, Comments, shares; legacy thường dùng 0 khi API thiếu metric |
| media | object: has_media boolean, media_type string/null, media_url string/null |
| deduplication | object: content_hash, is_duplicate, duplicate_group_id, original_record_id |
| quality | object: is_complete, missing_fields array, extraction_errors array, quality_score 0–100 |

Source.Source_id là **item ID**, không phải registry ID. Các native IDs được lưu dạng string; YouTube 11 ký tự, X/Telegram/TikTok/TruthSocial numeric, Reddit base36. Nền tảng/content type: X/tweet, YouTube/video, Telegram/message, Reddit/post, TikTok/video, TruthSocial/post. Facebook chưa thuộc validator legacy. YouTube thiếu channel dùng sentinel hiện có `UNRESOLVED_CHANNEL_ID`; không tự tạo một channel ID hợp lệ.

Timestamp có format `%Y-%m-%d %H:%M:%S UTC`; published_at không có có thể là `N/A`, updated_at null. Không chuyển sang ISO hoặc đổi sentinel trong refactor. title `N/A` được phép với nguồn không có title. asset_mention không phát hiện asset dùng entry có sáu trường null theo helper hiện có; confidence null thể hiện không có score, không bằng 0.

Records append và sort tăng theo published_at, unknown có sort key 0. Rerun dùng record IDs có sẵn trong JSON; Telegram có thể refresh edit tại đúng vị trí. JSON và SQLite dedup chưa chung transaction; crash recovery toàn pipeline chưa được đảm bảo.

| Policy | Hiện trạng phải giữ |
| --- | --- |
| YouTube / Reddit | DROP content duplicates sau đăng ký dedup |
| X / Telegram / TikTok / TruthSocial | Giữ records và gắn is_duplicate |
| TikTok old pinned | Continue, không break listing |
| TikTok / YouTube missing text | Không tạo record |
| TruthSocial media-only | Giữ placeholder và quality incomplete nếu không có alt text |
| Language | Mặc định en/fa; low-confidence language không bị hard-drop |
| Whisper | Mặc định translate, model small; GPU → CPU fallback, tải lazy |

build_quality là structural score, không hard schema gate và không phải relevance/confidence nghiệp vụ. Near dedup legacy giữ thuật toán, cả hạn chế hash text rỗng; sửa nằm ở CORE-06. CWD paths `keywords/`, `sources/`, `dedup/`, output dirs được giữ nguyên. Model state/monkeypatch thuộc [analysis](../../src/analysis/legacy_text.py) hoặc [transcription](../../src/media/transcription.py); dedup state thuộc `src.filtering.dedup`. Theo yêu cầu cleanup tiếp theo, root scripts và facade đã bỏ. Chạy collector qua `python -m engine.runtime --platform ...`, demo qua `python -m engine.legacy.demo`, selfchecks qua `python -m tests.contract.legacy_schema` và `python -m tests.integration.legacy_x_retry`. JSON contract không đổi; lệnh/import root cũ được thay bằng module paths này.

Acceptance LEG-01: JSON demo canonical bằng baseline. LEG-02: six-platform schema assertions không nới. LEG-03: rerun/sort/dedup/missing-text fixtures pass trước/sau. LEG-04: tám X retry assertions pass. LEG-05: import không chạy main hoặc tải model. Các kết quả ở [refactor report](../../docs/refactor-summary.md).
