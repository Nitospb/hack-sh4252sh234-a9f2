import json
from pathlib import Path
import sqlite3
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
import tempfile
import unittest
from pipeline.publication import publish
from recommendations.engine import Feed
from recommendations.snapshots import Snapshots
from service.seed import create
from recommendations.server import handler
from service.runtime import Runtime


class PublicationTests(unittest.TestCase):
    def test_switch_pins_requests_and_preserves_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=create(root/'old');new=create(root/'new')
            with sqlite3.connect(new) as db:
                db.execute("UPDATE articles SET title='Updated event' WHERE article_id='seed_article_0'")
            initial=Feed(old,root/'state.sqlite',embeddings=False)
            initial.event('SEED_1','user','seed_article_0','save','event-1')
            snapshots=Snapshots(initial,root/'releases',embeddings=False)
            first=publish(old.parent,root/'releases',allow_synthetic=True)
            pinned=snapshots.current()
            second=publish(new.parent,root/'releases',allow_synthetic=True)
            active=snapshots.current()
            self.assertNotEqual(first['version'],second['version'])
            with pinned.source() as db:self.assertNotEqual(db.execute('SELECT title FROM articles LIMIT 1').fetchone()[0],'Updated event')
            with active.source() as db:self.assertEqual(db.execute('SELECT title FROM articles LIMIT 1').fetchone()[0],'Updated event')
            with active.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0],1)
            self.assertIs(snapshots.current(),active)
            self.assertEqual(publish(new.parent,root/'releases',allow_synthetic=True)['version'],second['version'])
            # A failed build must not move the serving pointer.
            (root/'new/article_chunks.jsonl').write_text('{}\n')
            with self.assertRaises(ValueError):publish(new.parent,root/'releases',allow_synthetic=True)
            self.assertEqual(json.loads((root/'releases/current.json').read_text())['version'],second['version'])

    def test_corrupt_or_unsafe_release_retains_last_healthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=create(root/'old');new=create(root/'new')
            initial=Feed(old,root/'state.sqlite',embeddings=False)
            snapshots=Snapshots(initial,root/'releases',embeddings=False)
            manifest=publish(new.parent,root/'releases',allow_synthetic=True)
            (root/'releases'/manifest['version']/'report.json').write_text('{}')
            self.assertIs(snapshots.current(),initial)
            self.assertEqual(snapshots.status()['reload_error'],'ValueError')
            (root/'releases/current.json').write_text('{"version":"../../escape"}')
            self.assertIs(snapshots.current(),initial)
            self.assertEqual(snapshots.status()['reload_error'],'ValueError')

    def test_synthetic_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);catalog=create(root/'seed')
            with self.assertRaises(ValueError):publish(catalog.parent,root/'releases')
            self.assertFalse((root/'releases/current.json').exists())

    def test_http_reload_uses_new_catalog_without_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=create(root/'old');new=create(root/'new')
            with sqlite3.connect(new) as db:
                db.execute("UPDATE articles SET title='New HTTP event' WHERE article_id='seed_article_0'")
            feed=Feed(old,root/'feedback.sqlite',embeddings=False)
            snapshots=Snapshots(feed,root/'releases',embeddings=False)
            runtime=Runtime(feed,assets=old.parent/'service-assets.sqlite',state=root/'service.sqlite')
            server=ThreadingHTTPServer(('127.0.0.1',0),handler(feed,runtime,snapshots=snapshots))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            def get(path):
                with urlopen(base+path) as response:return json.load(response)
            try:
                before=get('/article?article_id=seed_article_0')
                version=publish(new.parent,root/'releases',allow_synthetic=True)['version']
                after=get('/article?article_id=seed_article_0')
                self.assertNotEqual(before['title'],after['title'])
                self.assertEqual(after['title'],'New HTTP event')
                self.assertEqual(get('/health')['catalog_publication']['serving_version'],version)
            finally:
                server.shutdown();server.server_close();thread.join();runtime.pool.shutdown(wait=True)

    def test_publication_cannot_silently_drop_existing_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=create(root/'old');new=create(root/'new')
            first=publish(old.parent,root/'releases',allow_synthetic=True)
            with sqlite3.connect(new) as db:db.execute("DELETE FROM articles WHERE article_id='seed_article_0'")
            with self.assertRaisesRegex(ValueError,'drop existing articles'):
                publish(new.parent,root/'releases',allow_synthetic=True)
            self.assertEqual(json.loads((root/'releases/current.json').read_text())['version'],first['version'])

    def test_retention_keeps_inflight_generation_and_current(self):
        from pipeline.publication import prune
        import gc
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);catalog=create(root/'candidate')
            feed=Feed(catalog,root/'feedback.sqlite',embeddings=False)
            manager=Snapshots(feed,root/'releases',embeddings=False)
            first=publish(catalog.parent,root/'releases',allow_synthetic=True)
            pinned=manager.current()
            for i in range(3):
                with sqlite3.connect(catalog) as db:
                    db.execute('UPDATE articles SET title=? WHERE article_id=?',(f'update {i}','seed_article_0'))
                latest=publish(catalog.parent,root/'releases',allow_synthetic=True)
                manager.current()
            self.assertNotIn(first['version'],prune(root/'releases',keep=2))
            self.assertTrue((root/'releases'/first['version']).is_dir())
            del pinned;gc.collect()
            self.assertIn(first['version'],prune(root/'releases',keep=2))
            self.assertTrue((root/'releases'/latest['version']).is_dir())
