"""Immutable OCR revisions with current pointers; backwards compatible with raw v2."""
import hashlib
import json
from src.storage.conversations import encode
from src.acquisition.models import utcnow


def ref_key(ref):
    return hashlib.sha256(encode({'id':ref.get('platform_media_id') or ref.get('url')}).encode()).hexdigest()


def initialize(raw):
    raw.db.executescript('''CREATE TABLE IF NOT EXISTS image_evidence(
      evidence_id TEXT PRIMARY KEY,node_id TEXT NOT NULL REFERENCES content_nodes(node_id),ref_key TEXT NOT NULL,
      payload TEXT NOT NULL,created_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS node_image_evidence(node_id TEXT NOT NULL REFERENCES content_nodes(node_id),
      ref_key TEXT NOT NULL,evidence_id TEXT NOT NULL REFERENCES image_evidence(evidence_id),PRIMARY KEY(node_id,ref_key));''')


def read(raw,node_id):
    if not raw.db.execute("SELECT 1 FROM sqlite_master WHERE name='node_image_evidence'").fetchone():return []
    node=raw.get(node_id)
    active={ref_key(r) for r in node['media_refs'] if r.get('media_type')=='IMAGE'} if node else set()
    return [dict(json.loads(r['payload']),evidence_id=r['evidence_id']) for r in raw.db.execute(
        'SELECT e.* FROM node_image_evidence n JOIN image_evidence e ON e.evidence_id=n.evidence_id WHERE n.node_id=? ORDER BY n.ref_key',(node_id,)) if r['ref_key'] in active]


def save(raw,node_id,ref,result):
    key=ref_key(ref)
    content={k:v for k,v in result.items() if k!='processed_at'}
    evidence_id='ocr:'+hashlib.sha256(encode([node_id,key,content]).encode()).hexdigest()
    payload=dict(result,node_id=node_id,media_ref=ref,media_ref_id=key)
    with raw.transaction():
        raw.db.execute('INSERT OR IGNORE INTO image_evidence VALUES (?,?,?,?,?)',(evidence_id,node_id,key,encode(payload),utcnow()))
        old=raw.db.execute('SELECT evidence_id FROM node_image_evidence WHERE node_id=? AND ref_key=?',(node_id,key)).fetchone()
        raw.db.execute('INSERT INTO node_image_evidence VALUES (?,?,?) ON CONFLICT(node_id,ref_key) DO UPDATE SET evidence_id=excluded.evidence_id',(node_id,key,evidence_id))
        if not old or old[0]!=evidence_id:
            node=raw.get(node_id);raw._event(node_id,node['revision_id'],'OCR_CHANGED:'+evidence_id,utcnow())
            for child in raw.db.execute('SELECT node_id,current_revision_id FROM content_nodes WHERE root_post_id=? AND node_id!=?',(node_id,node_id)):
                raw._event(child[0],child[1],'OCR_CONTEXT_CHANGED:'+evidence_id,utcnow())
    return evidence_id


def bindings(raw,node_id):
    return [dict(evidence_id=e['evidence_id'],text=e['text'],quality_status=e['quality_status'])
            for e in read(raw,node_id) if e['status']=='AVAILABLE' and e.get('text')]


def all_bindings(raw,nodes):
    if not raw.db.execute("SELECT 1 FROM sqlite_master WHERE name='node_image_evidence'").fetchone():return {}
    active={n['node_id']:{ref_key(r) for r in n['media_refs'] if r.get('media_type')=='IMAGE'} for n in nodes}
    output={}
    for row in raw.db.execute('SELECT e.* FROM node_image_evidence n JOIN image_evidence e ON e.evidence_id=n.evidence_id ORDER BY n.ref_key'):
        e=json.loads(row['payload'])
        if row['ref_key'] in active.get(row['node_id'],set()) and e['status']=='AVAILABLE' and e.get('text'):
            output.setdefault(row['node_id'],[]).append(dict(evidence_id=row['evidence_id'],text=e['text'],quality_status=e['quality_status']))
    return output


def summary(evidence,refs):
    images=[r for r in refs if r.get('media_type')=='IMAGE']
    statuses={e['status'] for e in evidence}
    status='NO_IMAGES' if not images else 'NOT_RUN' if not evidence else 'NEEDS_REVIEW' if any(e['status']=='AVAILABLE' and e['quality_status']!='ACCEPTABLE' for e in evidence) else 'PARTIAL' if len(evidence)<len(images) or len(statuses)>1 else next(iter(statuses))
    return {'ocr_status':status,'ocr_text':'\n\n'.join(e['text'] for e in evidence if e.get('text')),
            'image_evidence':evidence,'ocr_observed_images':len(images),'ocr_processed_images':len(evidence)}


def input_current(raw,item,nodes=None,images=None):
    node=(nodes or {}).get(item['item_id']) if nodes is not None else raw.get(item['item_id'])
    if not node:return False
    actual=[];seen=set()
    for origin_id,role in [(node['node_id'],'TARGET'),(node['root_post_id'],'ROOT_POST'),(node['parent_node_id'],'PARENT_COMMENT')]:
        if not origin_id or origin_id in seen:continue
        seen.add(origin_id)
        actual.extend((e['evidence_id'],origin_id,role) for e in (images.get(origin_id,[]) if images is not None else bindings(raw,origin_id)))
    return sorted(actual)==sorted((e['evidence_id'],e['item_id'],e['role']) for e in item.get('image_evidence',[]))
