"""Legacy keyword_matching behavior extracted without changing data policies."""



def keyword_matches(text: str, keyword: str) -> bool:
    """True when every whitespace-separated token of ``keyword`` occurs in ``text``.

    Used by the keyword mode of the account-driven platforms, which have no
    free search API and so filter the trusted accounts' own posts instead of
    querying a search endpoint. Token-wise rather than whole-phrase matching so
    "oil prices" still matches "prices of oil"; case-insensitive and script
    agnostic, so it works the same on Persian text as on English.
    """
    haystack = (text or "").casefold()
    tokens = (keyword or "").casefold().split()
    return bool(tokens) and all(token in haystack for token in tokens)
