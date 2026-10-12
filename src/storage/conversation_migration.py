"""Backed-up, additive migration. Never alter or purge legacy tables."""
import json
import hashlib
from pathlib import Path
import sqlite3
import uuid
from src.acquisition.models import Candidate, utcnow
from src.domain.conversation import node_from_candidate
from src.storage.conversations import ConversationStore, encode


def backup_database(database, backup):
    source, target = Path(database).resolve(), Path(backup).resolve()
    if source == target or target.exists() or not source.is_file():
        raise ValueError('Expected existing database and new distinct backup path')
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
    try:
        destination = sqlite3.connect(target)
        try:
            connection.backup(destination)
            if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup integrity failed')
        finally:
            destination.close()
    finally:
        connection.close()
    return str(target)


def migrate_legacy(database, backup, preserve_existing=False):
    backup_path = backup_database(database, backup)
    store = ConversationStore(database)
    try:
        tables = {r[0] for r in store.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        count = imported = skipped = 0
        migration_id = 'migration_' + uuid.uuid4().hex
        with store.transaction():
            rows = store.db.execute('SELECT record_id,payload FROM records').fetchall() if 'records' in tables else []
            for row in rows:
                count += 1
                payload = json.loads(row['payload'])
                if payload.get('platform') != 'facebook':
                    skipped += 1
                    continue
                candidate = Candidate(**{k: v for k, v in payload.items() if k in Candidate.__dataclass_fields__})
                node = node_from_candidate(candidate)
                known = {r[0] for alias in store.aliases(node) for r in store.db.execute('SELECT node_id FROM node_aliases WHERE alias=?', (alias,))}
                if len(known) > 1:
                    raise ValueError('Legacy identity conflict')
                node.node_id = next(iter(known), row['record_id'])
                current = store.get(node.node_id) if known and preserve_existing else None
                if current:
                    result = {'node_id':current['node_id'],'revision_id':current['revision_id']}
                    store.db.execute('INSERT OR IGNORE INTO node_sources VALUES (?,?,?)',
                        (current['node_id'],candidate.source_id,encode({'first_seen_at':candidate.collected_at or utcnow()})))
                else:
                    result = store.ingest(node, candidate.source_id, candidate.crawl_run_id,
                        observation_id='legacy-record:' + row['record_id'] + ':' + hashlib.sha256(row['payload'].encode()).hexdigest(),
                        observed_at=candidate.collected_at, lineage={'discovered_via': 'LEGACY_MIGRATION'})
                node_id = result['node_id']
                store.db.execute('INSERT OR IGNORE INTO legacy_node_map VALUES (?,?)', (row['record_id'], node_id))
                if 'aliases' in tables:
                    for alias in store.db.execute('SELECT alias FROM aliases WHERE record_id=?', (row['record_id'],)).fetchall():
                        store.db.execute('INSERT OR IGNORE INTO node_aliases VALUES (?,?)', ('legacy:' + alias[0], node_id))
                if 'observations' in tables:
                    for observation in store.db.execute('SELECT candidate_id,payload FROM observations WHERE record_id=?', (row['record_id'],)).fetchall():
                        obs = json.loads(observation['payload'])
                        store.db.execute('INSERT OR IGNORE INTO conversation_observations VALUES (?,?,?,?,?,?)',
                            ('legacy-observation:' + observation['candidate_id'], node_id, result['revision_id'],
                             obs.get('source_id') or candidate.source_id, obs.get('crawl_run_id') or candidate.crawl_run_id, encode(obs)))
                if 'content_reviews' in tables:
                    review = store.db.execute('SELECT payload FROM content_reviews WHERE record_id=?', (row['record_id'],)).fetchone()
                    if review:
                        store.db.execute('INSERT OR IGNORE INTO node_reviews VALUES (?,?)', (node_id, review[0]))
                if 'content_review_history' in tables:
                    for review in store.db.execute('SELECT id,payload FROM content_review_history WHERE record_id=?', (row['record_id'],)).fetchall():
                        store.db.execute('INSERT OR IGNORE INTO node_review_history VALUES (?,?,?)',
                            ('legacy-review:' + str(review['id']), node_id, review['payload']))
                imported += 1
            report = dict(migration_id=migration_id, status='MIGRATED', completed_at=utcnow(), backup=backup_path,
                legacy_records=count, facebook_records_mapped=imported, other_platform_records_unchanged=skipped,
                legacy_tables_modified=False, data_previously_purged_recovered=False)
            store.db.execute('INSERT INTO conversation_migrations VALUES (?,?)', (migration_id, encode(report)))
        return report
    finally:
        store.close()


def rollback_to_copy(backup, restored):
    """Rehearse restore into a new path; never overwrite production/WAL files."""
    return backup_database(backup, restored)
