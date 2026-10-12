"""Append raw lineage/revisions; filtering never deletes conversation data."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid
from src.acquisition.models import utcnow, parse_utc
from src.domain.conversation import ContentNode, node_from_candidate


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


DDL = """
CREATE TABLE IF NOT EXISTS conversation_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS content_nodes(node_id TEXT PRIMARY KEY,identity_key TEXT UNIQUE NOT NULL,node_type TEXT NOT NULL,
 root_post_id TEXT,parent_node_id TEXT,payload TEXT NOT NULL,current_revision_id TEXT,first_seen_at TEXT NOT NULL,last_seen_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS node_aliases(alias TEXT PRIMARY KEY,node_id TEXT NOT NULL REFERENCES content_nodes(node_id));
CREATE TABLE IF NOT EXISTS content_revisions(revision_id TEXT PRIMARY KEY,node_id TEXT NOT NULL REFERENCES content_nodes(node_id),
 content_hash TEXT NOT NULL,payload TEXT NOT NULL,observed_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS node_sources(node_id TEXT NOT NULL REFERENCES content_nodes(node_id),source_id TEXT NOT NULL,
 payload TEXT NOT NULL,PRIMARY KEY(node_id,source_id));
CREATE TABLE IF NOT EXISTS conversation_observations(observation_id TEXT PRIMARY KEY,node_id TEXT NOT NULL REFERENCES content_nodes(node_id),
 revision_id TEXT NOT NULL REFERENCES content_revisions(revision_id),source_id TEXT NOT NULL,run_id TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS node_reviews(node_id TEXT PRIMARY KEY REFERENCES content_nodes(node_id),payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS node_review_history(history_id TEXT PRIMARY KEY,node_id TEXT NOT NULL REFERENCES content_nodes(node_id),payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS raw_filter_decisions(node_id TEXT NOT NULL REFERENCES content_nodes(node_id),revision_id TEXT NOT NULL,
 rule_version TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(node_id,revision_id,rule_version));
CREATE TABLE IF NOT EXISTS conversation_outbox(event_id TEXT PRIMARY KEY,node_id TEXT NOT NULL REFERENCES content_nodes(node_id),
 revision_id TEXT NOT NULL,kind TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS conversation_checkpoints(task_id TEXT PRIMARY KEY,payload TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS legacy_node_map(record_id TEXT PRIMARY KEY,node_id TEXT NOT NULL REFERENCES content_nodes(node_id));
CREATE TABLE IF NOT EXISTS conversation_migrations(migration_id TEXT PRIMARY KEY,payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS node_thread ON content_nodes(root_post_id);
CREATE INDEX IF NOT EXISTS observation_run ON conversation_observations(run_id);
CREATE TABLE IF NOT EXISTS ingest_page_receipts(page_id TEXT PRIMARY KEY,checksum TEXT NOT NULL,task_id TEXT NOT NULL,payload TEXT NOT NULL,committed_at TEXT NOT NULL);
"""


class ConversationStore:
    def __init__(self, path, *, initialize=True):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        if not initialize:
            return
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript(DDL)
        with self.transaction():
            row = self.db.execute("SELECT value FROM conversation_meta WHERE key='schema_version'").fetchone()
            if row and row[0] not in {'conversation-store-v2','conversation-store-v3'}:
                raise ValueError('Unsupported conversation store version')
            self.db.execute("INSERT OR IGNORE INTO conversation_meta VALUES ('schema_version','conversation-store-v2')")
            self.db.execute("INSERT OR IGNORE INTO conversation_meta VALUES ('reader_capability','conversation-record-v2,v3')")

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        if self.db.in_transaction:
            # Nested scopes must roll back their own work even when caller catches errors.
            name = 'sp_' + uuid.uuid4().hex
            self.db.execute('SAVEPOINT ' + name)
            try:
                yield
                self.db.execute('RELEASE ' + name)
            except Exception:
                self.db.execute('ROLLBACK TO ' + name)
                self.db.execute('RELEASE ' + name)
                raise
            return
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def get(self, node_id):
        row = self.db.execute('SELECT * FROM content_nodes WHERE node_id=?', (node_id,)).fetchone()
        if not row:
            return None
        return {**json.loads(row['payload']), 'node_id': row['node_id'], 'revision_id': row['current_revision_id'],
            'first_seen_at': row['first_seen_at'], 'last_seen_at': row['last_seen_at']}

    @staticmethod
    def aliases(node):
        # Facebook comments and replies share native Comment IDs.
        prefix = node.platform + ':' + ('MEDIA' if node.platform=='THREADS' else 'POST' if node.node_type == 'POST' else 'COMMENT') + ':'
        result = []
        if node.platform_item_id:
            result.append(prefix + 'native:' + node.platform_item_id)
        if node.canonical_url:
            result.append(prefix + 'url:' + node.canonical_url)
        return result or [prefix + 'provisional:' + node.provisional_key]

    def ingest(self, node, source_id, run_id, observation_id=None, observed_at=None, lineage=None, *, reconcile_unresolved=False):
        if not isinstance(node, ContentNode) or not all(isinstance(v, str) and v.strip() for v in (source_id, run_id)):
            raise ValueError('Expected validated node/source/run')
        stamp = parse_utc(observed_at or utcnow()).isoformat().replace('+00:00', 'Z')
        observation_id = observation_id or 'obs_' + uuid.uuid4().hex
        with self.transaction():
            if node.platform=='THREADS':
                self.db.execute("UPDATE conversation_meta SET value='conversation-store-v3' WHERE key='schema_version'")
            aliases = self.aliases(node)
            matches = {r[0] for alias in aliases for r in self.db.execute('SELECT node_id FROM node_aliases WHERE alias=?', (alias,))}
            if len(matches) > 1:
                raise ValueError('Conflicting identities require explicit reconciliation')
            existing = next(iter(matches), None)
            if node.node_id and existing and node.node_id != existing:
                raise ValueError('Requested node ID conflicts with known identity')
            node_id = existing or node.node_id or 'node_' + uuid.uuid4().hex
            old = self.get(node_id)
            if reconcile_unresolved and not (old and node.platform=='THREADS' and old['relationship_status']=='UNRESOLVED' and node.relationship_status=='UNRESOLVED' and node.node_type==old['node_type'] and node.node_type!='POST' and node.root_post_id is None and node.parent_node_id is None):
                raise ValueError('Only unresolved Threads context can be cleared')
            reference_upgrade = old and old['extraction_status'] == 'REFERENCE_ONLY' and (old['node_type'] == node.node_type or {old['node_type'],node.node_type} <= {'COMMENT','REPLY'})
            if old and not existing and not reference_upgrade:
                raise ValueError('Node ID belongs to another identity')
            payload = node.payload()
            payload['node_id'] = node_id
            if node.node_type == 'POST':
                payload['root_post_id'] = node_id
            if old:
                if old['platform'] != node.platform:
                    raise ValueError('Cannot change node platform')
                if old['platform_item_id'] and node.platform_item_id and old['platform_item_id'] != node.platform_item_id:
                    raise ValueError('Native ID conflicts with URL alias')
                relationship_upgrade=node.platform=='THREADS' and old.get('relationship_status')!='RESOLVED' and (node.relationship_status=='RESOLVED' or old['node_type']=='POST' and node.node_type!='POST' and payload['root_post_id']!=node_id)
                if node.platform=='THREADS' and node.relationship_status!='RESOLVED' and old['node_type']!='POST' and node.node_type=='POST':
                    for key in ('node_type','root_post_id','parent_node_id','relationship_status'):payload[key]=old[key]
                    payload['missing_fields']=[f for f in payload['missing_fields'] if f!='UNVERIFIED_NODE_TYPE']
                    if payload['relationship_status']!='RESOLVED' and 'UNRESOLVED_PARENT' not in payload['missing_fields']:payload['missing_fields'].append('UNRESOLVED_PARENT')
                    if payload['root_post_id'] is None and 'UNRESOLVED_ROOT' not in payload['missing_fields']:payload['missing_fields'].append('UNRESOLVED_ROOT')
                if not reference_upgrade and not relationship_upgrade and not reconcile_unresolved and (old['root_post_id'] != payload['root_post_id'] or old['parent_node_id'] != payload['parent_node_id']):
                    raise ValueError('Thread identity cannot silently change')
                # Missing discovery metadata must not erase successfully fetched data.
                for key in ('raw_text', 'published_at', 'published_date_local', 'timestamp_raw', 'canonical_url',
                            'display_url', 'url_type', 'platform_item_id', 'author_uid', 'author_name', 'author_url'):
                    if payload[key] is None and old.get(key) is not None:
                        payload[key] = old[key]
                if (node.publication_precision == 'UNKNOWN' and old['publication_precision'] != 'UNKNOWN') or (old['publication_precision'] == 'INSTANT' and node.publication_precision == 'DATE_ONLY'):
                    payload['publication_precision'] = old['publication_precision']
                if node.raw_text is None and old['raw_text'] is not None:
                    payload['extraction_status'] = old['extraction_status']
                    payload['missing_fields'] = old['missing_fields']
                if not node.media_refs and old['media_refs'] and node.extraction_status != 'COMPLETE':
                    payload['media_refs'] = old['media_refs']
                if node.platform=='THREADS':
                    from urllib.parse import urlsplit
                    def asset(ref):
                        url=urlsplit(ref.get('url',''))
                        return ('meta-cdn:'+url.path) if url.hostname and url.hostname.endswith('.fbcdn.net') else ref.get('url')
                    previous_media={asset(ref):ref for ref in old['media_refs']}
                    for ref in payload['media_refs']:
                        previous_ref=previous_media.get(asset(ref),{})
                        if not ref.get('alt_text') and previous_ref.get('alt_text'):
                            ref['alt_text']=previous_ref['alt_text']
                for key, value in old['engagement'].items():
                    if payload['engagement'].get(key) is None:
                        payload['engagement'][key] = value
            self._validate_thread(payload)
            ContentNode(**payload)
            # Revision fingerprint includes changes that affect context/extraction, not observation time.
            content = {k: payload[k] for k in ('raw_text', 'media_refs', 'published_at', 'publication_precision',
                'published_date_local', 'edited_at', 'extraction_status', 'missing_fields', 'availability_status')}
            if node.platform=='THREADS':
                content.update({k:payload.get(k) for k in ('platform_topic_tags','link_relations','relationship_status','parent_node_id')})
            fingerprint=dict(content)
            if node.platform=='THREADS':
                from urllib.parse import urlsplit
                normalized=[]
                for ref in content['media_refs']:
                    value=dict(ref);url=urlsplit(value.get('url',''))
                    # Meta CDN signatures/edge hosts refresh without changing the
                    # image. Keep the latest download URL in raw; fingerprint the
                    # stable asset path. Other providers keep their complete URL.
                    if url.hostname and url.hostname.endswith('.fbcdn.net'):value['url']='meta-cdn:'+url.path
                    normalized.append(value)
                fingerprint['media_refs']=normalized
            digest = hashlib.sha256(encode(fingerprint).encode('utf-8')).hexdigest()
            previous = self.db.execute('SELECT content_hash FROM content_revisions WHERE revision_id=?', (old['revision_id'],)).fetchone() if old else None
            changed = previous is None or previous[0] != digest or bool(old and old['root_post_id']!=payload['root_post_id'])
            revision_id = 'rev_' + uuid.uuid4().hex if changed else old['revision_id']
            first = min(stamp, old['first_seen_at'], key=parse_utc) if old else stamp
            last = max(stamp, old['last_seen_at'], key=parse_utc) if old else stamp
            self.db.execute('''INSERT INTO content_nodes VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(node_id) DO UPDATE SET payload=excluded.payload,current_revision_id=excluded.current_revision_id,
                  node_type=excluded.node_type,root_post_id=excluded.root_post_id,parent_node_id=excluded.parent_node_id,
                  first_seen_at=excluded.first_seen_at,last_seen_at=excluded.last_seen_at''',
                (node_id, aliases[0], payload['node_type'], payload['root_post_id'], payload['parent_node_id'], encode(payload), revision_id, first, last))
            if changed:
                self.db.execute('INSERT INTO content_revisions VALUES (?,?,?,?,?)', (revision_id, node_id, digest, encode(content), stamp))
                self._event(node_id, revision_id, 'RAW_CHANGED', stamp)
                if node.node_type in {'POST', 'COMMENT'}:
                    for row in self.db.execute('SELECT node_id,current_revision_id FROM content_nodes WHERE parent_node_id=? OR root_post_id=?', (node_id, node_id)).fetchall():
                        if row[0] != node_id:
                            self._event(row[0], row[1], 'CONTEXT_CHANGED:' + revision_id, stamp)
            for alias in aliases:
                self.db.execute('INSERT OR IGNORE INTO node_aliases VALUES (?,?)', (alias, node_id))
            self.db.execute('INSERT OR IGNORE INTO node_sources VALUES (?,?,?)', (node_id, source_id, encode({'first_seen_at': stamp})))
            obs = dict(lineage or {}, observed_at=stamp, source_id=source_id, crawl_run_id=run_id)
            prior = self.db.execute('SELECT node_id,revision_id,source_id,run_id FROM conversation_observations WHERE observation_id=?', (observation_id,)).fetchone()
            if prior and tuple(prior) != (node_id, revision_id, source_id, run_id):
                raise ValueError('Observation ID reused for different content/revision')
            self.db.execute('INSERT OR IGNORE INTO conversation_observations VALUES (?,?,?,?,?,?)',
                (observation_id, node_id, revision_id, source_id, run_id, encode(obs)))
            return {'node_id': node_id, 'revision_id': revision_id, 'new': old is None, 'changed': changed}

    def _validate_thread(self, payload):
        for key in ('root_post_id','parent_node_id'):
            if payload.get(key) and payload[key]!=payload['node_id']:
                referenced=self.get(payload[key])
                if referenced and referenced['platform']!=payload['platform']:raise ValueError('Cross-platform thread reference')
        if payload['node_type'] == 'POST':
            return
        if payload['node_id'] == payload['parent_node_id'] or payload['node_id'] == payload['root_post_id']:
            raise ValueError('Cyclic thread reference')
        if payload['platform']=='THREADS' and payload.get('root_post_id'):
            root=self.get(payload['root_post_id'])
            if root and root['node_type']!='POST':raise ValueError('Unverified root must not reference a reply')
        seen={payload['node_id']};parent_id=payload.get('parent_node_id')
        while parent_id:
            if parent_id in seen:raise ValueError('Cyclic thread reference')
            seen.add(parent_id);parent=self.get(parent_id);parent_id=parent.get('parent_node_id') if parent else None
        if payload['relationship_status'] == 'RESOLVED':
            root, parent = self.get(payload['root_post_id']), self.get(payload['parent_node_id'])
            if not root or root['node_type'] != 'POST' or not parent or parent['root_post_id'] != root['node_id']:
                raise ValueError('Root/parent missing or from different thread')
            if root['platform'] != payload['platform'] or parent['platform'] != payload['platform']:
                raise ValueError('Root/parent must share platform')
            if payload['node_type'] == 'COMMENT' and parent['node_type'] != 'POST':
                raise ValueError('Comment parent must be a post')
            if payload['node_type'] == 'REPLY' and parent['node_type'] == 'POST':
                raise ValueError('Reply parent must be a comment/reply')

    def reconcile_threads_context(self, run_id):
        """Clear unverified contexts whose provisional root was later a reply."""
        repaired=[]
        for node in self.list_nodes():
            if node['platform']!='THREADS' or node['node_type']=='POST' or node['relationship_status']!='UNRESOLVED' or not node.get('root_post_id'):continue
            root=self.get(node['root_post_id'])
            if not root or root['node_type']=='POST':continue
            payload={k:v for k,v in node.items() if k not in {'revision_id','first_seen_at','last_seen_at','window_status'}}
            payload.update(root_post_id=None,parent_node_id=None)
            if 'UNRESOLVED_ROOT' not in payload['missing_fields']:payload['missing_fields'].append('UNRESOLVED_ROOT')
            source=self.db.execute('SELECT source_id FROM node_sources WHERE node_id=? LIMIT 1',(node['node_id'],)).fetchone()[0]
            repaired.append(self.ingest(ContentNode(**payload),source,run_id,reconcile_unresolved=True))
        return repaired

    def _event(self, node_id, revision_id, kind, stamp):
        key = hashlib.sha256(encode([node_id, revision_id, kind]).encode()).hexdigest()
        self.db.execute('INSERT OR IGNORE INTO conversation_outbox VALUES (?,?,?,?,?,?,?)',
            (key, node_id, revision_id, kind, 'PENDING', encode({'node_id': node_id, 'revision_id': revision_id}), stamp))

    def ensure_reference(self, node_id, node_type, source_id, run_id, root_post_id=None, parent_node_id=None, platform='FACEBOOK'):
        """Create an explicitly unresolved context stub, not a fabricated post."""
        existing = self.get(node_id)
        if existing:
            if existing['node_type'] != node_type or existing['platform'] != platform:
                raise ValueError('Reference type mismatch')
            return node_id
        self.ingest(ContentNode(node_type, node_id=node_id, root_post_id=root_post_id,
            parent_node_id=parent_node_id, provisional_key='reference:' + node_id,
            relationship_status='UNRESOLVED', extraction_status='REFERENCE_ONLY', availability_status='UNKNOWN',
            platform=platform,schema_version='conversation-record-v3' if platform=='THREADS' else 'conversation-record-v2'),
            source_id, run_id)
        return node_id

    def ingest_candidate(self, candidate, observation_suffix='raw'):
        return self.ingest(node_from_candidate(candidate), candidate.source_id, candidate.crawl_run_id,
            observation_id=candidate.candidate_id + ':' + observation_suffix,
            lineage={k: getattr(candidate, k) for k in ('query_id', 'query_type', 'search_keyword', 'discovered_via', 'discovered_at', 'collected_at')})

    def ingest_batch(self, entries, task_id, checkpoint):
        with self.transaction():
            result = [self.ingest(**entry) for entry in entries]
            self.db.execute('INSERT INTO conversation_checkpoints VALUES (?,?,?) ON CONFLICT(task_id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',
                (task_id, encode(checkpoint), utcnow()))
            return result

    def filter_saved(self, node_id, decision, rule_version):
        # Decision derives from already committed data. No raw DELETE API here.
        if decision.get('prefilter_decision') not in {'PASS', 'DROP', 'REVIEW'} or not rule_version:
            raise ValueError('Invalid saved-raw filter decision')
        with self.transaction():
            node = self.get(node_id)
            if not node:
                raise ValueError('Raw node not found')
            payload = dict(decision, filtered_at=utcnow(), raw_revision_id=node['revision_id'])
            self.db.execute('INSERT OR REPLACE INTO raw_filter_decisions VALUES (?,?,?,?)',
                (node_id, node['revision_id'], rule_version, encode(payload)))

    def review(self, node_id, status, note):
        if status not in {'UNREVIEWED', 'RELEVANT', 'IRRELEVANT', 'NEEDS_REVIEW'} or not isinstance(note, str) or len(note) > 2000:
            raise ValueError('Invalid review')
        with self.transaction():
            if not self.get(node_id):
                raise ValueError('Node not found')
            payload = encode({'status': status, 'note': note, 'updated_at': utcnow()})
            self.db.execute('INSERT OR REPLACE INTO node_reviews VALUES (?,?)', (node_id, payload))
            self.db.execute('INSERT INTO node_review_history VALUES (?,?,?)', ('review_' + uuid.uuid4().hex, node_id, payload))

    def list_nodes(self, source_id=None, window=None, node_type=None):
        rows = self.db.execute('SELECT node_id FROM content_nodes ORDER BY first_seen_at,node_id').fetchall()
        output = []
        for row in rows:
            node = self.get(row[0])
            if source_id and not self.db.execute('SELECT 1 FROM node_sources WHERE node_id=? AND source_id=?', (row[0], source_id)).fetchone():
                continue
            if node_type and node['node_type'] != node_type:
                continue
            node['window_status'] = window.status(node['published_at'], node['publication_precision']) if window else None
            if window and node['window_status'] != 'IN_WINDOW':
                continue
            output.append(node)
        return output
