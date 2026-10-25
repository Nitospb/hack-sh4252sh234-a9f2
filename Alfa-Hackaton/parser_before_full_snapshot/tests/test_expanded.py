from dataclasses import replace
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from news_collector.browser import Page, PageError
from news_collector.extract import discover, extract_article, listing_next, url_publication_day
from news_collector.models import Source, load_sources
from news_collector.report import coverage, write_report
from news_collector.runner import Collector
from news_collector.storage import Store
from news_collector.topics import classify

from test_collector import SOURCE, page


class ExpandedTests(unittest.TestCase):
    def test_complete_catalog_loads_and_domains_have_one_owner(self):
        # Includes disabled adapters; they must remain runnable explicitly.
        path = Path("config/sources.json")
        rows = json.loads(path.read_text())["sources"]
        candidates = Path("config/source-candidates.json")
        if candidates.exists():
            rows += json.loads(candidates.read_text())["sources"]
        with tempfile.TemporaryDirectory() as directory:
            combined=Path(directory)/"sources.json"
            combined.write_text(json.dumps({"sources":rows}))
            self.assertGreaterEqual(len(load_sources(combined,[s["id"] for s in rows])),40)

    def test_financial_sources_run_first_and_technology_has_smaller_budget(self):
        sources = load_sources(Path("config/sources.json"))
        self.assertEqual(sources[0].collection_priority,100)
        candidate_path=Path("config/source-candidates.json")
        if candidate_path.exists():
            candidate_ids=[s["id"] for s in json.loads(candidate_path.read_text())["sources"]]
            sources += load_sources(candidate_path,candidate_ids)
        by = {s.id:s for s in sources}
        self.assertGreater(by["interfax"].max_articles_per_cycle,by["techcrunch"].max_articles_per_cycle)
        self.assertGreater(by["rbc"].collection_priority,by["anthropic"].collection_priority)
        self.assertGreater(by["rbc"].collection_priority,by["cnbc"].collection_priority)
        self.assertGreater(by["rbc"].max_articles_per_cycle,by["cnbc"].max_articles_per_cycle)

    def test_rbc_includes_requested_politics_but_excludes_sport(self):
        source = load_sources(Path("config/sources.json"),["rbc"])[0]
        slug = "/24/10/2026/"+"a"*24
        self.assertFalse(source.accepts("https://www.rbc.ru/sport"+slug))
        self.assertTrue(source.accepts("https://www.rbc.ru/politics"+slug))
        self.assertTrue(source.accepts("https://www.rbc.ru/business"+slug))

    def test_financial_headlines_outrank_generic_sidebar_news_before_limit(self):
        source = replace(SOURCE,collection_priority=100)
        p = page()
        p.html += '<a href="/article/2">Обмен пленными</a><a href="/article/3">Банк повысил ставки по облигациям</a>'
        self.assertEqual(discover(p,source,limit=1),["https://news.example/article/3"])

    def test_topic_hints_multilingual_and_do_not_invent_relevance(self):
        for title in ("OpenAI raises startup funding", "Нейросеть для бизнеса", "人工智能公司融资"):
            topics, score = classify(title,None,"")
            self.assertIn("ai",topics)
            self.assertGreater(score,0)
        self.assertEqual(classify("Победа фигуристки",None,"Медаль чемпионата"),([],0))

    def test_political_source_ranks_its_topic_before_unrelated_links(self):
        source = replace(SOURCE,collection_priority=95,topics=["politics"])
        p = page()
        p.html = '<a href="/article/1">Рецепт пирога</a><a href="/article/2">Парламент обсуждает законопроект</a>'
        self.assertEqual(discover(p,source,limit=1),["https://news.example/article/2"])
        for headline in ("Президент объявил выборы", "Parliament election results", "政府外交", "Bundestag Regierung"):
            self.assertIn("politics",classify(headline,None,"")[0])

    def test_european_financial_topic_hints(self):
        for headline in ("Banque et marchés", "Aktien und Börse", "Banca e credito", "Mercados e inversión", "Giełda i kredyty"):
            self.assertIn("finance",classify(headline,None,"")[0])
        for headline in ("Économie française", "Wirtschaft und Konjunktur", "Gospodarka i inflacja"):
            self.assertIn("economy",classify(headline,None,"")[0])

    def test_only_explicit_pagination_inside_listing(self):
        source = replace(SOURCE,seeds=["https://news.example/economy"])
        p = Page(source.seeds[0],source.seeds[0],"",'<a rel="next" href="/economy?page=2">Next</a>',"",200)
        self.assertEqual(listing_next(p,source,source.seeds[0]),"https://news.example/economy?page=2")
        for href in ("https://evil.example/economy?page=2","/sports?page=2","/article/2"):
            p.html = f'<a rel="next" href="{href}">Next</a>'
            self.assertIsNone(listing_next(p,source,source.seeds[0]))

    def test_discovery_respects_document_base_without_accepting_foreign_hosts(self):
        p=Page('https://news.example/news/','https://news.example/news/','',
               '<base href="https://news.example/"><a href="article/2">Парламент</a>',"",200)
        self.assertEqual(discover(p,SOURCE),['https://news.example/article/2'])
        p.html=p.html.replace('https://news.example/','https://foreign.example/')
        self.assertEqual(discover(p,SOURCE),[])

    def test_query_id_required_for_query_based_article_routes(self):
        source = replace(SOURCE,article_pattern=r"^/press/event/$",article_query_pattern=r"(?:^|&)id=\d+(?:&|$)")
        self.assertTrue(source.accepts("https://news.example/press/event/?id=123"))
        self.assertFalse(source.accepts("https://news.example/press/event/"))

    def test_url_date_hint_does_not_treat_arbitrary_ids_as_dates(self):
        self.assertEqual(str(url_publication_day("https://news.example/2026/10/24/story")),"2026-10-24")
        self.assertEqual(str(url_publication_day("https://news.example/a/202610/24/WS123.html")),"2026-10-24")
        self.assertIsNone(url_publication_day("https://news.example/article/20261024"))
        self.assertIsNone(url_publication_day("https://news.example/2026/13/90/story"))

    def test_listing_canonical_is_rejected_instead_of_saved_as_article(self):
        p = page()
        p.html = p.html.replace("https://news.example/article/1?utm_source=feed","https://news.example/economy")
        from news_collector.extract import ExtractionError
        with self.assertRaises(ExtractionError):
            extract_article(p,SOURCE,"raw/x")

    def test_document_title_fallback_still_requires_article_evidence(self):
        from news_collector.extract import ExtractionError
        source = replace(SOURCE,body_selectors=['//div[@class="story-text"]'])
        p = page()
        p.html = '<html><head><title>Полимерный кластер</title></head><body><div class="story-text">'+('Компании инвестируют в промышленный кластер. '*20)+'</div></body></html>'
        article = extract_article(p,source,"raw/x")
        self.assertEqual(article.title,"Полимерный кластер")
        self.assertIn("промышленный кластер",article.text)
        with self.assertRaises(ExtractionError):
            extract_article(p,replace(source,body_selectors=[]),"raw/x")

    def test_source_title_selector_excludes_sidebar_heading(self):
        p=page()
        p.html=p.html.replace('<body>','<body><h1>Аналитика и комментарии</h1>')
        p.html=p.html.replace('<h1>Новый завод</h1>','<h1 class="aTitle">Инвестиции компании</h1>')
        source=replace(SOURCE,title_selectors=['//h1[@class="aTitle"]'])
        self.assertEqual(extract_article(p,source,'raw/x').title,'Инвестиции компании')

    def test_teaser_article_elements_do_not_make_a_section_an_article(self):
        from news_collector.extract import ExtractionError
        p=page()
        p.html='<html><h1>Экономика</h1>'+('<article><h2>Краткий анонс</h2><p>'+('Анонс другой публикации. '*20)+'</p></article>')*3+'</html>'
        with self.assertRaises(ExtractionError):
            extract_article(p,replace(SOURCE,body_selectors=[]),'raw/x')

    def test_configured_body_excludes_inline_ads_code_and_preserves_paragraphs(self):
        p=page()
        p.html='<article><h1>Инвестиции</h1><div id="story"><p>'+('Компания строит завод. '*10)+'</p><script>window.advertisingSecret="not article text";</script><style>.advert { color: red }</style><p>Вторая часть новости.</p></div></article>'
        article=extract_article(p,replace(SOURCE,body_selectors=['//*[@id="story"]']),'raw/x')
        self.assertNotIn('advertisingSecret',article.text)
        self.assertNotIn('color: red',article.text)
        self.assertIn('\n\nВторая часть новости.',article.text)

    def test_subscription_advert_is_not_a_paid_article_excerpt(self):
        from news_collector.extract import ExtractionError
        p = page(body="Новый завод Subscribe to unlock this article " + "Explore more offers and subscribe now. "*15,paid=True)
        with self.assertRaises(ExtractionError):
            extract_article(p,SOURCE,"raw/x")

    def test_existing_database_migrates_queue_and_prioritizes_fresh_discovery(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"db"
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE frontier(source_id TEXT,url TEXT,discovered_at TEXT,state TEXT DEFAULT 'pending',attempts INTEGER DEFAULT 0,next_attempt REAL DEFAULT 0,lease_until REAL DEFAULT 0,last_error TEXT,PRIMARY KEY(source_id,url))")
            db.commit()
            db.close()
            store = Store(path)
            try:
                store.enqueue("a",["old"])
                store.enqueue("a",["fresh"],{"fresh":100})
                self.assertEqual(store.claim("a")["url"],"fresh")
                self.assertEqual(store.claim("a")["url"],"old")
            finally:
                store.close()

    def test_quarantine_preserves_record_and_allows_recovery_after_adapter_fix(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory)/"db")
            try:
                a = extract_article(page(),SOURCE,"raw/x")
                store.complete({"url":a.url},a)
                store.quarantine(a.record(),"Bad adapter")
                self.assertEqual(store.stats()["articles"],0)
                self.assertEqual(store.stats()["revisions"],1)
                saved = json.loads(store.db.execute("SELECT record FROM quarantined_articles").fetchone()[0])
                self.assertEqual(saved["raw_html_path"],"raw/x")
                store.complete({"url":a.url},a)
                self.assertEqual(store.stats()["articles"],1)
                self.assertEqual(store.db.execute("SELECT count(*) FROM quarantined_articles").fetchone()[0],0)
            finally:
                store.close()

    def test_export_filters_dates_topics_and_paid_fragments(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory)/"db")
            try:
                now = datetime.now(timezone.utc)
                for index,(date,paid) in enumerate(((now,False),(now,True),(now-timedelta(days=100),False))):
                    a = extract_article(page(published=date.isoformat(),paid=paid),SOURCE,"raw/x")
                    a.canonical_url = a.url = f"https://news.example/article/{index}"
                    a.topics = ["business"]
                    store.complete({"url":a.url},a)
                dest = Path(directory)/"out.jsonl"
                self.assertEqual(store.export(dest,max_age_days=14,topics=["business"],full_text_only=True),1)
                self.assertEqual(store.export(dest,topics=["ai"]),0)
                self.assertEqual(store.stats()["articles"],3)
            finally:
                store.close()

    def test_seed_failure_does_not_lose_other_sections_or_queued_articles(self):
        class FakeBrowser:
            identity = {"userAgent":"Chrome"}
            def diagnostic(self,*_): pass
            def read(self,url,article=False,**_):
                if url.endswith("/robots.txt"):
                    return Page(url,url,"",'<pre>User-agent: *\nAllow: /</pre>',"User-agent: *\nAllow: /",200)
                if url.endswith("/broken"):
                    raise PageError("HTTP 404")
                if article:
                    return page(published=datetime.now(timezone.utc).isoformat())
                return Page(url,url,"",'<a href="/article/1">business</a>',"",200)
        class FastCollector(Collector):
            def paced_read(self,browser,store,source,url,**kw):
                return browser.read(url,**kw)
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory)/"news.sqlite3")
            try:
                source = replace(SOURCE,seeds=["https://news.example/broken",*SOURCE.seeds])
                result = FastCollector(Path(directory)).collect_source(FakeBrowser(),store,source,1,20)
                self.assertEqual(result["saved"],1)
                self.assertEqual(len(result["seed_errors"]),1)
                self.assertEqual(result["discovered"],1)
            finally:
                store.close()

    def test_report_does_not_confuse_configured_with_collected(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            config = directory/"sources.json"
            config.write_text(json.dumps({"sources":[{"id":"example","name":"Example","enabled":True},{"id":"unseen","name":"Unseen","enabled":True}]}))
            store = Store(directory/"db")
            try:
                store.complete({"url":page().url},extract_article(page(),SOURCE,"raw/x"))
                result = write_report(store,config,directory/"coverage.md")
                self.assertEqual(result["sources_with_articles"],1)
                self.assertEqual(result["sources"][1]["status"],"untested")
                self.assertTrue((directory/"coverage.json").exists())
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
