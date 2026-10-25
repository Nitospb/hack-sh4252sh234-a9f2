import base64
from dataclasses import asdict
import gzip
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from lxml import html
from PIL import Image

from news_collector.browser import Browser, Page, PageError
from news_collector.cli import main
from news_collector.extract import extract_article
from news_collector.images import candidates, download_images, image_url, persist_image
from news_collector.models import digest
from news_collector.storage import Store
from news_collector.runner import Collector
from test_collector import SOURCE, page


def png(width=640,height=360):
    buffer = BytesIO()
    Image.new("RGB",(width,height),(15,110,130)).save(buffer,"PNG")
    return buffer.getvalue()


class ImagesTests(unittest.TestCase):
    def test_document_base_resolves_images_and_preserves_article_identity(self):
        tree=html.fromstring('<html><base href="https://news.example/"><article><img src="media/lead.jpg?sig=z%2B2&amp;b=1"></article></html>')
        result=candidates(tree,SOURCE,'https://news.example/article/1',{})
        self.assertEqual(result[0]['url'],'https://news.example/media/lead.jpg?sig=z%2B2&b=1')
        self.assertEqual(result[0]['article_id'],digest('https://news.example/article/1'))

    def test_cdn_signature_is_preserved_and_private_schemes_rejected(self):
        self.assertEqual(image_url("https://news.example/story","https://cdn.example/image?z=2&sig=AbC&x=1#photo"),"https://cdn.example/image?z=2&sig=AbC&x=1")
        for value in ("data:image/png;base64,AAA","javascript:alert(1)","http://127.0.0.1/a.jpg","https://user:pass@example.com/a"):
            self.assertIsNone(image_url("https://news.example/",value))

    def test_lead_and_body_images_exclude_outside_logo_and_related_news(self):
        tree = html.fromstring('''<html><head><meta property="og:image" content="/lead.jpg"></head><body>
          <img src="/logo.png"><article><figure><img src="/small.jpg" srcset="/medium.jpg 640w, /large.jpg 1280w" alt="Биржа"><figcaption>Фото биржи</figcaption></figure>
          <aside><img src="/related.jpg"></aside><img class="avatar" src="/avatar.jpg">
          <div class="related"><img src="/other-news.jpg"></div>
          <div class="widget-subscription"><img src="/subscribe.png"></div>
          <a href="/article/999?utm_source=interlink"><img src="/linked-other-story.jpg"></a>
          </article></body></html>''')
        images = candidates(tree,SOURCE,page().url,{"image":{"url":"/lead.jpg"}})
        self.assertEqual([x["url"] for x in images],["https://news.example/lead.jpg","https://news.example/large.jpg"])
        self.assertEqual(images[1]["caption"],"Фото биржи")
        self.assertEqual(images[0]["article_id"],digest(page().url))

    def test_real_bytes_format_size_and_hash_not_url_extension(self):
        with tempfile.TemporaryDirectory() as folder:
            data = png()
            result = persist_image(Path(folder),"a"*64,data)
            self.assertEqual(result["mime_type"],"image/png")
            self.assertEqual((result["width"],result["height"]),(640,360))
            self.assertEqual(result["sha256"],hashlib.sha256(data).hexdigest())
            self.assertEqual((Path(folder)/result["local_path"]).read_bytes(),data)
            for bad in (b"<html>Subscribe</html>",png(16,16),png(300,300),png(1600,100),b"x"*(10*1024*1024+1)):
                with self.assertRaises((ValueError,OSError)):
                    persist_image(Path(folder),"a"*64,bad)
            self.assertEqual(persist_image(Path(folder),"a"*64,png(400,400))["width"],400)

    def test_download_failure_is_separate_from_text_and_cached_images_not_redownloaded(self):
        class FakeBrowser:
            calls = 0
            def image_bytes(self,url,limit):
                self.calls += 1
                if "bad" in url:
                    raise RuntimeError("HTTP 403")
                return png()
        p = page()
        p.html = p.html.replace("</head>",'<meta property="og:image" content="/bad.jpg"><meta name="twitter:image" content="/good.jpg"></head>')
        a = extract_article(p,SOURCE,"raw/x")
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            browser = FakeBrowser()
            a.images,a.main_image_path = download_images(browser,runtime,a.canonical_url,a.title,a.images)
            self.assertEqual(a.images[0]["status"],"failed")
            self.assertEqual(a.images[1]["status"],"saved")
            self.assertTrue(a.main_image_path)
            self.assertTrue(a.text)
            self.assertEqual(a.record()["images_status"],"partial")
            again = extract_article(p,SOURCE,"raw/x")
            again.images,again.main_image_path = download_images(browser,runtime,a.canonical_url,a.title,again.images,a.images)
            # A valid cached lead makes failed metadata alternatives unnecessary.
            self.assertEqual(browser.calls,2)
            self.assertEqual(again.main_image_path,a.main_image_path)
            manifest = json.loads((runtime/"images"/a.record()["id"]/"manifest.json").read_text())
            self.assertEqual(manifest["canonical_url"],a.canonical_url)

    def test_small_image_is_filtered_without_discarding_news(self):
        p = page()
        p.html = p.html.replace("</head>",'<meta property="og:image" content="/small.jpg"></head>')
        a = extract_article(p,SOURCE,"raw/x")
        class FakeBrowser:
            def image_bytes(self,*_): return png(300,300)
        with tempfile.TemporaryDirectory() as folder:
            a.images,a.main_image_path = download_images(FakeBrowser(),Path(folder),a.canonical_url,a.title,a.images)
            self.assertEqual(a.images[0]["status"],"filtered")
            self.assertIsNone(a.main_image_path)
            self.assertEqual(a.record()["images_status"],"filtered")
            self.assertTrue(a.text)

    def test_collector_commits_news_before_attempting_image_download(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            class FakeBrowser:
                identity = {"userAgent":"Chrome"}
                def __init__(self,*_,**__): pass
                def __enter__(self): return self
                def __exit__(self,*_): pass
                def diagnostic(self,*_): pass
                def read(self,url,article=False,**_):
                    if url.endswith("/robots.txt"):
                        return Page(url,url,"","<pre>User-agent: *\nAllow: /</pre>","User-agent: *\nAllow: /",200)
                    if article:
                        p = page(published=datetime.now(timezone.utc).isoformat())
                        p.html = p.html.replace("</head>",'<meta property="og:image" content="/photo.jpg"></head>')
                        return p
                    return Page(url,url,"",'<a href="/article/1">News</a>',"News",200)
                def image_bytes(self,*_):
                    probe = Store(runtime/"news.sqlite3")
                    try:
                        assert probe.stats()["articles"]==1, "Text must already be committed"
                    finally:
                        probe.close()
                    raise PageError("Image CDN unavailable")
            class FastCollector(Collector):
                def paced_read(self,browser,store,source,url,**kw): return browser.read(url,**kw)
            Store(runtime/"news.sqlite3").close()
            with patch("news_collector.runner.Browser",FakeBrowser):
                results = FastCollector(runtime).cycle([SOURCE],workers=1,max_articles=1)
            self.assertEqual(results[0]["saved"],1)
            store = Store(runtime/"news.sqlite3")
            try:
                record = json.loads(store.db.execute("SELECT record FROM articles").fetchone()[0])
                self.assertEqual(record["images"][0]["status"],"failed")
                self.assertTrue(record["text"])
                self.assertEqual(store.db.execute("SELECT state FROM frontier").fetchone()[0],"done")
            finally:
                store.close()

    def test_image_links_are_transactional_and_do_not_change_text_versions(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            a = extract_article(page(),SOURCE,"raw/x")
            store = Store(runtime/"db")
            try:
                store.complete({"url":a.url},a)
                image = {"id":"img1","article_id":a.record()["id"],"status":"saved","local_path":"images/test.png"}
                store.set_images(a.record()["id"],[image],image["local_path"])
                data = json.loads(store.db.execute("SELECT record FROM articles").fetchone()[0])
                self.assertEqual(data["content_hash"],a.record()["content_hash"])
                self.assertEqual(data["main_image_path"],"images/test.png")
                self.assertEqual(store.stats()["revisions"],1)
                self.assertEqual(store.db.execute("SELECT article_id FROM article_images").fetchone()[0],a.record()["id"])
            finally:
                store.close()

    def test_audit_preserves_downloaded_files_and_their_links(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            config = runtime/"sources.json"
            config.write_text(json.dumps({"sources":[asdict(SOURCE)]}))
            p = page()
            p.html = p.html.replace("</head>",'<meta property="og:image" content="/lead.jpg"></head>')
            (runtime/"raw").mkdir()
            (runtime/"raw/x.gz").write_bytes(gzip.compress(p.html.encode()))
            a = extract_article(p,SOURCE,"raw/x.gz")
            class FakeBrowser:
                def image_bytes(self,*_): return png()
            a.images,a.main_image_path = download_images(FakeBrowser(),runtime,a.canonical_url,a.title,a.images)
            store = Store(runtime/"news.sqlite3")
            store.complete({"url":a.url},a)
            store.close()
            with patch("builtins.print"):
                self.assertEqual(main(["--runtime",str(runtime),"--config",str(config),"audit"]),0)
            record = json.loads((runtime/"articles.jsonl").read_text())
            self.assertEqual(record["main_image_path"],a.main_image_path)
            self.assertEqual(record["images"][0]["status"],"saved")


class BrowserImageTests(unittest.TestCase):
    def test_unavailable_image_host_is_not_retried_for_every_image(self):
        class Driver:
            calls = 0
            def execute_cdp_cmd(self,name,params):
                if name=="Page.getFrameTree": return {"frameTree":{"frame":{"id":"f"}}}
                if name=="Network.loadNetworkResource":
                    self.calls += 1
                    return {"resource":{"success":False,"netErrorName":"net::ERR_NAME_NOT_RESOLVED"}}
                raise AssertionError(name)
        browser = Browser.__new__(Browser)
        browser.driver = Driver()
        browser._image_responses = {}
        for url in ("https://cdn.example/one.jpg","https://cdn.example/two.jpg"):
            with self.assertRaises(PageError): browser.image_bytes(url,100000)
        self.assertEqual(browser.driver.calls,1)

    def test_cdp_stream_is_closed_on_success_and_size_rejection(self):
        class Driver:
            closed = False
            def execute_cdp_cmd(self,name,params):
                if name=="Page.getFrameTree": return {"frameTree":{"frame":{"id":"f"}}}
                if name=="Network.loadNetworkResource": return {"resource":{"success":True,"stream":"s","httpStatusCode":200}}
                if name=="IO.read": return {"data":base64.b64encode(png()).decode(),"base64Encoded":True,"eof":True}
                if name=="IO.close": self.closed=True; return {}
                raise AssertionError(name)
        browser = Browser.__new__(Browser)
        browser.driver = Driver()
        browser._image_responses = {}
        self.assertEqual(browser.image_bytes("https://cdn.example/image",100000),png())
        self.assertTrue(browser.driver.closed)
        browser.driver.closed = False
        with self.assertRaises(ValueError):
            browser.image_bytes("https://cdn.example/image",10)
        self.assertTrue(browser.driver.closed)
