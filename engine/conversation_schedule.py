"""Fixed Vietnam slots, durable ticks and bounded leases for v2 workers."""
from datetime import datetime, time, timedelta, timezone
import hashlib
import json
import uuid
from src.acquisition.models import parse_utc
from src.storage.conversations import encode

VN = timezone(timedelta(hours=7))
DEFAULT_SLOTS = ((time(5), time(8,30)), (time(17), time(18,30)))


def daily_ticks(day, slots=DEFAULT_SLOTS, interval_minutes=45):
    if type(interval_minutes) is not int or interval_minutes <= 0:
        raise ValueError('Positive interval required')
    for opening, closing in slots:
        start = datetime.combine(day, opening, VN)
        end = datetime.combine(day, closing, VN)
        if start >= end:
            raise ValueError('Same-day nonempty slot required')
        tick = start
        while tick < end:
            yield start, tick, False
            tick += timedelta(minutes=interval_minutes)
        yield start, end, True


class CrawlTasks:
    def __init__(self, raw):
        self.raw = raw
        raw.db.executescript('''
          CREATE TABLE IF NOT EXISTS conversation_tasks(
            task_id TEXT PRIMARY KEY,source_id TEXT NOT NULL,payload TEXT NOT NULL,
            status TEXT NOT NULL,scheduled_for TEXT NOT NULL,lease_until TEXT,
            lease_token TEXT,attempts INTEGER NOT NULL DEFAULT 0,result TEXT);
          CREATE INDEX IF NOT EXISTS conversation_task_due ON conversation_tasks(status,scheduled_for);
          CREATE TABLE IF NOT EXISTS thread_inventory(
            source_id TEXT NOT NULL,node_id TEXT NOT NULL REFERENCES content_nodes(node_id),
            post_url TEXT NOT NULL,last_scanned_at TEXT,last_outcome TEXT,
            PRIMARY KEY(source_id,node_id));
        ''')

    def enqueue_days(self, source_ids, first_day, last_day, now, schedule_id='daily-v2', slots=DEFAULT_SLOTS):
        """Explicit date range is the backfill bound; restart replays only missing keys."""
        if not source_ids or first_day > last_day or (last_day-first_day).days > 366:
            raise ValueError('Source IDs and date range of at most 367 days required')
        now = parse_utc(now)
        inserted = 0
        day = first_day
        with self.raw.transaction():
            while day <= last_day:
                for start,tick,final in daily_ticks(day, slots):
                    if tick > now: continue
                    for source_id in sorted(set(source_ids)):
                        key = encode([schedule_id,source_id,start.isoformat(),tick.isoformat()])
                        task_id = 'crawl_' + hashlib.sha256(key.encode()).hexdigest()
                        payload = dict(source_id=source_id,window_start=start.isoformat(),window_end=tick.isoformat(),
                            inventory_only=tick==start,final_tick=final,schedule_id=schedule_id)
                        inserted += self.raw.db.execute('INSERT OR IGNORE INTO conversation_tasks(task_id,source_id,payload,status,scheduled_for) VALUES (?,?,?,?,?)',
                            (task_id,source_id,encode(payload),'PENDING',tick.astimezone(timezone.utc).isoformat())).rowcount
                day += timedelta(days=1)
        return inserted

    def claim(self, now, lease_seconds=1200, max_attempts=3, task_id=None):
        now = parse_utc(now)
        if lease_seconds <= 0 or max_attempts <= 0: raise ValueError('Positive lease/attempts required')
        with self.raw.transaction():
            self.raw.db.execute("UPDATE conversation_tasks SET status='FAILED',result=? WHERE status='RUNNING' AND lease_until<=? AND attempts>=?",
                (encode({'error_code':'WORKER_LEASE_EXHAUSTED'}),now.isoformat(),max_attempts))
            row = self.raw.db.execute("SELECT * FROM conversation_tasks WHERE scheduled_for<=? AND attempts<? AND ((status='PENDING' AND (lease_until IS NULL OR lease_until<=?)) OR (status='RUNNING' AND lease_until<=?)) AND (? IS NULL OR task_id=?) ORDER BY scheduled_for,source_id LIMIT 1",
                (now.isoformat(),max_attempts,now.isoformat(),now.isoformat(),task_id,task_id)).fetchone()
            if not row: return None
            token = uuid.uuid4().hex
            self.raw.db.execute("UPDATE conversation_tasks SET status='RUNNING',lease_until=?,lease_token=?,attempts=attempts+1 WHERE task_id=?",
                ((now+timedelta(seconds=lease_seconds)).isoformat(),token,row['task_id']))
            return {**json.loads(row['payload']),'task_id':row['task_id'],'lease_token':token,'attempt':row['attempts']+1}

    def finish(self, task, result, now):
        with self.raw.transaction():
            if result.get('status')=='SKIPPED' and (result.get('error_code')=='PROFILE_IN_USE' or result.get('inventory',{}).get('error_code')=='PROFILE_IN_USE'):
                changed=self.raw.db.execute("UPDATE conversation_tasks SET status='PENDING',result=?,lease_until=?,lease_token=NULL,attempts=attempts-1 WHERE task_id=? AND status='RUNNING' AND lease_token=? AND lease_until>?",
                    (encode(result),(parse_utc(now)+timedelta(seconds=30)).isoformat(),task['task_id'],task['lease_token'],parse_utc(now).isoformat())).rowcount
                if changed!=1: raise ValueError('Task lease expired or belongs to another worker')
                return
            changed = self.raw.db.execute("UPDATE conversation_tasks SET status='DONE',result=?,lease_until=NULL WHERE task_id=? AND status='RUNNING' AND lease_token=? AND lease_until>?",
                (encode(result),task['task_id'],task['lease_token'],parse_utc(now).isoformat())).rowcount
            if changed != 1: raise ValueError('Task lease expired or belongs to another worker')

    def add_post(self, source_id, node_id, post_url):
        node = self.raw.get(node_id)
        if not node or node['node_type'] != 'POST' or node['canonical_url'] != post_url:
            raise ValueError('Verified stored post URL required')
        with self.raw.transaction():
            self.raw.db.execute('INSERT INTO thread_inventory(source_id,node_id,post_url) VALUES (?,?,?) ON CONFLICT(source_id,node_id) DO UPDATE SET post_url=excluded.post_url',
                (source_id,node_id,post_url))

    def fair_posts(self, source_id, limit=20):
        if type(limit) is not int or limit <= 0: raise ValueError('Positive inventory limit required')
        # Never restrict by parent publication time. Never-scanned/oldest scan first.
        return [dict(row) for row in self.raw.db.execute('SELECT * FROM thread_inventory WHERE source_id=? ORDER BY last_scanned_at IS NOT NULL,last_scanned_at,node_id LIMIT ?',
            (source_id,limit))]

    def scanned(self, source_id, node_id, outcome, now):
        with self.raw.transaction():
            self.raw.db.execute('UPDATE thread_inventory SET last_scanned_at=?,last_outcome=? WHERE source_id=? AND node_id=?',
                (parse_utc(now).isoformat(),encode(outcome),source_id,node_id))
