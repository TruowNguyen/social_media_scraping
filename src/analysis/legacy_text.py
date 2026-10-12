"""Legacy legacy_text behavior extracted without changing data policies."""

import json
import logging
import os
import re
import threading
from src.config.env import env_float, env_int, env_str
from src.config.paths import ASSET_REGISTRY_PATH
from src.domain.sentiment_labels import _SENTIMENT_LABEL_MAP

_DEFAULT_ASSET_REGISTRY = [
    {"canonical_name": "Bitcoin", "Symbol": "BTC", "asset_class": "cryptocurrency", "asset_id": "crypto:BTC", "aliases": ["bitcoin", "btc", "xbt", "بیت کوین", "بیتکوین", "بیت‌کوین"], "topics": ["crypto", "cryptocurrency", "digital assets"], "description": "the Bitcoin cryptocurrency"},
    {"canonical_name": "Ethereum", "Symbol": "ETH", "asset_class": "cryptocurrency", "asset_id": "crypto:ETH", "aliases": ["ethereum", "ether", "eth", "اتریوم", "اتر"], "topics": ["crypto", "smart contracts", "digital assets"], "description": "the Ethereum cryptocurrency and smart-contract network"},
    {"canonical_name": "Solana", "Symbol": "SOL", "asset_class": "cryptocurrency", "asset_id": "crypto:SOL", "aliases": ["solana", "sol", "سولانا"], "topics": ["crypto", "blockchain", "digital assets"], "description": "the Solana cryptocurrency and blockchain"},
    {"canonical_name": "XRP", "Symbol": "XRP", "asset_class": "cryptocurrency", "asset_id": "crypto:XRP", "aliases": ["xrp", "ripple", "ریپل"], "topics": ["crypto", "payments", "digital assets"], "description": "the XRP cryptocurrency associated with Ripple payments"},
    {"canonical_name": "Gold", "Symbol": "XAU", "asset_class": "commodity", "asset_id": "commodity:XAU", "aliases": ["gold", "xau", "xauusd", "طلا", "انس طلا", "طلای جهانی"], "topics": ["precious metals", "safe haven", "bullion"], "description": "the gold precious-metal commodity"},
    {"canonical_name": "Silver", "Symbol": "XAG", "asset_class": "commodity", "asset_id": "commodity:XAG", "aliases": ["silver", "xag", "xagusd", "نقره"], "topics": ["precious metals", "bullion"], "description": "the silver precious-metal commodity"},
    {"canonical_name": "WTI Crude Oil", "Symbol": "WTI", "asset_class": "commodity", "asset_id": "commodity:WTI", "aliases": ["wti", "wti crude", "west texas intermediate"], "topics": ["oil", "crude", "petroleum", "energy markets", "oil prices", "OPEC"], "description": "West Texas Intermediate crude oil benchmark"},
    {"canonical_name": "Brent Crude Oil", "Symbol": "BRENT", "asset_class": "commodity", "asset_id": "commodity:BRENT", "aliases": ["brent", "brent crude", "brent oil", "برنت", "نفت برنت"], "topics": ["oil", "crude", "petroleum", "energy markets", "oil prices", "OPEC"], "description": "Brent crude oil benchmark"},
    {"canonical_name": "Crude Oil", "Symbol": "OIL", "asset_class": "commodity", "asset_id": "commodity:OIL", "aliases": ["crude oil", "oil prices", "oil price", "نفت", "نفت خام", "قیمت نفت"], "topics": ["oil", "petroleum", "energy markets", "refining", "OPEC", "oil supply", "oil demand"], "description": "global crude-oil prices and petroleum markets"},
    {"canonical_name": "Energy Select Sector SPDR Fund", "Symbol": "XLE", "asset_class": "ETF", "asset_id": "etf:XLE", "aliases": ["xle", "energy select sector spdr"], "topics": ["energy stocks", "oil stocks", "oil companies", "oil and gas companies", "energy companies", "integrated oil companies"], "description": "a US exchange-traded fund tracking large energy, oil and gas companies"},
    {"canonical_name": "Exxon Mobil", "Symbol": "XOM", "asset_class": "equity", "asset_id": "equity:XOM", "aliases": ["exxon", "exxon mobil", "xom"], "topics": ["oil company", "energy company", "integrated oil and gas"], "description": "Exxon Mobil, an integrated oil and gas company"},
    {"canonical_name": "Chevron", "Symbol": "CVX", "asset_class": "equity", "asset_id": "equity:CVX", "aliases": ["chevron", "cvx"], "topics": ["oil company", "energy company", "integrated oil and gas"], "description": "Chevron, an integrated oil and gas company"},
    {"canonical_name": "Shell", "Symbol": "SHEL", "asset_class": "equity", "asset_id": "equity:SHEL", "aliases": ["shell plc", "shell", "shel"], "topics": ["oil company", "energy company", "integrated oil and gas", "LNG"], "description": "Shell plc, an integrated oil, gas and LNG company"},
    {"canonical_name": "BP", "Symbol": "BP", "asset_class": "equity", "asset_id": "equity:BP", "aliases": ["bp plc", "bp"], "topics": ["oil company", "energy company", "integrated oil and gas"], "description": "BP plc, an integrated oil and gas company"},
    {"canonical_name": "S&P 500", "Symbol": "SPX", "asset_class": "index", "asset_id": "index:SPX", "aliases": ["s&p 500", "s&p500", "sp500", "spx", "اس اند پی"], "topics": ["US stocks", "large cap stocks", "US equity market"], "description": "the S&P 500 US large-cap equity index"},
    {"canonical_name": "Nasdaq Composite", "Symbol": "IXIC", "asset_class": "index", "asset_id": "index:IXIC", "aliases": ["nasdaq composite", "nasdaq", "ixic", "نزدک", "نزدَک"], "topics": ["technology stocks", "US stocks", "growth stocks"], "description": "the Nasdaq Composite equity index"},
    {"canonical_name": "Dow Jones Industrial Average", "Symbol": "DJI", "asset_class": "index", "asset_id": "index:DJI", "aliases": ["dow jones", "dow", "djia", "dji", "داوجونز", "داو جونز"], "topics": ["US stocks", "blue chip stocks"], "description": "the Dow Jones Industrial Average US equity index"},
    {"canonical_name": "US Dollar", "Symbol": "USD", "asset_class": "currency", "asset_id": "fx:USD", "aliases": ["us dollar", "u.s. dollar", "usd", "dollar index", "dxy", "دلار", "شاخص دلار"], "topics": ["foreign exchange", "FX", "dollar", "Federal Reserve"], "description": "the United States dollar currency"},
    {"canonical_name": "Euro", "Symbol": "EUR", "asset_class": "currency", "asset_id": "fx:EUR", "aliases": ["euro", "eur", "یورو"], "topics": ["foreign exchange", "FX", "ECB", "eurozone"], "description": "the euro currency"},
    {"canonical_name": "British Pound", "Symbol": "GBP", "asset_class": "currency", "asset_id": "fx:GBP", "aliases": ["british pound", "pound sterling", "sterling", "gbp", "پوند"], "topics": ["foreign exchange", "FX", "Bank of England", "UK currency"], "description": "the British pound sterling currency"},
    {"canonical_name": "Japanese Yen", "Symbol": "JPY", "asset_class": "currency", "asset_id": "fx:JPY", "aliases": ["japanese yen", "yen", "jpy", "ین"], "topics": ["foreign exchange", "FX", "Bank of Japan", "Japan currency"], "description": "the Japanese yen currency"},
    {"canonical_name": "Apple", "Symbol": "AAPL", "asset_class": "equity", "asset_id": "equity:AAPL", "aliases": ["apple inc", "apple", "aapl", "اپل"], "topics": ["iPhone", "consumer technology", "big tech"], "description": "Apple Inc. common stock"},
    {"canonical_name": "Microsoft", "Symbol": "MSFT", "asset_class": "equity", "asset_id": "equity:MSFT", "aliases": ["microsoft", "msft"], "topics": ["software", "cloud computing", "Azure", "big tech"], "description": "Microsoft Corporation common stock"},
    {"canonical_name": "NVIDIA", "Symbol": "NVDA", "asset_class": "equity", "asset_id": "equity:NVDA", "aliases": ["nvidia", "nvda", "انویدیا"], "topics": ["AI chips", "GPUs", "semiconductors", "artificial intelligence"], "description": "NVIDIA Corporation common stock"},
    {"canonical_name": "Tesla", "Symbol": "TSLA", "asset_class": "equity", "asset_id": "equity:TSLA", "aliases": ["tesla", "tsla", "تسلا"], "topics": ["electric vehicles", "EVs", "automotive"], "description": "Tesla Inc. common stock"},
    {"canonical_name": "Amazon", "Symbol": "AMZN", "asset_class": "equity", "asset_id": "equity:AMZN", "aliases": ["amazon", "amzn"], "topics": ["ecommerce", "AWS", "cloud computing", "big tech"], "description": "Amazon.com Inc. common stock"},
    {"canonical_name": "Meta Platforms", "Symbol": "META", "asset_class": "equity", "asset_id": "equity:META", "aliases": ["meta platforms", "meta", "facebook", "meta stock"], "topics": ["social media", "digital advertising", "big tech"], "description": "Meta Platforms Inc. common stock"},
    {"canonical_name": "Tether", "Symbol": "USDT", "asset_class": "cryptocurrency", "asset_id": "crypto:USDT", "aliases": ["tether", "usdt", "تتر"], "topics": ["crypto", "stablecoin", "digital assets", "dollar peg"], "description": "the Tether (USDT) dollar-pegged stablecoin"},
    {"canonical_name": "USD Coin", "Symbol": "USDC", "asset_class": "cryptocurrency", "asset_id": "crypto:USDC", "aliases": ["usd coin", "usdc"], "topics": ["crypto", "stablecoin", "digital assets", "dollar peg"], "description": "the USD Coin (USDC) dollar-pegged stablecoin"},
    {"canonical_name": "BNB", "Symbol": "BNB", "asset_class": "cryptocurrency", "asset_id": "crypto:BNB", "aliases": ["bnb", "binance coin", "بی ان بی"], "topics": ["crypto", "exchange token", "digital assets"], "description": "the BNB cryptocurrency of the BNB Chain"},
    {"canonical_name": "Cardano", "Symbol": "ADA", "asset_class": "cryptocurrency", "asset_id": "crypto:ADA", "aliases": ["cardano", "ada", "کاردانو"], "topics": ["crypto", "blockchain", "digital assets"], "description": "the Cardano cryptocurrency"},
    {"canonical_name": "Dogecoin", "Symbol": "DOGE", "asset_class": "cryptocurrency", "asset_id": "crypto:DOGE", "aliases": ["dogecoin", "doge", "دوج کوین", "دوج"], "topics": ["crypto", "meme coin", "digital assets"], "description": "the Dogecoin cryptocurrency"},
    {"canonical_name": "Toncoin", "Symbol": "TON", "asset_class": "cryptocurrency", "asset_id": "crypto:TON", "aliases": ["toncoin", "ton coin", "تون کوین"], "topics": ["crypto", "Telegram", "digital assets"], "description": "the Toncoin cryptocurrency of The Open Network"},
    {"canonical_name": "Natural Gas", "Symbol": "NG", "asset_class": "commodity", "asset_id": "commodity:NG", "aliases": ["natural gas", "henry hub", "lng", "گاز طبیعی", "گاز"], "topics": ["gas", "energy markets", "LNG", "energy prices"], "description": "natural gas and LNG markets"},
    {"canonical_name": "Iranian Rial", "Symbol": "IRR", "asset_class": "currency", "asset_id": "fx:IRR", "aliases": ["iranian rial", "irr", "toman", "ریال", "تومان"], "topics": ["foreign exchange", "FX", "Iran currency", "Iran economy"], "description": "the Iranian rial/toman currency"},
]

_CASHTAG_RE = re.compile(r"(?<!\w)\$([A-Za-z][A-Za-z0-9._-]{0,14})\b")

_ASSET_REGISTRY_CACHE = {}

_ASSET_REGISTRY_LOCK = threading.Lock()

_ASSET_NLI_MODEL_NAME = env_str("ASSET_NLI_MODEL", "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli")

_ASSET_NLI_DEVICE = env_str("ASSET_NLI_DEVICE", "auto").strip().lower()

_ASSET_CONTEXT_MAX_RESULTS = env_int("ASSET_CONTEXT_MAX_RESULTS", 0)  # 0 = keep all NLI-entailing context candidates

_ASSET_NLI_BATCH_SIZE = max(1, env_int("ASSET_NLI_BATCH_SIZE", 16))

_ASSET_DIRECT_MIN_CONFIDENCE = env_float("ASSET_DIRECT_MIN_CONFIDENCE", 0.10)

_ASSET_NLI_BUNDLE = None

_ASSET_NLI_LOCK = threading.Lock()

_ASSET_CONTEXT_CACHE = {}

_ASSET_CONTEXT_CACHE_LOCK = threading.Lock()

_ASSET_MODEL_WARNING_EMITTED = False

_SENTIMENT_MODEL_NAME = env_str("SENTIMENT_MODEL", "ProsusAI/finbert")

_MULTILINGUAL_SENTIMENT_MODEL_NAME = env_str(
    "MULTILINGUAL_SENTIMENT_MODEL", "cardiffnlp/twitter-xlm-roberta-base-sentiment")

_SENTIMENT_BUNDLES = {}

_SENTIMENT_LOCK = threading.Lock()

_SENTIMENT_WARNED = set()

def _is_oom_error(exc) -> bool:
    """Whether an exception is a GPU out-of-memory condition."""
    text = f"{type(exc).__name__}: {exc}".lower()
    return "outofmemory" in text or "out of memory" in text or "cuda error" in text

def _load_sentiment_model(model_name: str):
    """Lazy-loads one sentiment pipeline by model name, cached per name.

    Returns None if unavailable (missing transformers/torch, a download
    failure, or the model explicitly disabled with "none") -- callers then
    store a null sentiment rather than fabricating one.
    """
    if not model_name or model_name.strip().lower() in {"", "none", "off", "disabled"}:
        return None
    cached = _SENTIMENT_BUNDLES.get(model_name)
    if cached is not None:
        return None if cached is False else cached
    with _SENTIMENT_LOCK:
        cached = _SENTIMENT_BUNDLES.get(model_name)
        if cached is not None:
            return None if cached is False else cached
        try:
            from transformers import pipeline
            try:
                _SENTIMENT_BUNDLES[model_name] = pipeline("sentiment-analysis", model=model_name)
            except Exception as e:
                # A GPU that is full (another scraper, another process, a
                # smaller card) is a resource condition, not a missing model:
                # retry pinned to CPU rather than nulling sentiment for the
                # whole run. This mirrors _demote_nli_to_cpu on the NLI path,
                # which already degrades this way instead of giving up.
                if not _is_oom_error(e):
                    raise
                logging.getLogger(__name__).warning(
                    "Sentiment model '%s' did not fit on the GPU (%s). Falling back to CPU.",
                    model_name, str(e).splitlines()[0] if str(e) else type(e).__name__,
                )
                _SENTIMENT_BUNDLES[model_name] = pipeline(
                    "sentiment-analysis", model=model_name, device=-1)
        except Exception as e:
            _SENTIMENT_BUNDLES[model_name] = False
            if model_name not in _SENTIMENT_WARNED:
                logging.getLogger(__name__).warning(
                    "Sentiment model '%s' unavailable (%s). sentiment.label/confidence will be null.",
                    model_name, str(e).splitlines()[0] if str(e) else type(e).__name__,
                )
                _SENTIMENT_WARNED.add(model_name)
            return None
    return _SENTIMENT_BUNDLES[model_name]

def _sentiment_model_for(lang: str) -> str:
    """FinBERT for English, the multilingual model for anything else.

    Nothing is translated any more, so a Persian record is scored as Persian.
    FinBERT would tokenize it to mostly [UNK] and return a label built out of
    noise, which is worse than a null.
    """
    return _SENTIMENT_MODEL_NAME if (lang or "en") == "en" else _MULTILINGUAL_SENTIMENT_MODEL_NAME

def analyze_sentiment(text: str, lang: str = "en") -> dict:
    """Scores ``text`` in its own language -- English through FinBERT, any
    other language through the multilingual model.

    Returns {"label": "positive"|"neutral"|"negative", "confidence": 0-1} or
    {"label": None, "confidence": None} for empty input or when the model for
    that language is unavailable.
    """
    text = (text or "").strip()
    if not text:
        return {"label": None, "confidence": None}
    model = _load_sentiment_model(_sentiment_model_for(lang))
    if not model:
        return {"label": None, "confidence": None}
    # These models have a 512-token input window, so scoring a long transcript
    # in one call silently judges the whole video by its opening ~380 words.
    # Chunking and averaging the per-label probabilities keeps every part of
    # the text in the verdict; a short post is a single chunk.
    chunks = _split_nli_premise(text, max_chars=1200, max_chunks=12)
    if not chunks:
        return {"label": None, "confidence": None}
    try:
        outputs = model(chunks, truncation=True, max_length=512, top_k=None)
        totals = {}
        for scores in outputs:
            for entry in scores:
                # cardiffnlp emits LABEL_0/1/2, FinBERT emits words; both are
                # mapped onto the schema's three labels.
                label = _SENTIMENT_LABEL_MAP.get(str(entry["label"]).lower())
                if label is None:
                    continue
                totals[label] = totals.get(label, 0.0) + float(entry["score"])
        if not totals:
            return {"label": None, "confidence": None}
        label, total = max(totals.items(), key=lambda kv: kv[1])
        return {"label": label, "confidence": round(total / len(outputs), 4)}
    except Exception as e:
        logging.getLogger(__name__).warning(
            "Sentiment analysis failed: %s", str(e).splitlines()[0] if str(e) else type(e).__name__
        )
        return {"label": None, "confidence": None}

def analyze_text(text: str, lang: str, asset_text: str = None, context_terms=None) -> tuple:
    """Returns (sentiment_dict, asset_mention_list) for one record.

    The single entry point every scraper uses for text analysis, so the
    per-language handling is identical everywhere. Nothing is translated: the
    record's own text is scored in its own language (FinBERT for English, the
    multilingual model otherwise) and asset extraction reads the same original
    text, matching both Latin aliases/cashtags and the registry's non-Latin
    aliases against it.

    ``asset_text`` lets a scraper widen the asset input beyond the record's
    raw_text (Reddit adds the title, TikTok the video description); it defaults
    to ``text``.
    """
    asset_text = text if asset_text is None else asset_text
    return (
        analyze_sentiment(text, lang),
        extract_asset_mentions(asset_text, context_terms=context_terms, lang=lang),
    )

def _normalized_asset_entry(entry: dict) -> dict:
    symbol = str(entry.get("Symbol") or entry.get("symbol") or "").strip().upper() or None
    canonical_name = str(entry.get("canonical_name") or "").strip() or symbol
    asset_class = str(entry.get("asset_class") or "").strip() or None
    asset_id = str(entry.get("asset_id") or "").strip() or (f"symbol:{symbol}" if symbol else None)
    aliases = entry.get("aliases") or []
    topics = entry.get("topics") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    if isinstance(topics, str):
        topics = [topics]
    aliases = [str(a).strip() for a in aliases if str(a).strip()]
    topics = [str(t).strip() for t in topics if str(t).strip()]
    if symbol:
        aliases.append(symbol)
    if canonical_name:
        aliases.append(canonical_name)
    seen = set()
    unique_aliases = []
    for alias in aliases:
        key = alias.casefold()
        if key not in seen:
            seen.add(key)
            unique_aliases.append(alias)
    return {
        "canonical_name": canonical_name,
        "Symbol": symbol,
        "asset_class": asset_class,
        "asset_id": asset_id,
        "aliases": unique_aliases,
        "topics": topics,
        "description": str(entry.get("description") or "").strip() or None,
        "context_inference": (
            entry.get("context_inference")
            if "context_inference" in entry
            else str(asset_class or "").strip().casefold() != "equity"
        ) is not False,
    }

def load_asset_registry(filepath: str = ASSET_REGISTRY_PATH) -> list:
    """Load the built-in registry plus optional project-specific definitions.

    Custom entries can add aliases, topics and a natural-language description.
    Entries with the same ``asset_id`` replace the built-in definition.
    """
    abs_path = os.path.abspath(filepath)
    try:
        mtime = os.path.getmtime(abs_path)
    except OSError:
        mtime = None
    cache_key = (abs_path, mtime)
    with _ASSET_REGISTRY_LOCK:
        cached = _ASSET_REGISTRY_CACHE.get(cache_key)
        if cached is not None:
            return cached
        combined = [_normalized_asset_entry(x) for x in _DEFAULT_ASSET_REGISTRY]
        if mtime is not None:
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                custom = payload.get("assets", []) if isinstance(payload, dict) else payload
                custom = [_normalized_asset_entry(x) for x in (custom or []) if isinstance(x, dict)]
                by_id = {x.get("asset_id"): x for x in combined if x.get("asset_id")}
                for entry in custom:
                    if entry.get("asset_id"):
                        by_id[entry["asset_id"]] = entry
                    else:
                        combined.append(entry)
                combined = list(by_id.values()) + [x for x in combined if not x.get("asset_id")]
            except Exception as e:
                logging.getLogger(__name__).warning("Could not load %s: %s", filepath, e)
        _ASSET_REGISTRY_CACHE.clear()
        _ASSET_REGISTRY_CACHE[cache_key] = combined
        return combined

def _find_alias(text: str, alias: str):
    r"""Finds ``alias`` in ``text`` on word boundaries, in any script.

    The boundary class is \w (Unicode-aware), not [A-Za-z0-9_]: with the ASCII
    class a Persian alias like "طلا" matched inside "طلایی", because the
    following Persian letter is not an ASCII word character and therefore
    counted as a boundary.
    """
    if not text or not alias:
        return None
    pattern = re.compile(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", re.IGNORECASE | re.UNICODE)
    return pattern.search(text)

_LATIN_RE = re.compile(r"[A-Za-z]")

def _is_latin_text(text: str, min_ratio: float = 0.5) -> bool:
    """Whether ``text`` is mostly Latin script.

    The NLI relevance model is English-only. Fed a Persian premise it does not
    return "unsure" -- it returns a confident verdict on tokens it never saw,
    which used to CONTRADICT perfectly real mentions and delete them. So the
    model is consulted only for text it can actually read.
    """
    letters = [c for c in (text or "") if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if _LATIN_RE.match(c)) / len(letters) >= min_ratio

def _asset_hypothesis(entry: dict) -> str:
    name = entry.get("canonical_name") or entry.get("Symbol") or "this asset"
    symbol = entry.get("Symbol")
    desc = entry.get("description") or entry.get("asset_class") or "financial asset"
    topics = ", ".join((entry.get("topics") or [])[:8])
    sym_text = f" ({symbol})" if symbol else ""
    topic_text = f" Related market topics include {topics}." if topics else ""
    return (
        f"This information is materially about, relevant to, or capable of affecting "
        f"the financial asset {name}{sym_text}, {desc}.{topic_text}"
    )

def _load_asset_nli_model():
    """Lazy-load a compact NLI model used to estimate asset relevance.

    If the model/dependencies are unavailable, the caller receives ``None``.
    In that case direct mentions are still extracted, but confidence is left
    null and semantic/context inference is disabled rather than fabricated.
    """
    global _ASSET_NLI_BUNDLE, _ASSET_MODEL_WARNING_EMITTED
    if _ASSET_NLI_MODEL_NAME.strip().lower() in {"", "none", "off", "disabled"}:
        return None
    if _ASSET_NLI_BUNDLE is False:
        return None
    if _ASSET_NLI_BUNDLE is not None:
        return _ASSET_NLI_BUNDLE
    with _ASSET_NLI_LOCK:
        if _ASSET_NLI_BUNDLE is not None:
            return None if _ASSET_NLI_BUNDLE is False else _ASSET_NLI_BUNDLE
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(_ASSET_NLI_MODEL_NAME)
            model = AutoModelForSequenceClassification.from_pretrained(_ASSET_NLI_MODEL_NAME)
            if _ASSET_NLI_DEVICE in {"auto", "cuda"} and torch.cuda.is_available():
                device = torch.device("cuda")
            else:
                device = torch.device("cpu")
            model.to(device)
            model.eval()

            id2label = {int(k): str(v).lower() for k, v in (model.config.id2label or {}).items()}
            # "not_entailment" also contains "entail", so match the prefix, not
            # the substring. A model that exposes no contradiction/neutral
            # class leaves those None rather than aliasing them onto index 0/2,
            # which would mislabel its predictions.
            entail_idx = next((i for i, label in id2label.items() if label.startswith("entail")), 1)
            contradiction_idx = next((i for i, label in id2label.items() if "contrad" in label), None)
            neutral_idx = next((i for i, label in id2label.items() if label == "neutral"), None)
            _ASSET_NLI_BUNDLE = (tokenizer, model, torch, device, entail_idx, contradiction_idx, neutral_idx)
        except Exception as e:
            _ASSET_NLI_BUNDLE = False
            if not _ASSET_MODEL_WARNING_EMITTED:
                logging.getLogger(__name__).warning(
                    "Asset NLI model unavailable (%s). Direct mentions will be kept with confidence=null; "
                    "semantic/context-only asset inference is disabled until transformers/torch and the model are available.",
                    str(e).splitlines()[0] if str(e) else type(e).__name__,
                )
                _ASSET_MODEL_WARNING_EMITTED = True
            return None
    return _ASSET_NLI_BUNDLE

def _demote_nli_to_cpu(reason: str):
    """Moves the loaded NLI model to CPU for the rest of this process.

    VRAM is shared: a second scraper started by hand (or a long batch) can
    exhaust it mid-run, and an uncaught CUDA OOM here loses every record of
    the keyword/account being processed, not just one asset score. Same
    trade-off the Whisper circuit breaker already makes -- slower, but the
    run keeps producing records.
    """
    global _ASSET_NLI_BUNDLE
    tokenizer, model, torch, device, *rest = _ASSET_NLI_BUNDLE
    if device.type == "cpu":
        return device
    cpu = torch.device("cpu")
    model.to(cpu)
    torch.cuda.empty_cache()
    _ASSET_NLI_BUNDLE = (tokenizer, model, torch, cpu, *rest)
    logging.getLogger(__name__).warning(
        "Asset NLI model moved to CPU after CUDA OOM (%s). Scoring continues on CPU.", reason
    )
    return cpu

def _split_nli_premise(text: str, max_chars: int = 1400, max_chunks: int = 12) -> list:
    """Split long content into bounded semantic chunks for NLI scoring.

    X posts normally remain one chunk. Long YouTube transcripts are evaluated
    across several chunks so an asset discussed later in the video is not lost
    merely because a transformer input has a finite token window.
    """
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks, current = [], []
    current_len = 0
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if current and current_len + len(sentence) + 1 > max_chars:
            chunks.append(" ".join(current))
            current, current_len = [], 0
            if len(chunks) >= max_chunks:
                break
        if len(sentence) > max_chars:
            # Extremely long subtitle segments are cut on character boundaries;
            # this is only an input-window safeguard, not a relevance heuristic.
            for i in range(0, len(sentence), max_chars):
                if len(chunks) >= max_chunks:
                    break
                piece = sentence[i:i + max_chars].strip()
                if piece:
                    chunks.append(piece)
            continue
        current.append(sentence)
        current_len += len(sentence) + 1
    if current and len(chunks) < max_chunks:
        chunks.append(" ".join(current))
    return chunks[:max_chunks]

def _nli_asset_scores(premise: str, entries: list) -> dict:
    """Return model-derived entailment probabilities and predicted NLI labels.

    For long content, each asset keeps the strongest entailment evidence found
    in any semantic chunk. This avoids the first-512-token bias that would
    otherwise make YouTube asset extraction much less reliable than X.
    """
    chunks = _split_nli_premise(premise)
    if not chunks or not entries:
        return {}
    bundle = _load_asset_nli_model()
    if not bundle:
        return {}
    tokenizer, model, torch, device, entail_idx, contradiction_idx, neutral_idx = bundle
    hypotheses = [_asset_hypothesis(e) for e in entries]
    out = {}

    pairs = []
    pair_meta = []
    for chunk in chunks:
        for entry, hypothesis in zip(entries, hypotheses):
            pairs.append((chunk, hypothesis))
            pair_meta.append(entry)

    with torch.no_grad():
        for start in range(0, len(pairs), _ASSET_NLI_BATCH_SIZE):
            batch_pairs = pairs[start:start + _ASSET_NLI_BATCH_SIZE]
            batch_entries = pair_meta[start:start + _ASSET_NLI_BATCH_SIZE]
            encoded = tokenizer(
                [p[0] for p in batch_pairs],
                [p[1] for p in batch_pairs],
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            try:
                logits = model(**{k: v.to(device) for k, v in encoded.items()}).logits
            except torch.cuda.OutOfMemoryError as e:
                device = _demote_nli_to_cpu(str(e).splitlines()[0])
                logits = model(**{k: v.to(device) for k, v in encoded.items()}).logits
            probs = torch.softmax(logits, dim=-1).detach().cpu()
            pred = probs.argmax(dim=-1).tolist()
            for entry, row, pred_idx in zip(batch_entries, probs, pred):
                if pred_idx == entail_idx:
                    label = "entailment"
                elif contradiction_idx is not None and pred_idx == contradiction_idx:
                    label = "contradiction"
                elif neutral_idx is not None and pred_idx == neutral_idx:
                    label = "neutral"
                else:
                    label = "not_entailment"
                key = entry.get("asset_id") or entry.get("Symbol") or entry.get("canonical_name")
                candidate = {"entailment": float(row[entail_idx].item()), "label": label}
                current = out.get(key)
                if current is None or candidate["entailment"] > current["entailment"]:
                    out[key] = candidate
    return out

def _context_candidates(context_terms, registry: list) -> list:
    context_text = " ; ".join(str(t).strip() for t in context_terms if str(t).strip())
    if not context_text:
        return []
    registry_sig = tuple((e.get("asset_id"), e.get("canonical_name"), tuple(e.get("topics") or [])) for e in registry)
    cache_key = (context_text.casefold(), registry_sig)
    with _ASSET_CONTEXT_CACHE_LOCK:
        cached = _ASSET_CONTEXT_CACHE.get(cache_key)
        if cached is not None:
            return cached

    eligible = [e for e in registry if e.get("context_inference", True)]
    scores = _nli_asset_scores(f"Search topic: {context_text}", eligible)
    ranked = []
    for entry in eligible:
        key = entry.get("asset_id") or entry.get("Symbol") or entry.get("canonical_name")
        score = scores.get(key)
        # NLI itself decides whether the topic entails relevance; there is no
        # hand-written confidence percentage or numeric relevance threshold.
        if score and score["label"] == "entailment":
            ranked.append((score["entailment"], entry, score))
    ranked.sort(key=lambda x: x[0], reverse=True)
    selected = ranked if _ASSET_CONTEXT_MAX_RESULTS <= 0 else ranked[:_ASSET_CONTEXT_MAX_RESULTS]
    result = [(entry, score_info) for _, entry, score_info in selected]
    with _ASSET_CONTEXT_CACHE_LOCK:
        _ASSET_CONTEXT_CACHE[cache_key] = result
    return result

def extract_asset_mentions(text: str, context_terms=None, lang: str = "en",
                           registry_path: str = ASSET_REGISTRY_PATH) -> list:
    """Extract direct and contextual financial-asset relevance.

    Confidence is produced by a Natural Language Inference model, not by
    hard-coded per-rule percentages. Direct literal/cashtag mentions are always
    preserved; the model then judges whether the content is materially about or
    could affect that asset. Context-only assets are considered when the search
    topic itself entails an asset relationship and the actual record text also
    entails that relationship. Their confidence is the geometric mean of the
    two independent entailment probabilities, so a strong keyword alone cannot
    manufacture a high-confidence asset association.
    """
    text = text or ""
    if context_terms is None:
        context_terms = []
    elif isinstance(context_terms, str):
        context_terms = [context_terms]

    registry = load_asset_registry(registry_path)
    # The NLI relevance model reads English only. For a non-Latin record it is
    # skipped entirely: direct alias/cashtag matches are facts that stand on
    # their own and are emitted with a null confidence, rather than being
    # filtered by a model that cannot read the premise. This is what made a
    # Persian post saying "USDT" come back with no asset_mention at all.
    model_readable = _is_latin_text(text) and (lang or "en") not in {"fa", "ar", "ru", "zh", "ja", "ko", "he"}
    symbol_map = {e.get("Symbol", "").upper(): e for e in registry if e.get("Symbol")}
    direct = {}
    unknown = {}

    for match in _CASHTAG_RE.finditer(text):
        symbol = match.group(1).upper()
        entry = symbol_map.get(symbol)
        if entry:
            direct[entry.get("asset_id") or symbol] = (entry, match.group(0))
        else:
            unknown[symbol] = {
                "mentioned_text": match.group(0),
                "canonical_name": None,
                "Symbol": symbol,
                "asset_class": None,
                "asset_id": None,
                "confidence": None,
            }

    for entry in registry:
        best = None
        for alias in sorted(entry.get("aliases", []), key=len, reverse=True):
            m = _find_alias(text, alias)
            if m:
                best = m.group(0)
                break
        if best:
            direct[entry.get("asset_id") or entry.get("Symbol") or entry.get("canonical_name")] = (entry, best)

    context = _context_candidates(context_terms, registry) if model_readable else []
    candidate_map = {key: pair for key, pair in direct.items()}
    for entry, query_score in context:
        key = entry.get("asset_id") or entry.get("Symbol") or entry.get("canonical_name")
        candidate_map.setdefault(key, (entry, None))

    entries = [pair[0] for pair in candidate_map.values()]
    text_scores = _nli_asset_scores(text, entries) if model_readable else {}
    query_score_by_key = {
        entry.get("asset_id") or entry.get("Symbol") or entry.get("canonical_name"): score
        for entry, score in context
    }

    results = []
    for key, (entry, surface) in candidate_map.items():
        text_score = text_scores.get(key)
        confidence = None
        if surface is not None:
            # A literal mention is a fact; relevance confidence comes only from
            # the model's entailment probability for the actual record text.
            confidence = text_score["entailment"] if text_score else None
            # A word can match an alias without the content being about the
            # asset ("Shell" the noun, "gold" the colour). When the model
            # actively contradicts the relevance claim and its entailment
            # probability is negligible, that is a false positive, not a
            # low-confidence hit -- emitting it would pollute downstream
            # asset joins with mentions the model already rejected.
            # Deliberately requires an explicit "contradiction": a merely
            # neutral verdict means the model is unsure, and dropping those
            # would discard real mentions the model simply could not confirm.
            if (
                text_score
                and text_score["label"] == "contradiction"
                and confidence < _ASSET_DIRECT_MIN_CONFIDENCE
            ):
                continue
        else:
            # Context-only inference is emitted only if BOTH the search topic
            # and the record text are independently classified as entailment.
            query_score = query_score_by_key.get(key)
            if not text_score or not query_score:
                continue
            if text_score["label"] != "entailment" or query_score["label"] != "entailment":
                continue
            confidence = (text_score["entailment"] * query_score["entailment"]) ** 0.5

        results.append({
            "mentioned_text": surface,
            "canonical_name": entry.get("canonical_name"),
            "Symbol": entry.get("Symbol"),
            "asset_class": entry.get("asset_class"),
            "asset_id": entry.get("asset_id"),
            "confidence": round(float(confidence), 4) if confidence is not None else None,
        })

    results.extend(unknown.values())
    if results:
        return sorted(results, key=lambda x: (x["confidence"] is None, -(x["confidence"] or 0.0), str(x.get("Symbol") or "")))

    return [{
        "mentioned_text": None,
        "canonical_name": None,
        "Symbol": None,
        "asset_class": None,
        "asset_id": None,
        "confidence": None,
    }]
