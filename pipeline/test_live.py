import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from pipeline.live import prepare_runtime,freeze_news,lock,arguments


class LiveStagingTests(unittest.TestCase):
    def test_old_queues_are_rejected_and_online_restarts_preserve_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'history-job.json').write_text('{}')
            with self.assertRaises(ValueError):prepare_runtime(root)
            (root/'history-job.json').unlink()
            with sqlite3.connect(root/'news.sqlite3') as db:db.execute('CREATE TABLE articles(id TEXT, record TEXT)')
            with self.assertRaises(ValueError):prepare_runtime(root)
            (root/'news.sqlite3').unlink();prepare_runtime(root)
            with sqlite3.connect(root/'news.sqlite3') as db:
                db.executescript('CREATE TABLE articles(id TEXT,record TEXT); CREATE TABLE source_state(source_id TEXT,cooldown_until REAL);')
                db.execute('INSERT INTO articles VALUES(?,?)',('a',json.dumps({'id':'a','text':'news','published_at':None,'fetched_at':'first'})))
                db.execute('INSERT INTO source_state VALUES(?,?)',('source',123))
            prepare_runtime(root)
            frozen,first,count,sources=freeze_news(root)
            self.assertEqual(count,1);self.assertEqual(sources[0]['cooldown_until'],123)
            with sqlite3.connect(root/'news.sqlite3') as db:
                db.execute('UPDATE articles SET record=?',(json.dumps({'id':'a','text':'news','published_at':None,'fetched_at':'second'}),))
            self.assertEqual(freeze_news(root)[1],first)
            with sqlite3.connect(root/'news.sqlite3') as db:
                db.execute('UPDATE articles SET record=?',(json.dumps({'id':'a','text':'news','published_at':'2026-10-26T00:00:00Z'}),))
            self.assertNotEqual(freeze_news(root)[1],first)
            with sqlite3.connect(frozen) as db:self.assertEqual(db.execute('SELECT count(*) FROM articles').fetchone()[0],1)

    def test_duplicate_worker_and_invalid_budget_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'worker.lock'
            with lock(path):
                with self.assertRaises(BlockingIOError):
                    with lock(path):pass
            with self.assertRaises(SystemExit):arguments(['--runtime',tmp,'--sources','rbc','--interval','1'])
