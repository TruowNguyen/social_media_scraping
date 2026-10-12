from datetime import date
from pathlib import Path
import tempfile
import unittest
from engine.conversation_schedule import CrawlTasks,daily_ticks
from src.domain.conversation import ContentNode
from src.storage.conversations import ConversationStore


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.raw=ConversationStore(Path(self.tmp.name)/'raw.sqlite3')
        self.tasks=CrawlTasks(self.raw)

    def tearDown(self):
        self.raw.close(); self.tmp.cleanup()

    def test_ticks_final_and_opening_inventory(self):
        ticks=list(daily_ticks(date(2026,10,8)))
        self.assertEqual([tick.strftime('%H:%M') for _,tick,_ in ticks],
            ['05:00','05:45','06:30','07:15','08:00','08:30','17:00','17:45','18:30'])
        self.assertEqual([t.strftime('%H:%M') for _,t,final in ticks if final],['08:30','18:30'])
        self.tasks.enqueue_days(['group'],date(2026,10,8),date(2026,10,8),'2026-10-08T00:00:00Z')
        task=self.tasks.claim('2026-10-08T00:00:00Z')
        self.assertTrue(task['inventory_only'])

    def test_restart_idempotent_final_is_queued_while_earlier_job_busy(self):
        day=date(2026,10,8)
        now='2026-10-08T11:30:00Z'
        self.assertEqual(self.tasks.enqueue_days(['group'],day,day,now),9)
        self.assertEqual(self.tasks.enqueue_days(['group'],day,day,now),0)
        active=self.tasks.claim(now)
        self.assertIsNotNone(active)
        self.assertEqual(self.raw.db.execute("SELECT count(*) FROM conversation_tasks WHERE status='PENDING'").fetchone()[0],8)
        self.assertEqual(self.raw.db.execute("SELECT count(*) FROM conversation_tasks WHERE json_extract(payload,'$.final_tick')=1").fetchone()[0],2)

    def test_expired_lease_reclaimed_old_worker_cannot_finish(self):
        day=date(2026,10,8)
        now='2026-10-07T22:00:00Z'
        self.tasks.enqueue_days(['group'],day,day,now)
        first=self.tasks.claim(now,lease_seconds=1)
        second=self.tasks.claim('2026-10-07T22:00:02Z',lease_seconds=10)
        self.assertEqual(first['task_id'],second['task_id'])
        self.assertNotEqual(first['lease_token'],second['lease_token'])
        with self.assertRaises(ValueError): self.tasks.finish(first,{},'2026-10-07T22:00:03Z')
        self.tasks.finish(second,{},'2026-10-07T22:00:03Z')
        self.assertIsNone(self.tasks.claim('2026-10-07T22:00:04Z'))

    def test_fair_inventory_never_cuts_off_old_parent(self):
        ids=[]
        for native in ('111','222'):
            url='https://www.facebook.com/groups/123/posts/'+native
            node=self.raw.ingest(ContentNode('POST',platform_item_id=native,canonical_url=url,
                published_at='2020-01-01T00:00:00Z',publication_precision='INSTANT'),'group','run')['node_id']
            self.tasks.add_post('group',node,url); ids.append(node)
        first=self.tasks.fair_posts('group',1)[0]
        self.tasks.scanned('group',first['node_id'],{'status':'PARTIAL'},'2026-10-08T00:00:00Z')
        second=self.tasks.fair_posts('group',1)[0]
        self.assertNotEqual(first['node_id'],second['node_id'])
        self.assertEqual(len(self.tasks.fair_posts('group')),2)

    def test_exhausted_crash_retries_mark_failed(self):
        day=date(2026,10,8)
        self.tasks.enqueue_days(['group'],day,day,'2026-10-07T22:00:00Z')
        self.tasks.claim('2026-10-07T22:00:00Z',lease_seconds=1,max_attempts=1)
        self.assertIsNone(self.tasks.claim('2026-10-07T22:00:02Z',max_attempts=1))
        self.assertEqual(self.raw.db.execute('SELECT status FROM conversation_tasks').fetchone()[0],'FAILED')

    def test_profile_busy_preserves_final_task_and_waits_before_retry(self):
        day=date(2026,10,8)
        now='2026-10-07T22:00:00Z'
        self.tasks.enqueue_days(['group'],day,day,now)
        task=self.tasks.claim(now)
        self.tasks.finish(task,{'status':'SKIPPED','error_code':'PROFILE_IN_USE'},now)
        self.assertIsNone(self.tasks.claim('2026-10-07T22:00:20Z'))
        retried=self.tasks.claim('2026-10-07T22:00:31Z')
        self.assertEqual(retried['task_id'],task['task_id'])
        self.assertEqual(retried['attempt'],1)
