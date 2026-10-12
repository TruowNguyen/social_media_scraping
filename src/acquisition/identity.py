"""Allowlisted, identity-preserving URL normalization. No network resolution."""
from dataclasses import dataclass
import hashlib
import re
from urllib.parse import parse_qs, urlencode, urlsplit


@dataclass(frozen=True)
class Target:
    platform: str
    url: str
    kind: str
    item_id: str | None = None
    origin: str | None = None
    source_type: str | None = None


def identify(url):
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or parts.username or parts.password or parts.port not in {None, 80, 443}:
        raise ValueError("Unsupported URL")
    host, path = (parts.hostname or "").lower(), re.sub(r"/+", "/", parts.path).rstrip("/")
    query = parse_qs(parts.query)
    if host in {"threads.com", "www.threads.com", "threads.net", "www.threads.net"}:
        # Keep the observed host: migration between .net/.com needs object evidence.
        host = host.removeprefix("www.")
        post = re.fullmatch(r"/@([A-Za-z0-9_.]+)/post/([A-Za-z0-9_-]+)", path)
        profile = re.fullmatch(r"/@([A-Za-z0-9_.]+)", path)
        if post:
            return Target("threads", f"https://{host}{path}", "CONTENT_ITEM", origin=post[1])
        if profile:
            return Target("threads", f"https://{host}{path}", "SOURCE_CONTAINER", origin=profile[1], source_type="THREADS_PROFILE")
        if path == "/search" and query.get("q"):
            return Target("threads", f"https://{host}/search?" + urlencode({"q":query['q'][0]}), "SOURCE_CONTAINER", origin=query['q'][0], source_type="THREADS_SEARCH")
        raise ValueError("Unsupported Threads reference")
    if host in {"vm.tiktok.com", "vt.tiktok.com", "fb.watch"}:
        return Target("facebook" if host == "fb.watch" else "tiktok", "https://" + host + path, "CONTENT_ITEM")
    if host in {"facebook.com", "www.facebook.com", "web.facebook.com", "m.facebook.com", "mbasic.facebook.com"}:
        host = "www.facebook.com"
        group = re.fullmatch(r"/groups/([^/]+)(?:/(posts|permalink)/([^/]+))?", path)
        if group:
            origin, _, item = group.groups()
            return Target("facebook", f"https://{host}/groups/{origin}" + (f"/posts/{item}" if item else ""), "CONTENT_ITEM" if item else "SOURCE_CONTAINER", item, origin, "FACEBOOK_GROUP")
        identity_query = {key: query[key][0] for key in ("story_fbid", "id") if query.get(key)}
        canonical = f"https://{host}{path}" + ("?" + urlencode(identity_query) if identity_query else "")
        item = identity_query.get("story_fbid")
        return Target("facebook", canonical, "CONTENT_ITEM" if item or re.search(r"/(posts|reel|videos)/", path) else "SOURCE_CONTAINER", item)
    if host in {"tiktok.com", "www.tiktok.com", "m.tiktok.com"}:
        video = re.fullmatch(r"/@([^/]+)/video/(\d+)", path)
        if video:
            creator, item = video.groups()
            return Target("tiktok", f"https://www.tiktok.com/@{creator}/video/{item}", "CONTENT_ITEM", item, creator, "TIKTOK_ACCOUNT")
        account = re.fullmatch(r"/@([^/]+)", path)
        tag = re.fullmatch(r"/tag/([^/]+)", path)
        return Target("tiktok", "https://www.tiktok.com" + path, "SOURCE_CONTAINER", origin=account[1] if account else tag[1] if tag else None, source_type="TIKTOK_ACCOUNT" if account else "TIKTOK_SEARCH" if tag else None)
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        item = path.strip("/") if host == "youtu.be" else (query.get("v", [None])[0] if path == "/watch" else None)
        short = re.fullmatch(r"/(shorts|live|embed)/([A-Za-z0-9_-]{11})", path)
        item = short[2] if short else item
        if item and re.fullmatch(r"[A-Za-z0-9_-]{11}", item):
            return Target("youtube", "https://www.youtube.com/watch?" + urlencode({"v": item}), "CONTENT_ITEM", item)
        channel = re.fullmatch(r"/(?:channel/([^/]+)|(@[^/]+))", path)
        return Target("youtube", "https://www.youtube.com" + path, "SOURCE_CONTAINER", origin=(channel[1] or channel[2]) if channel else None, source_type="YOUTUBE_CHANNEL" if channel else None)
    raise ValueError("URL outside platform allowlist")


def identity(candidate):
    return f"{candidate.platform}:{candidate.candidate_kind}:" + (candidate.platform_item_id or candidate.canonical_url)


def source_references(source):
    refs = {source.get("platform_group_ref"), source.get("platform_source_ref"), *source.get("verified_source_refs", [])}
    for url in source.get("verified_url_aliases", []):
        target = identify(url)
        if target.platform == source["platform"] and target.kind == "SOURCE_CONTAINER":
            refs.add(target.origin)
    return refs - {None}


def resolve_redirects(url, deadline, http=None):
    """Bounded short-link resolution inside the platform allowlist only."""
    import requests
    from urllib.parse import urljoin
    http = http or requests
    current = identify(url).url
    for _ in range(3):
        deadline.check()
        response = http.head(current, allow_redirects=False, timeout=min(10, deadline.remaining()))
        if response.status_code not in {301, 302, 303, 307, 308}:
            return identify(current)
        location = response.headers.get("Location")
        if not location:
            raise ValueError("Redirect without location")
        current = identify(urljoin(current, location)).url
    raise ValueError("Redirect limit exceeded")


def text_hash(text):
    normalized = " ".join((text or "").casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if any(c.isalnum() for c in normalized) else None


def hashtag_query(value):
    tag = value.lstrip("#")
    if not tag or re.search(r"[\s#/?]", tag):
        raise ValueError("Hashtag must be nonempty and have no spaces")
    return tag
