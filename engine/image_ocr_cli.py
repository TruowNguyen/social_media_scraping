"""Probe OCR or refresh image references and OCR for one approved stored post."""
import argparse
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
from engine.registry import Registry
from engine.acquisition import adapter_job
from engine.image_enrichment import enrich_post
from src.acquisition.models import Candidate,Deadline,FetchContext,Window
from src.media.image_ocr import probe
from src.storage.conversations import ConversationStore

ROOT=Path(__file__).resolve().parents[1]


def reprocess(raw,node_id,registry,seconds=90):
    node=raw.get(node_id)
    if not node or node['node_type']!='POST' or not node['canonical_url']:raise ValueError('Stored post permalink required')
    sources=[r[0] for r in raw.db.execute('SELECT source_id FROM node_sources WHERE node_id=?',(node_id,))]
    source=next((registry.sources[s] for s in sources if s in registry.sources and not registry.readiness(registry.sources[s])),None)
    if not source:raise ValueError('Approved enabled accessible source required')
    deadline=Deadline(seconds);now=datetime.now(timezone.utc)
    candidate=Candidate('facebook',node['canonical_url'],node['canonical_url'],source['source_id'],'ocr_refresh_'+now.strftime('%Y%m%dT%H%M%S%f'),'BROWSER_THREAD',platform_item_id=node['platform_item_id'])
    with adapter_job(source,deadline,None) as adapter:
        fetched=adapter.fetch_item(candidate,FetchContext(source,Window(now-timedelta(days=14),now),deadline,raw_first=True)).candidate
        raw.ingest_candidate(fetched,'ocr_refresh')
        return enrich_post(raw,node_id,adapter.page,deadline)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe',action='store_true');parser.add_argument('--node-id')
    parser.add_argument('--db',type=Path,default=ROOT/'sessions/acquisition/acquisition.sqlite3')
    parser.add_argument('--config-dir',type=Path,default=ROOT/'config');parser.add_argument('--seconds',type=int,default=90)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    if not 1<=args.seconds<=300:parser.error('seconds must be 1..300')
    if args.probe:result=probe()
    else:
        if not args.node_id:parser.error('--node-id required unless --probe')
        raw=ConversationStore(args.db)
        try:result=reprocess(raw,args.node_id,Registry(args.config_dir),args.seconds)
        finally:raw.close()
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
