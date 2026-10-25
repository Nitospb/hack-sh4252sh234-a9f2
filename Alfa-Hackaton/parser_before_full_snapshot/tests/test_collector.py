import json
from pathlib import Path
import tempfile
import time
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from news_collector.browser import AccessBlocked, Page, windows_identity
from news_collector.extract import ExtractionError, discover, extract_article, parse_date
from news_collector.models import Source, normalize_url, load_sources
from news_collector.storage import Store
from news_collector.runner import Collector


SOURCE = Source("example","Example",["https://news.example/economy"],["news.example"],r"^/article/\d+$","ru","RU",
                body_selectors=["//article//p"],min_text_chars=80)
BODY = "Компания сообщила о запуске нового завода. Производство начнётся в следующем году. Объём инвестиций составит пять миллиардов рублей."


def page(body=BODY,published="2026-10-24T12:00:00+03:00",paid=False):
    data = {"@type":"NewsArticle","headline":"Новый завод","datePublished":published,"isAccessibleForFree":not paid,
            "author":{"@type":"Person","name":"Автор"},"keywords":"промышленность,инвестиции"}
    markup = '<html lang="ru"><head><title>News</title><link rel="canonical" href="https://news.example/article/1?utm_source=feed">'
    markup += '<script type="application/ld+json">'+json.dumps(data,ensure_ascii=False)+'</script></head>'
    markup += '<body><nav>Меню сайта</nav><article><h1>Новый завод</h1><p>'+body+'</p></article><footer>Реклама</footer></body></html>'
    return Page("https://news.example/article/1","https://news.example/article/1","News",markup,body,200)


class ExtractionTests(unittest.TestCase):
    def test_article_keeps_provenance_and_strips_navigation(self):
        a = extract_article(page(),SOURCE,"raw/test.html.gz")
        self.assertEqual(a.title,"Новый завод")
        self.assertEqual(a.text,BODY)
        self.assertEqual(a.canonical_url,"https://news.example/article/1")
        self.assertEqual(a.published_at,"2026-10-24T09:00:00+00:00")
        self.assertEqual(a.authors,["Автор"])
        self.assertEqual(a.record()["kind"],"external_news")
        self.assertNotIn("Меню",a.text)

    def test_unknown_timezone_is_not_invented(self):
        a = extract_article(page(published="2026-10-24T12:00:00"),SOURCE,"raw/x")
        self.assertIsNone(a.published_at)
        self.assertEqual(a.publication_date_status,"timezone_missing")

    def test_paywall_is_marked_as_excerpt(self):
        self.assertEqual(extract_article(page(paid=True),SOURCE,"raw/x").text_scope,"accessible_excerpt")

    def test_short_error_page_is_not_an_article(self):
        with self.assertRaises(ExtractionError):
            extract_article(page(body="Нет доступа"),SOURCE,"raw/x")

    def test_nested_jsonld_graph(self):
        p = page()
        p.html = p.html.replace('"@type": "NewsArticle"','"@type": ["Article", "NewsArticle"]')
        self.assertEqual(extract_article(p,SOURCE,"raw/x").title,"Новый завод")

    def test_discovery_deduplicates_and_blocks_foreign_urls(self):
        p = page()
        p.html += '<a href="/article/2?utm_source=x">a</a><a href="/article/2">b</a><a href="https://elsewhere.example/article/3">c</a><a href="javascript:alert(1)">d</a>'
        self.assertEqual(discover(p,SOURCE),["https://news.example/article/2"])

    def test_url_normalization_keeps_meaningful_queries(self):
        self.assertEqual(normalize_url("https://NEWS.example/article/1?id=2&utm_campaign=a#section"),"https://news.example/article/1?id=2")
        for value in ("file:///etc/passwd","http://127.0.0.1/a","https://user:pass@example.com/a"):
            with self.assertRaises(ValueError):
                normalize_url(value)

    def test_ua_matches_real_chrome_version(self):
        identity = windows_identity("155.0.8059.85")
        self.assertIn("Chrome/155.0.0.0",identity["userAgent"])
        self.assertEqual(identity["userAgentMetadata"]["platform"],"Windows")
        self.assertNotIn("Linux",identity["userAgent"])

    def test_missing_and_invalid_dates(self):
        self.assertEqual(parse_date(None),(None,"missing"))
        self.assertEqual(parse_date("yesterday"),(None,"unparsed"))

    def test_itemprop_date_used_by_rbc(self):
        p = page(published=None)
        p.html = p.html.replace("</head>",'<meta itemprop="datePublished" content="2026-10-24T12:00:00+03:00"></head>')
        self.assertEqual(extract_article(p,SOURCE,"raw/x").published_at,"2026-10-24T09:00:00+00:00")


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.store = Store(self.path/"news.db")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_restart_and_exactly_one_claim(self):
        self.assertEqual(self.store.enqueue("example",["https://news.example/article/1"]*2),1)
        task = self.store.claim("example")
        second = Store(self.path/"news.db")
        try:
            self.assertIsNone(second.claim("example"))
        finally:
            second.close()
        self.store.close()
        self.store = Store(self.path/"news.db")
        self.assertIsNone(self.store.claim("example"))
        with self.store.db:
            self.store.db.execute("UPDATE frontier SET lease_until=0")
        self.assertEqual(self.store.claim("example")["attempts"],2)

    def test_saved_article_and_revisions_are_idempotent(self):
        self.store.enqueue("example",["https://news.example/article/1"])
        task = self.store.claim("example")
        a = extract_article(page(),SOURCE,"raw/x")
        self.assertTrue(self.store.complete(task,a))
        self.assertFalse(self.store.complete(task,a))
        self.assertEqual(self.store.stats()["revisions"],1)
        a.text += " Дополнение."
        self.assertFalse(self.store.complete(task,a))
        self.assertEqual(self.store.stats()["articles"],1)
        self.assertEqual(self.store.stats()["revisions"],2)
        self.assertIsNone(self.store.claim("example"))

    def test_failure_backoff_and_blocked_tasks(self):
        self.store.enqueue("example",["https://news.example/article/1"])
        task = self.store.claim("example")
        self.store.fail("example",task,"timeout")
        self.assertIsNone(self.store.claim("example"))
        row = self.store.db.execute("SELECT state,next_attempt FROM frontier").fetchone()
        self.assertEqual(row["state"],"retry")
        self.assertGreater(row["next_attempt"],time.time())
        self.store.fail("example",task,"challenge",blocked=True)
        self.assertEqual(self.store.db.execute("SELECT state FROM frontier").fetchone()[0],"blocked")

    def test_export_preserves_unicode_and_schema(self):
        self.store.enqueue("example",["https://news.example/article/1"])
        self.store.complete(self.store.claim("example"),extract_article(page(),SOURCE,"raw/x"))
        output = self.path/"articles.jsonl"
        self.assertEqual(self.store.export(output),1)
        data = json.loads(output.read_text())
        self.assertEqual(data["title"],"Новый завод")
        self.assertEqual(data["schema_version"],1)
        self.assertIn("first_seen_at",data)


class RunnerTests(unittest.TestCase):
    def test_blocked_source_does_not_stop_other_worker(self):
        class FakeBrowser:
            identity = {"userAgent":"Chrome/155.0.0.0"}
            def __init__(self,*_,**__): pass
            def __enter__(self): return self
            def __exit__(self,*_): pass
            def diagnostic(self,*_): pass
            def read(self,url,article=False,**_):
                if url.endswith("/robots.txt"):
                    return Page(url,url,"","<html><pre>User-agent: *\nAllow: /</pre></html>","User-agent: *\nAllow: /",200)
                if article:
                    if "bad.example" in url:
                        raise AccessBlocked("Synthetic access challenge")
                    result = page(published=datetime.now(timezone.utc).isoformat())
                    result.requested_url=result.url=url
                    result.html=result.html.replace("news.example","good.example")
                    return result
                return Page(url,url,"Listing",'<html><body><a href="/article/1">News</a></body></html>',"News",200)
        class FastCollector(Collector):
            def paced_read(self,browser,store,source,url,article=False,check_access=True):
                return browser.read(url,article=article,check_access=check_access)
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            Store(runtime/"news.sqlite3").close()
            sources = [Source(name,name,[f"https://{name}.example/economy"],[f"{name}.example"],r"^/article/\d+$","ru","RU",body_selectors=["//article//p"],min_text_chars=80) for name in ("bad","good")]
            with patch("news_collector.runner.Browser",FakeBrowser):
                results = FastCollector(runtime).cycle(sources,workers=2,max_articles=1)
            indexed = {r["source_id"]:r for r in results}
            self.assertEqual(indexed["bad"]["blocked"],1)
            self.assertEqual(indexed["good"]["saved"],1)
            store = Store(runtime/"news.sqlite3")
            try:
                self.assertGreater(store.state("bad")["cooldown_until"],time.time())
                self.assertEqual(store.stats()["articles"],1)
                self.assertEqual(store.db.execute("SELECT state FROM frontier WHERE source_id='bad'").fetchone()[0],"blocked")
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
