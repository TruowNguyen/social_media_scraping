"""Conservative intent rules. Ambiguous/mixed text stays available for review."""
import re
import unicodedata
from types import SimpleNamespace

RULE_ID = "NO_SALES_RECRUITMENT_BUY_SELL_EXCHANGE"


def normalize(text):
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", text).casefold().replace("đ", "d") if unicodedata.category(c) != "Mn").split())


PATTERNS = {
    "REAL_ESTATE_LISTING": r"\b(?:ban (?:can ho|nha|dat)|cho thue (?:nha|phong|can ho)|nhuong phong)\b",
    "RECRUITMENT": r"\b(?:can tuyen|tuyen (?:cong nhan|ky su|tho|nhan vien)|tuyen dung|tim nhan su)\b",
    "BUY_SELL": r"\b(?:can mua|can ban|rao ban|thanh ly|ban xe|sang nhuong)\b",
    "GOODS_EXCHANGE": r"\b(?:doi (?:xe|do|hang)|trao doi hang hoa|giao luu doi do)\b",
    "SALES_MARKETING": r"\b(?:mua ngay|chot don|dat hang|ban hang|khuyen mai|uu dai)\b",
    "RENTAL": r"\b(?:cho thue|can thue|tim phong tro|tim (?:nha|phong|xe|mat bang) (?:de )?thue)\b",
    "LOAN_DEBT": r"\b(?:cho vay|can vay|vay tien|vay von|vay no|vay tra gop|ho tro vay|giai ngan|dao han|mua ban no|mua no|ban no)\b",
}
TRANSACTION = r"\b(?:lien he|inbox|gia|bang gia|nhan ho so|ung tuyen|luong|thu nhap|can tuyen|tuyen cong nhan|can mua|can ban|thanh ly|lay|bu tien|chot don|dat hang|mua ngay|lai suat|giai ngan)\b"
OPERATIONAL = r"\b(?:phan anh|khieu nai|buc xuc|khong phan hoi|khong ho tro|khong tra loi|khong hoan tien|chua hoan tien|khong nhan duoc ve|chua xu ly|xu ly cham|un tac|un|ket xe|xep hang|cho vao|cho lau|khong vao duoc|trao doi ca lam|trao doi voi quan ly|no luong|cham luong|no tien cong|cham tra luong)\b"
AMBIGUOUS = r"\b(?:khong tuyen|khong ban|khong mua|canh bao|lua dao|gia mao|co phai|tai sao)\b"


def protected_content(text):
    """Protect concrete problems/questions, not disclaimers in a commercial offer."""
    text = normalize(text)
    text = re.sub(r"\b(?:cam ket|dam bao) khong (?:cham luong|no luong|cham tra luong)\b", "", text)
    text = re.sub(r"\bkhong phai (?:qua )?(?:trung gian|moi gioi)\b", "", text)
    text = re.sub(r"\b(?:khong (?:phai |can |bi )?|chong |tranh )(?:xep hang|cho lau|ket xe|ket cong|un tac)\b", "", text)
    return bool(re.search(OPERATIONAL, text) or re.search(AMBIGUOUS, text)
                or re.search(r"\b(?:ket cong|nghen cong|bi chan cong)\b", text)
                or re.search(r"\bkhong phai\b.{0,45}\b(?:vao duoc|tra tien|tra luong)\b", text))

# Explicit offers are sufficient evidence; contact details are not mandatory.
# Evaluate a result title separately so group names in Google snippets cannot
# alone exclude an unrelated post. Generic mentions still require review.
RECRUITMENT_ROLE = r"(?:cong nhan|ky su|tho|nhan vien|nhan cong|nhan su|lao dong(?: pho thong)?|doi(?: tho| thi cong)|to(?: doi)? thi cong)"
RECRUITMENT_MODIFIERS = r"(?:(?:gap|them|so luong(?: lon)?|hang chuc nghin|hang nghin|[\d.,]+(?:-[\d.,]+)?|nam(?:\s*/\s*nu)?|nu(?:\s*/\s*nam)?)\s+){0,5}"
STAFFING_OFFER = rf"\b(?:bo sung|tiep nhan|chieu mo|can them)\s+(?:thong tin\s+)?{RECRUITMENT_MODIFIERS}{RECRUITMENT_ROLE}\b"
APPLICANT_OFFER = r"\b(?:tim kiem (?:nhung )?ung vien|tim (?:kiem )?dong doi|viec lam hap dan|vi tri tuyen dung|tuyen dung (?:khoi|bo phan)|tuyen dung [\"']?khung)\b"
JOB_BENEFITS = r"\b(?:bao an o|phu cap|thu nhap|nhan ho so|ung tuyen|luong (?:hap dan|[\d.,]+)|di lam ngay)\b"
JOB_SEEKING = r"\b(?:xin viec|tim viec lam|can viec lam|dang tim viec|can tim viec|xin vao lam|muon (?:xin )?vao lam|muon ung tuyen)\b"
DIRECT_INTENT = {
    "SALES_MARKETING": r"\b(?:ban (?:ve|dien thoai|iphone|samsung|do an)|nhan (?:dat|book) ve|dai ly ve)\b|\b(?:inbox|ib)\b.{0,20}\b(?:mua|dat|book) ve\b|\bve\b.{0,45}\b(?:gia re|gia si)\b.{0,60}\b(?:inbox|lien he|zalo|chot don)\b",
    "RECRUITMENT": rf"\b(?:(?:can )?(?:tuyen(?: dung)?|tim)\s+{RECRUITMENT_MODIFIERS}{RECRUITMENT_ROLE}|co hoi viec lam|tin tuyen dung)\b|^(?:#?\w+\s+){{0,3}}tuyen dung\b",
    "RENTAL": PATTERNS["RENTAL"],
    "LOAN_DEBT": PATTERNS["LOAN_DEBT"],
    "BUY_SELL": PATTERNS["BUY_SELL"],
    "REAL_ESTATE_LISTING": PATTERNS["REAL_ESTATE_LISTING"],
    "GOODS_EXCHANGE": PATTERNS["GOODS_EXCHANGE"],
}


def apply_prefilter(candidate, enabled=True):
    candidate.rule_id = candidate.drop_reason = None
    if candidate.candidate_kind == "SOURCE_CONTAINER":
        candidate.prefilter_decision = "REVIEW"
        return "REVIEW"
    text = normalize(" ".join(filter(None, (candidate.caption, candidate.raw_text, candidate.search_snippet, candidate.title))))
    own_text = normalize(" ".join(filter(None, (candidate.title, candidate.caption, candidate.raw_text))))
    # An employer's promise is not a complaint about unpaid wages. Preserve
    # any actual complaint elsewhere in the post, including broken promises.
    # Search snippets can carry the only offer evidence, but neighboring posts
    # and the recruitment group's name must not classify the target post.
    snippet = re.split(r"\b(?:other posts|bai viet khac)\b", normalize(candidate.search_snippet or ""), maxsplit=1)[0]
    if not text:
        decision = "REVIEW"
    elif protected_content(own_text or text):
        decision = "REVIEW"
    elif enabled:
        matches = [intent for intent, pattern in PATTERNS.items() if re.search(pattern, text)]
        direct = [intent for intent, pattern in DIRECT_INTENT.items() if re.search(pattern, own_text)]
        if re.search(STAFFING_OFFER, own_text) or re.search(JOB_SEEKING, own_text) or re.search(APPLICANT_OFFER, own_text):
            direct.insert(0, "RECRUITMENT")
        # Recruitment announcements are excluded even if the title does not
        # start with "tuyển dụng" or include a contact number.
        if re.search(r"\btuyen dung\b", own_text) and re.search(rf"\b{RECRUITMENT_ROLE}\b|\bvincons\b", own_text):
            direct.insert(0, "RECRUITMENT")
        snippet_protected = protected_content(snippet)
        snippet_offer = re.search(STAFFING_OFFER, snippet) or re.search(APPLICANT_OFFER, snippet)
        snippet_offer = snippet_offer or (re.search(DIRECT_INTENT["RECRUITMENT"], snippet) and re.search(JOB_BENEFITS, snippet))
        if snippet_offer and not snippet_protected:
            direct.insert(0, "RECRUITMENT")
        if re.search(r"#(?:tuyendung|vieclam\w*)\b", own_text) and re.search(RECRUITMENT_ROLE, own_text) and re.search(TRANSACTION, own_text):
            direct.insert(0, "RECRUITMENT")
        # A clear numeric urgent recruitment offer in a snippet is not merely
        # the name of a recruitment group.
        if re.search(r"\btuyen gap\s+(?:[\d.,]+\s+)?cong nhan\b", text):
            direct.append("RECRUITMENT")
        if direct or (matches and re.search(TRANSACTION, text)):
            candidate.prefilter_decision = "DROP"
            candidate.rule_id, candidate.drop_reason = RULE_ID, (direct or matches)[0]
            return "DROP"
        decision = "REVIEW" if matches or "CAPTION_TRUNCATED" in candidate.missing_data_reasons else "PASS"
    else:
        decision = "PASS"
    candidate.prefilter_decision = decision
    return decision


def classify_payload(payload):
    """Re-evaluate a stored/output payload without mutating it or its lineage."""
    candidate = SimpleNamespace(
        candidate_kind=payload.get("candidate_kind") or payload.get("entry_kind") or "CONTENT_ITEM",
        caption=payload.get("caption"), raw_text=payload.get("raw_text"),
        search_snippet=payload.get("search_snippet"), title=payload.get("title"),
        missing_data_reasons=payload.get("missing_data_reasons") or [],
    )
    apply_prefilter(candidate)
    return candidate
