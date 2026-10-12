"""Backed-up atomic merge of disjoint SQLite schemas, preserving every source row."""
import sqlite3
from pathlib import Path
from src.storage.conversation_migration import backup_database, migrate_legacy
from src.storage.conversations import ConversationStore
from engine.conversation_schedule import CrawlTasks
from src.acquisition.identity import identify, source_references


def quote(name):
    return '"'+name.replace('"','""')+'"'


def consolidate(source, target, backup_dir, registry):
    source,target,backup_dir=Path(source).resolve(),Path(target).resolve(),Path(backup_dir).resolve()
    if source==target: raise ValueError('Distinct databases required')
    backups={key:backup_database(path,backup_dir/(key+'.sqlite3')) for key,path in [('raw-v2',source),('acquisition',target)]}
    db=sqlite3.connect(target,timeout=10)
    copied={}
    try:
        db.execute('ATTACH DATABASE ? AS incoming',(str(source),))
        db.execute('BEGIN IMMEDIATE')
        objects=db.execute("SELECT type,name,sql FROM incoming.sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type='table' DESC").fetchall()
        for kind,name,sql in objects:
            exists=db.execute('SELECT sql FROM main.sqlite_master WHERE name=?',(name,)).fetchone()
            if exists and exists[0]!=sql: raise ValueError('Schema collision: '+name)
            if not exists: db.execute(sql)
            if kind=='table':
                db.execute('INSERT OR IGNORE INTO main.'+quote(name)+' SELECT * FROM incoming.'+quote(name))
                # Detect conflicting rows rather than silently dropping them.
                missing=db.execute('SELECT * FROM incoming.'+quote(name)+' EXCEPT SELECT * FROM main.'+quote(name)).fetchone()
                if missing: raise ValueError('Data collision: '+name)
                copied[name]=db.execute('SELECT count(*) FROM incoming.'+quote(name)).fetchone()[0]
        if db.execute('PRAGMA main.foreign_key_check').fetchone(): raise ValueError('Foreign key validation failed')
        if db.execute('PRAGMA main.integrity_check').fetchone()[0]!='ok': raise ValueError('Integrity validation failed')
        db.commit()
    except Exception:
        db.rollback();raise
    finally: db.close()
    migration=migrate_legacy(target,backup_dir/'merged-before-legacy-migration.sqlite3',preserve_existing=True)
    raw=ConversationStore(target)
    try:
        tasks=CrawlTasks(raw); seeded=0
        for node in raw.list_nodes(node_type='POST'):
            try: item=identify(node['canonical_url'] or '')
            except ValueError: continue
            for sid,src in registry.sources.items():
                if src.get('source_type')=='FACEBOOK_GROUP' and item.origin in source_references(src):
                    tasks.add_post(sid,node['node_id'],node['canonical_url']);seeded+=1
        if raw.db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or raw.db.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('Final integrity validation failed')
        counts={r[0]:r[1] for r in raw.db.execute('SELECT node_type,count(*) FROM content_nodes GROUP BY node_type')}
        return dict(status='CONSOLIDATED',database=str(target),backups=backups,source_tables_preserved=copied,
            legacy_migration=migration,raw_counts=counts,inventory_posts_seeded=seeded,integrity='ok',foreign_keys='ok')
    finally: raw.close()
