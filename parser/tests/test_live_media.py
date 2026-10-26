from datetime import datetime,timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from test_collector import SOURCE,page
from news_collector.browser import Page
from news_collector.runner import Collector
from news_collector.storage import Store


class LinksOnlyTests(unittest.TestCase):
    def test_collection_keeps_article_and_image_url_without_download(self):
        class Browser:
            identity={'userAgent':'Chrome/155.0.0.0'}
            def __init__(self,*args,**kwargs):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def diagnostic(self,*args):pass
            def read(self,url,article=False,**kwargs):
                if url.endswith('/robots.txt'):
                    return Page(url,url,'','<pre>User-agent: *\nAllow: /</pre>','User-agent: *\nAllow: /',200)
                if article:
                    p=page(published=datetime.now(timezone.utc).isoformat())
                    p.html=p.html.replace('</head>','<meta property="og:image" content="https://cdn.example/large.jpg"></head>')
                    return p
                return Page(url,url,'Listing','<a href="/article/1">article</a>','article',200)
        class Fast(Collector):
            def paced_read(self,browser,store,source,url,article=False,check_access=True):
                return browser.read(url,article=article)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);Store(root/'news.sqlite3').close()
            with patch('news_collector.runner.Browser',Browser),patch('news_collector.runner.download_images') as download:
                result=Fast(root,defer_images=True).cycle([SOURCE],workers=1,max_articles=1)
                download.assert_not_called()
            self.assertEqual(result[0]['saved'],1)
            with sqlite3.connect(root/'news.sqlite3') as db:
                record=json.loads(db.execute('SELECT record FROM articles').fetchone()[0])
            self.assertTrue(record['text']);self.assertEqual(record['images'][0]['url'],'https://cdn.example/large.jpg')
            self.assertFalse(list(root.glob('images/**/*.jpg')))
