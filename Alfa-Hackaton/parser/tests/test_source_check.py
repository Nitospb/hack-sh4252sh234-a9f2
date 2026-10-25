from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from news_collector.browser import AccessBlocked, Page, PageError
from news_collector.models import digest
from news_collector.runner import Collector
from news_collector.source_check import check_one, check_sources, source_fingerprint
from news_collector.storage import Store
from test_collector import SOURCE, page


class FastCollector(Collector):
    def paced_read(self,browser,store,source,url,**kwargs):
        return browser.read(url,**kwargs)


class FakeBrowser:
    identity = {"userAgent":"Chrome"}
    reads = []
    def __init__(self,*_,**__): pass
    def __enter__(self): return self
    def __exit__(self,*_): pass
    def read(self,url,article=False,**_):
        self.reads.append(url)
        if url.endswith('/robots.txt'):
            return Page(url,url,"",'<pre>User-agent: *\nAllow: /</pre>',"User-agent: *\nAllow: /",200)
        if url.endswith('/broken'):
            raise PageError('HTTP 404')
        if article:
            p = page(published=datetime.now(timezone.utc).isoformat())
            p.html = p.html.replace('https://news.example/article/1?utm_source=feed',url)
            p.html = p.html.replace('Компания сообщила',f'Компания {url.rsplit("/",1)[-1]} сообщила')
            p.url=p.requested_url=url
            return p
        return Page(url,url,"Listing",'<a href="/article/1">Банк и инвестиции</a><a href="/article/2">Экономика</a><a href="/2020/01/01/old">Старый материал</a>',"Listing",200)
    def image_bytes(self,*_):
        raise AssertionError('Adapter check must not download images')


class SourceCheckTests(unittest.TestCase):
    def setUp(self): FakeBrowser.reads=[]

    def test_checks_two_articles_without_collecting_corpus_or_images(self):
        with tempfile.TemporaryDirectory() as directory,patch('news_collector.source_check.Browser',FakeBrowser):
            runtime=Path(directory)
            result=check_one(FastCollector(runtime),SOURCE)
            self.assertEqual(result['status'],'passed')
            self.assertEqual(len(result['samples']),2)
            records=[json.loads(line) for line in (runtime/'source-checks'/SOURCE.id/'samples.jsonl').read_text().splitlines()]
            self.assertEqual(len(records),2)
            self.assertGreater(len(records[0]['text']),SOURCE.min_text_chars)
            self.assertEqual(records[0]['source_id'],SOURCE.id)
            store=Store(runtime/'news.sqlite3')
            try:self.assertEqual(store.stats()['articles'],0)
            finally:store.close()

    def test_bad_seed_does_not_prevent_good_section(self):
        with tempfile.TemporaryDirectory() as directory,patch('news_collector.source_check.Browser',FakeBrowser):
            source=replace(SOURCE,seeds=['https://news.example/broken',*SOURCE.seeds])
            result=check_one(FastCollector(Path(directory)),source)
            self.assertEqual(result['status'],'passed')
            self.assertEqual(len(result['seed_errors']),1)

    def test_alias_urls_do_not_count_as_distinct_verified_articles(self):
        from news_collector.extract import extract_article
        def one_canonical(*args):
            article=extract_article(*args)
            article.canonical_url='https://news.example/article/1'
            return article
        with tempfile.TemporaryDirectory() as directory,patch('news_collector.source_check.Browser',FakeBrowser),patch('news_collector.source_check.extract_article',side_effect=one_canonical):
            result=check_one(FastCollector(Path(directory)),SOURCE)
            self.assertEqual(len(result['samples']),1)
            self.assertEqual(result['status'],'partial')
            self.assertIn('Duplicate canonical',result['article_errors'][0]['error'])

    def test_repeated_boilerplate_does_not_prove_two_articles_work(self):
        from news_collector.extract import extract_article
        def identical_text(*args):
            article=extract_article(*args)
            article.text='A publisher subscription footer repeated on every page. '*10
            return article
        with tempfile.TemporaryDirectory() as directory,patch('news_collector.source_check.Browser',FakeBrowser),patch('news_collector.source_check.extract_article',side_effect=identical_text):
            result=check_one(FastCollector(Path(directory)),SOURCE)
            self.assertEqual(result['status'],'partial')
            self.assertIn('Duplicate extracted text',result['article_errors'][0]['error'])

    def test_old_url_is_not_visited_for_current_news_check(self):
        with tempfile.TemporaryDirectory() as directory,patch('news_collector.source_check.Browser',FakeBrowser):
            source=replace(SOURCE,article_pattern=r'^/(?:article/\d+|2020/01/01/old)$')
            result=check_one(FastCollector(Path(directory)),source,samples=3)
            self.assertEqual(len(result['samples']),2)
            self.assertNotIn('https://news.example/2020/01/01/old',FakeBrowser.reads)

    def test_robots_denial_is_reported_without_article_reads(self):
        with tempfile.TemporaryDirectory() as directory,patch('news_collector.source_check.Browser',FakeBrowser):
            collector=FastCollector(Path(directory))
            with patch.object(collector,'robots',return_value=False):result=check_one(collector,SOURCE)
            self.assertEqual(result['status'],'robots_disallowed')
            self.assertFalse(FakeBrowser.reads)

    def test_stop_does_not_start_browser_for_queued_sources(self):
        with tempfile.TemporaryDirectory() as directory,patch('news_collector.source_check.Browser') as browser:
            stop=threading.Event();stop.set()
            result=check_one(FastCollector(Path(directory),stop=stop),SOURCE)
            self.assertEqual(result['status'],'interrupted')
            browser.assert_not_called()

    def test_resume_skips_same_rules_but_retries_interrupted_work(self):
        with tempfile.TemporaryDirectory() as directory,patch('news_collector.source_check.Browser',FakeBrowser):
            runtime=Path(directory);collector=FastCollector(runtime)
            check_sources(collector,[SOURCE],workers=1)
            with patch('news_collector.source_check.check_one') as check:
                report=check_sources(collector,[replace(SOURCE,enabled=False)],resume=True)
                check.assert_not_called()
                self.assertEqual(report['passed_sources'],1)
            report=json.loads((runtime/'source-checks.json').read_text());report['sources'][0]['status']='interrupted'
            (runtime/'source-checks.json').write_text(json.dumps(report))
            report=check_sources(collector,[SOURCE],resume=True)
            self.assertEqual(report['passed_sources'],1)

    def test_fingerprint_changes_with_adapter_rules_not_enable_flag(self):
        self.assertEqual(source_fingerprint(SOURCE),source_fingerprint(replace(SOURCE,enabled=False)))
        self.assertNotEqual(source_fingerprint(SOURCE),source_fingerprint(replace(SOURCE,article_pattern='^/new/')))
        self.assertNotEqual(source_fingerprint(SOURCE),source_fingerprint(replace(SOURCE,title_selectors=['//h2'])))

    def test_resume_increases_requested_sample_depth(self):
        with tempfile.TemporaryDirectory() as directory,patch('news_collector.source_check.Browser',FakeBrowser):
            collector=FastCollector(Path(directory))
            report=check_sources(collector,[SOURCE],samples=1)
            self.assertEqual(len(report['sources'][0]['samples']),1)
            report=check_sources(collector,[SOURCE],samples=2,resume=True)
            self.assertEqual(len(report['sources'][0]['samples']),2)
