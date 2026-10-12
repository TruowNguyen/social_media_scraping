"""Raw conversation nodes; acquisition state is independent of relevance."""
from dataclasses import asdict, dataclass, field
from datetime import date
from urllib.parse import parse_qs, urlencode, urlsplit
import uuid
from src.acquisition.identity import identify
from src.acquisition.models import parse_utc


def canonical_node_url(url, node_type, platform='FACEBOOK'):
    if not url:
        return None
    target = identify(url)
    if platform == 'THREADS':
        if target.platform != 'threads' or target.kind != 'CONTENT_ITEM':
            raise ValueError('Expected Threads content URL')
        return target.url
    if target.platform != 'facebook' or target.kind != 'CONTENT_ITEM':
        raise ValueError('Expected Facebook content URL')
    query = parse_qs(urlsplit(url).query)
    comments = {key: query[key][0] for key in ('comment_id', 'reply_comment_id') if query.get(key)}
    if node_type == 'POST' and comments:
        raise ValueError('Comment URL cannot identify a post')
    if node_type != 'POST' and not comments:
        raise ValueError('Parent URL cannot identify a comment')
    if node_type == 'REPLY' and 'reply_comment_id' not in comments and 'comment_id' not in comments:
        raise ValueError('Reply requires a verified comment link')
    separator = '&' if '?' in target.url else '?'
    return target.url + (separator + urlencode(comments) if comments else '')


@dataclass
class ContentNode:
    node_type: str
    platform_item_id: str | None = None
    canonical_url: str | None = None
    node_id: str | None = None
    root_post_id: str | None = None
    parent_node_id: str | None = None
    provisional_key: str | None = None
    platform: str = 'FACEBOOK'
    schema_version: str = 'conversation-record-v2'
    relationship_status: str = 'RESOLVED'
    display_url: str | None = None
    url_type: str | None = None
    author_uid: str | None = None
    author_name: str | None = None
    author_url: str | None = None
    raw_text: str | None = None
    media_refs: list = field(default_factory=list)
    engagement: dict = field(default_factory=dict)
    published_at: str | None = None
    publication_precision: str = 'UNKNOWN'
    published_date_local: str | None = None
    timestamp_raw: str | None = None
    timestamp_basis: str | None = None
    edited_at: str | None = None
    extraction_status: str = 'PARTIAL'
    missing_fields: list = field(default_factory=list)
    availability_status: str = 'AVAILABLE'
    platform_shortcode: str | None = None
    platform_topic_tags: list = field(default_factory=list)
    link_relations: list = field(default_factory=list)

    def __post_init__(self):
        versions={'FACEBOOK':{'conversation-record-v2','conversation-record-v3'},'THREADS':{'conversation-record-v3'}}
        if self.node_type not in {'POST', 'COMMENT', 'REPLY'} or self.schema_version not in versions.get(self.platform,set()):
            raise ValueError('Invalid node type/platform/version')
        if self.relationship_status not in {'RESOLVED', 'PARTIAL', 'UNRESOLVED'} or self.extraction_status not in {'COMPLETE', 'PARTIAL', 'FAILED', 'REFERENCE_ONLY'} or self.availability_status not in {'AVAILABLE', 'UNAVAILABLE', 'DELETED_CONFIRMED', 'UNKNOWN'}:
            raise ValueError('Invalid acquisition status')
        if self.publication_precision not in {'INSTANT', 'APPROXIMATE', 'DATE_ONLY', 'UNKNOWN'}:
            raise ValueError('Invalid time precision')
        for key in ('platform_item_id', 'node_id', 'root_post_id', 'parent_node_id', 'provisional_key', 'author_uid'):
            value = getattr(self, key)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError('Invalid node identifier')
        if self.raw_text is not None and not isinstance(self.raw_text, str):
            raise ValueError('Invalid raw text')
        for key in ('published_at', 'edited_at'):
            if getattr(self, key) is not None:
                setattr(self, key, parse_utc(getattr(self, key)).isoformat().replace('+00:00', 'Z'))
        if self.publication_precision == 'INSTANT' and self.published_at is None:
            raise ValueError('Instant publication requires timestamp')
        if self.publication_precision == 'UNKNOWN' and self.published_at is not None:
            raise ValueError('Unknown precision cannot carry publication instant')
        if self.published_date_local is not None:
            date.fromisoformat(self.published_date_local)
        if self.publication_precision == 'DATE_ONLY' and (not self.published_date_local or self.published_at):
            raise ValueError('Date-only time requires date without instant')
        if not isinstance(self.media_refs, list) or not isinstance(self.missing_fields, list) or not isinstance(self.engagement, dict) or not isinstance(self.platform_topic_tags,list) or not isinstance(self.link_relations,list):
            raise ValueError('Invalid raw metadata')
        if any(v is not None and (type(v) is not int or v < 0) for v in self.engagement.values()):
            raise ValueError('Engagement must be null or nonnegative integer')
        self.canonical_url = canonical_node_url(self.canonical_url, self.node_type, self.platform)
        if self.canonical_url:
            self.display_url, self.url_type = self.canonical_url, 'DIRECT'
        elif self.display_url:
            if self.node_type == 'POST' or self.url_type != 'PARENT_FALLBACK':
                raise ValueError('Unverified direct URL')
            self.display_url = canonical_node_url(self.display_url, 'POST', self.platform)
        elif self.url_type is not None:
            raise ValueError('URL type without URL')
        if self.node_type == 'POST' and self.parent_node_id is not None:
            raise ValueError('Post cannot have parent')
        if self.node_type != 'POST' and (not self.root_post_id or not self.parent_node_id):
            if self.relationship_status == 'RESOLVED':
                raise ValueError('Resolved child requires root and parent')
        if not self.platform_item_id and not self.canonical_url and not self.provisional_key:
            self.provisional_key = 'provisional_' + uuid.uuid4().hex

    def payload(self):
        value=asdict(self)
        if self.schema_version=='conversation-record-v2':
            for key in ('platform_shortcode','platform_topic_tags','link_relations'):value.pop(key)
        return value


def node_from_candidate(candidate, node_id=None):
    if candidate.platform != 'facebook' or candidate.candidate_kind != 'CONTENT_ITEM':
        raise ValueError('Raw-first candidate must be a Facebook content item')
    return ContentNode('POST', platform_item_id=candidate.platform_item_id, canonical_url=candidate.canonical_url,
        node_id=node_id, raw_text=candidate.raw_text if candidate.raw_text is not None else candidate.caption,
        author_uid=candidate.author.get('platform_author_id'), author_name=candidate.author.get('display_name'),
        author_url=candidate.author.get('profile_url'), media_refs=candidate.media_refs, engagement=candidate.engagement,
        published_at=candidate.published_at, publication_precision=candidate.publication_precision,
        published_date_local=candidate.publication_date, timestamp_raw=candidate.published_time_raw,
        extraction_status='COMPLETE' if candidate.extraction_status == 'FETCHED' else 'PARTIAL',
        missing_fields=list(candidate.missing_data_reasons))
