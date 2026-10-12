"""Local dashboard facade; one asynchronous classification cycle at a time."""
import threading
import time
from engine.classification_worker import classification_cycle,classification_rows,RUNTIME_TAXONOMY
from src.analysis.gemini_gateway import GeminiGateway
from src.analysis.taxonomy import load_snapshot,require_runtime_ready
from src.storage.conversations import ConversationStore


class ClassificationService:
    def __init__(self,database,taxonomy_dir=RUNTIME_TAXONOMY):
        self.database,self.taxonomy_dir=database,taxonomy_dir
        self.lock=threading.Lock();self.running=False;self.result=None
        self.view_lock=threading.Lock();self.view_cache=None;self.view_cached_at=0

    def status(self):
        with self.lock: return {'running':self.running,'result':self.result}

    def start(self):
        with self.lock:
            if self.running: return {'running':True,'already_running':True}
            self.running=True;self.result=None
        threading.Thread(target=self._run,daemon=True).start()
        return {'running':True}

    def _run(self):
        try:
            snapshot=load_snapshot(self.taxonomy_dir);require_runtime_ready(snapshot)
            raw=ConversationStore(self.database)
            try:
                from engine.worker_heartbeat import Heartbeat
                with Heartbeat(self.database):result=classification_cycle(raw,snapshot,GeminiGateway())
            finally: raw.close()
        except Exception: result={'status':'FAILED','error_code':'CLASSIFICATION_SERVICE_FAILED'}
        with self.lock: self.result=result;self.running=False

    def rows(self,refresh=False):
        with self.view_lock:
            if not refresh and self.view_cache is not None and time.monotonic()-self.view_cached_at<15:
                return self.view_cache
            rows=self._rows()
            self.view_cache=rows;self.view_cached_at=time.monotonic()
            return rows

    def _rows(self):
        snapshot=load_snapshot(self.taxonomy_dir)
        if not self.database.exists(): return []
        raw=ConversationStore(self.database,initialize=False)
        try: return classification_rows(raw,snapshot)
        finally:raw.close()
