from dataclasses import replace
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from news_collector.browser import AccessBlocked, Browser, Page
from news_collector.extract import extract_article
from news_collector.history import (History, Window, archive_seeds, enqueue_page, job_window,
                                    page_priority, pagination_urls, prepare, sitemap_entries,
                                    timestamp, write_history_report)
from news_collector.runner import Collector
from news_collector.storage import Store
from news_collector.source_check import source_fingerprint
from test_collector import SOURCE, page


WINDOW = Window(timestamp("2026-09-24"), timestamp("2026-10-25"))


class HistoryTests(unittest.TestCase):
    def test_interval_is_half_open_and_requires_aware_timestamps(self):
        self.assertTrue(WINDOW.contains("2026-09-24T03:00:00+03:00"))
        self.assertFalse(WINDOW.contains("2026-10-25T00:00:00Z"))
        self.assertFalse(WINDOW.contains(None))
        self.assertFalse(WINDOW.contains("2026-10-01T12:00:00"))
        with self.assertRaises(ValueError):
            Window(WINDOW.end, WINDOW.start)

    def test_resume_freezes_relative_window_and_rejects_different_job(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            first = job_window(runtime, days=30)
            self.assertEqual(job_window(runtime, days=30), first)
            self.assertEqual(job_window(runtime), first)
            with self.assertRaises(ValueError):
                job_window(runtime, days=14)
            with self.assertRaises(ValueError):
                job_window(runtime, since="2000-01-01")
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            store = Store(runtime / "news.sqlite3")
            store.enqueue(SOURCE.id, [page().url])
            store.close()
            with self.assertRaisesRegex(ValueError, "fresh runtime"):
                job_window(runtime, days=30)

    def test_sitemap_index_gzip_and_news_publication_are_distinct_from_lastmod(self):
        data = b'''<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
          xmlns:n="http://www.google.com/schemas/sitemap-news/0.9"><url>
          <loc>https://news.example/article/1?a=1&amp;b=2</loc><lastmod>2026-10-24</lastmod>
          <n:news><n:publication_date>2026-09-25T12:00:00Z</n:publication_date></n:news>
          </url></urlset>'''
        kind, entries = sitemap_entries(gzip.compress(data))
        self.assertEqual(kind, "urlset")
        self.assertEqual(entries, [("https://news.example/article/1?a=1&b=2", "2026-09-25T12:00:00Z", "2026-10-24")])
        kind, entries = sitemap_entries(b'<sitemapindex><sitemap><loc>https://news.example/sitemap-2026-10.xml</loc></sitemap></sitemapindex>')
        self.assertEqual(kind, "sitemapindex")
        self.assertEqual(len(entries), 1)
        self.assertGreater(page_priority(entries[0][0], WINDOW), page_priority("https://news.example/sitemap-2019-10.xml", WINDOW))
        with self.assertRaises(ValueError):
            sitemap_entries(b'<html><body>Challenge</body></html>')

    def test_sitemap_does_not_resolve_external_entities(self):
        data = b'<!DOCTYPE urlset [<!ENTITY leak SYSTEM "file:///etc/passwd">]><urlset><url><loc>&leak;</loc></url></urlset>'
        self.assertEqual(sitemap_entries(data)[1], [])

    def test_reverse_index_starts_at_end_when_lastmod_is_equal(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "news.sqlite3")
            prepare(store)
            collector = Collector(Path(folder))
            collector.robots = lambda *_: True
            history = History(collector, WINDOW)
            history.read_map = lambda *_: ("sitemapindex", [
                ("https://news.example/map-old.xml", None, "2026-10-24"),
                ("https://news.example/map-new.xml", None, "2026-10-24")])
            source = replace(SOURCE, sitemap_reverse=True)
            history.discover_page(object(), store, source, {"url": "https://news.example/sitemap.xml", "kind": "sitemap"}, {})
            rows = store.db.execute("SELECT url FROM history_pages ORDER BY priority DESC,rowid").fetchall()
            self.assertEqual(rows[0][0], "https://news.example/map-new.xml")
            self.assertGreater(page_priority("https://news.example/sitemap.xml?page=daily", WINDOW), page_priority("https://news.example/sitemap.xml?page=0", WINDOW))
            store.close()

    def test_url_date_hints_schedule_but_never_become_publication_dates(self):
        from news_collector.history import article_priority
        from news_collector.extract import url_publication_day
        url = "https://news.example/politics/24/10/2026/story"
        self.assertEqual(str(url_publication_day(url)), "2026-10-24")
        self.assertGreater(article_priority(url, WINDOW), article_priority("https://news.example/politics/24/10/2005/story", WINDOW))
        self.assertGreater(article_priority("https://news.example/article/1", WINDOW, "2026-10-01"), 0)
        self.assertIsNone(extract_article(page(published=None), SOURCE, "raw/x").published_at)

    def test_no_browser_is_started_for_queued_work_after_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            collector = Collector(Path(folder))
            collector.stop.set()
            with patch("news_collector.history.Browser", side_effect=AssertionError("should not start")):
                result = History(collector, WINDOW).source_turn(SOURCE)
            self.assertEqual(result["status"], "interrupted")
            self.assertFalse((Path(folder) / "news.sqlite3").exists())

    def test_archive_templates_and_pagination_stay_in_source_scope(self):
        source = replace(SOURCE, archive_seeds=["https://news.example/archive/{year}/{month}/{day}/"])
        seeds = archive_seeds(source, Window(timestamp("2026-10-01"), timestamp("2026-10-02")))
        self.assertIn("https://news.example/archive/2026/09/30/", seeds)
        p = Page(source.seeds[0], source.seeds[0], "", '''<div class="pagination">
          <a href="/economy?page=2">2</a><a href="https://foreign.example/economy?page=3">3</a>
          <a href="/sports?page=4">4</a></div><a href="/article/99">99</a>''', "", 200)
        self.assertEqual(pagination_urls(p, source, source.seeds[0]), ["https://news.example/economy?page=2"])

    def test_training_export_excludes_undated_excerpts_outside_and_exact_duplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            store = Store(runtime / "news.sqlite3")
            prepare(store)
            variants = [page(published="2026-09-25T12:00:00Z"), page(published=None),
                        page(published="2026-10-01T12:00:00Z", paid=True),
                        page(published="2020-01-01T12:00:00Z"), page(published="2026-10-23T12:00:00Z")]
            for index, p in enumerate(variants):
                a = extract_article(p, SOURCE, "raw/x")
                a.canonical_url = f"https://news.example/article/{index}"
                store.complete({"url": a.canonical_url}, a)
            report = write_history_report(store, runtime, WINDOW, [SOURCE], target=2)
            self.assertEqual(report["period_articles"], 3)
            self.assertEqual(report["undated_articles"], 1)
            self.assertEqual(report["accessible_excerpts"], 1)
            self.assertEqual(report["duplicate_texts"], 1)
            self.assertEqual(report["training_articles"], 1)
            self.assertFalse(report["target_reached"])
            self.assertEqual(len((runtime / "training-news.jsonl").read_text().splitlines()), 1)
            self.assertEqual(len((runtime / "period-news.jsonl").read_text().splitlines()), 3)
            store.close()

    def test_history_ignores_realtime_age_limit_and_resumes_without_refetch(self):
        class FakeBrowser:
            identity = {"userAgent": "Chrome"}
            reads = []
            def __init__(self, *_, **__): pass
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def resource_bytes(self, url, _):
                return b'<urlset><url><loc>https://news.example/article/1</loc><lastmod>2026-10-24</lastmod></url></urlset>'
            def read(self, url, article=False, **_):
                self.reads.append(url)
                if url.endswith('/robots.txt'):
                    return Page(url, url, "", "<pre>User-agent: *\nAllow: /\nSitemap: https://news.example/sitemap.xml</pre>",
                                "User-agent: *\nAllow: /\nSitemap: https://news.example/sitemap.xml", 200)
                if article:
                    return page(published="2026-09-25T12:00:00Z")
                return Page(url, url, "", '<a href="/article/1">News</a>', "", 200)
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            store = Store(runtime / "news.sqlite3")
            prepare(store)
            store.close()
            collector = Collector(runtime)
            collector.paced_read = lambda browser, store, source, url, **kwargs: browser.read(url, **kwargs)
            history = History(collector, WINDOW, defer_images=True)
            with patch("news_collector.history.Browser", FakeBrowser), patch.object(history, "read_map", lambda b,s,src,url: sitemap_entries(b.resource_bytes(url, 10000))):
                first = history.source_turn(SOURCE)
                self.assertEqual(first["new"], 1)
                count = FakeBrowser.reads.count(page().url)
                second = history.source_turn(SOURCE)
                self.assertEqual(second["attempted"], 0)
                self.assertEqual(FakeBrowser.reads.count(page().url), count)
            store = Store(runtime / "news.sqlite3")
            self.assertFalse(history.eligible(store, SOURCE))
            self.assertEqual(write_history_report(store, runtime, WINDOW, [SOURCE])["period_articles"], 1)
            store.close()

    def test_text_survives_image_failure_and_undated_is_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            store = Store(runtime / "news.sqlite3")
            prepare(store)
            collector = Collector(runtime)
            collector.robots = lambda *_: True
            collector.paced_read = lambda *_args, **_kwargs: page(published=None)
            history = History(collector, WINDOW)
            store.enqueue(SOURCE.id, [page().url])
            task = store.claim(SOURCE.id)
            with patch("news_collector.history.download_images", side_effect=RuntimeError("broken CDN")):
                self.assertEqual(history.article(object(), store, SOURCE, task, {}), "new")
            record = json.loads(store.db.execute("SELECT record FROM articles").fetchone()[0])
            self.assertIn("history_period_unverified", record["quality_flags"])
            self.assertEqual(store.db.execute("SELECT state FROM frontier").fetchone()[0], "done")
            store.close()

    def test_disallowed_discovery_does_not_make_resource_request(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "news.sqlite3")
            prepare(store)
            enqueue_page(store, SOURCE, "http://127.0.0.1/sitemap.xml", "sitemap")
            enqueue_page(store, SOURCE, "https://foreign.example/sitemap.xml", "sitemap")
            self.assertEqual(store.db.execute("SELECT count(*) FROM history_pages").fetchone()[0], 0)
            collector = Collector(Path(folder))
            collector.robots = lambda *_: False
            result = History(collector, WINDOW).discover_page(object(), store, SOURCE, {"url": "https://news.example/sitemap.xml", "kind": "sitemap"}, {})
            self.assertEqual(result, "robots_disallowed")
            store.close()

    def test_waiting_retry_does_not_reopen_browser_before_due_time(self):
        import time
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "news.sqlite3")
            prepare(store)
            store.db.execute("INSERT INTO history_sources(source_id,initialized,status,fingerprint) VALUES (?,1,'processed',?)", (SOURCE.id,source_fingerprint(SOURCE)))
            store.db.commit()
            store.enqueue(SOURCE.id, [page().url])
            with store.db:
                store.db.execute("UPDATE frontier SET state='retry',next_attempt=?", (time.time() + 3600,))
            history = History(Collector(Path(folder)), WINDOW)
            self.assertTrue(history.eligible(store, SOURCE))
            self.assertFalse(history.ready(store, SOURCE))
            with store.db:
                store.db.execute("UPDATE frontier SET next_attempt=0")
            self.assertTrue(history.ready(store, SOURCE))
            with store.db:
                store.db.execute("UPDATE history_sources SET status='blocked'")
            self.assertFalse(history.eligible(store, SOURCE))
            store.close()

    def test_prepare_is_additive_and_budgets_are_cumulative(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "news.sqlite3")
            store.complete({"url": page().url}, extract_article(page(), SOURCE, "raw/x"))
            prepare(store)
            prepare(store)
            self.assertEqual(store.stats()["articles"], 1)
            store.db.execute("INSERT INTO history_sources(source_id,initialized,status,fingerprint) VALUES (?,1,'processed',?)", (SOURCE.id,source_fingerprint(SOURCE)))
            store.db.commit()
            enqueue_page(store, SOURCE, "https://news.example/sitemap.xml", "sitemap")
            store.db.execute("UPDATE history_pages SET state='done'")
            store.db.commit()
            enqueue_page(store, SOURCE, "https://news.example/sitemap2.xml", "sitemap")
            history = History(Collector(Path(folder)), WINDOW, max_pages=1)
            self.assertFalse(history.eligible(store, SOURCE))
            history.max_pages = 2
            self.assertTrue(history.eligible(store, SOURCE))
            store.close()

    def test_old_history_schema_migrates_without_losing_queue(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "news.sqlite3")
            store.db.executescript('''
              CREATE TABLE history_sources(source_id TEXT PRIMARY KEY,initialized INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',last_error TEXT,updated_at TEXT);
              CREATE TABLE history_pages(source_id TEXT,url TEXT,kind TEXT,seed TEXT,priority INTEGER DEFAULT 0,
                state TEXT DEFAULT 'pending',attempts INTEGER DEFAULT 0,next_attempt REAL DEFAULT 0,last_error TEXT,
                PRIMARY KEY(source_id,url));
              INSERT INTO history_sources(source_id,initialized,status) VALUES ('example',1,'processed');
              INSERT INTO history_pages(source_id,url,kind,seed,state) VALUES ('example','https://news.example/sitemap.xml','sitemap','https://news.example/sitemap.xml','done');
            ''')
            prepare(store)
            self.assertIsNone(store.db.execute("SELECT fingerprint FROM history_sources").fetchone()[0])
            self.assertEqual(tuple(store.db.execute("SELECT state,position FROM history_pages").fetchone()), ("done", 0))
            store.close()

    def test_changed_archive_configuration_rediscovers_roots_but_preserves_articles(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "news.sqlite3")
            prepare(store)
            store.enqueue(SOURCE.id, [page().url])
            store.complete({"url": page().url}, extract_article(page(), SOURCE, "raw/x"))
            enqueue_page(store, SOURCE, "https://news.example/sitemap.xml", "sitemap")
            with store.db:
                store.db.execute("UPDATE history_pages SET state='done'")
                store.db.execute("INSERT INTO history_sources(source_id,initialized,status,fingerprint) VALUES (?,1,'processed',?)", (SOURCE.id,source_fingerprint(SOURCE)))
            collector = Collector(Path(folder))
            collector.robots = lambda *_: True
            class Robot:
                def site_maps(self): return ["https://news.example/sitemap.xml"]
            changed = replace(SOURCE, sitemap_reverse=True)
            history = History(collector, WINDOW)
            self.assertTrue(history.eligible(store, changed))
            history.initialize(object(), store, changed, {"https://news.example": Robot()})
            self.assertEqual(store.db.execute("SELECT state FROM history_pages WHERE kind='sitemap'").fetchone()[0], "pending")
            self.assertEqual(store.db.execute("SELECT state FROM frontier").fetchone()[0], "done")
            self.assertEqual(store.stats()["articles"], 1)
            self.assertEqual(store.db.execute("SELECT fingerprint FROM history_sources").fetchone()[0], source_fingerprint(changed))
            store.close()

    def test_resource_stream_closes_on_limit_and_access_failures(self):
        class Driver:
            closed = False
            def execute_cdp_cmd(self, method, params):
                if method == "Page.getFrameTree": return {"frameTree": {"frame": {"id": "frame"}}}
                if method == "Network.loadNetworkResource": return {"resource": {"success": True, "stream": "stream", "httpStatusCode": 200}}
                if method == "IO.read": return {"data": "oversized", "eof": True}
                if method == "IO.close": self.closed = True
        browser = Browser.__new__(Browser)
        browser.driver = Driver()
        with self.assertRaises(ValueError):
            browser.resource_bytes("https://news.example/sitemap.xml", 2)
        self.assertTrue(browser.driver.closed)

        class RestrictedDriver(Driver):
            def execute_cdp_cmd(self, method, params):
                if method == "Network.loadNetworkResource":
                    return {"resource": {"success": False, "stream": "restricted", "httpStatusCode": 403}}
                return super().execute_cdp_cmd(method, params)
        browser.driver = RestrictedDriver()
        with self.assertRaises(AccessBlocked):
            browser.resource_bytes("https://news.example/sitemap.xml", 100)
        self.assertTrue(browser.driver.closed)


if __name__ == "__main__":
    unittest.main()
