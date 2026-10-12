"""Legacy language behavior extracted without changing data policies."""

from py3langid.langid import LanguageIdentifier, MODEL_FILE

_identifier = LanguageIdentifier.from_model_file(MODEL_FILE, norm_probs=True)

def detect_language(text: str) -> tuple:
    """Returns (lang_code, confidence 0-1). py3langid is deterministic
    (unlike langdetect, which needs a fixed seed to be reproducible) and
    is built to handle short text reasonably well, which matters for
    tweet-length input."""
    if not text or not text.strip():
        return "unknown", 0.0
    lang, prob = _identifier.classify(text)
    return lang, prob

def is_english(text: str, min_confidence: float = 0.70) -> bool:
    lang, prob = detect_language(text)
    return lang == "en" and prob >= min_confidence

def language_allowed(lang: str, confidence: float, allowed, min_confidence: float) -> bool:
    """Whether a record's detected language clears the collection filter.

    A post is dropped only when the detector is CONFIDENT it is a language
    outside ``allowed``. A low-confidence verdict is the detector saying it
    does not know -- which is the normal outcome for a three-word post, a
    headline, or a caption full of hashtags -- and dropping those threw away
    real posts from the trusted accounts the run is supposed to collect.
    """
    if lang in allowed:
        return True
    return confidence < min_confidence
