"""Durable liveness signal, independent of provider request duration."""
import threading
import uuid
from src.storage.conversations import ConversationStore, encode
from src.acquisition.models import utcnow


class Heartbeat:
    def __init__(self,database):
        self.database=database;self.identifier='classifier_'+uuid.uuid4().hex
        self.stop=threading.Event();self.thread=None
    def _tick(self,status):
        raw=ConversationStore(self.database,initialize=False)
        try:
            with raw.transaction():
                raw.db.execute('INSERT OR REPLACE INTO dashboard_worker_heartbeats VALUES (?,?)',
                    (self.identifier,encode({'worker_id':self.identifier,'updated_at':utcnow(),'status':status})))
        finally:raw.close()
    def __enter__(self):
        raw=ConversationStore(self.database,initialize=False)
        try:raw.db.execute('CREATE TABLE IF NOT EXISTS dashboard_worker_heartbeats(worker_id TEXT PRIMARY KEY,payload TEXT NOT NULL)');raw.db.commit()
        finally:raw.close()
        self._tick('RUNNING')
        def work():
            while not self.stop.wait(15):
                try:self._tick('RUNNING')
                except Exception:pass # A missed tick becomes STALE; it is never fabricated.
        self.thread=threading.Thread(target=work,daemon=True);self.thread.start();return self
    def __exit__(self,*args):
        self.stop.set();self.thread.join(timeout=2)
        self._tick('STOPPED')
