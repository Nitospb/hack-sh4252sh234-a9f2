import os
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from recommendations.engine import Feed
from recommendations.server import handler
from service.runtime import Runtime
from service.seed import create
from service.smoke import check
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import json

class HttpTests(unittest.TestCase):
    def test_clean_seed_end_to_end_without_llm(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'ALFA_API_KEY':'','ALFA_INTERNAL_TOKEN':''}):
            root=Path(tmp);catalog=create(root/'seed')
            feed=Feed(catalog,root/'feedback.sqlite',embeddings=False)
            runtime=Runtime(feed,assets=root/'seed/service-assets.sqlite',state=root/'service.sqlite')
            server=ThreadingHTTPServer(('127.0.0.1',0),handler(feed,runtime))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            try:
                result=check(base)
                self.assertEqual(result['dataset_kind'],'synthetic');self.assertGreater(result['feed_items'],0)
                scope={'company_id':'SEED_1','source_record_id':'SEED_1:line:2','user_id':'u','article_id':'seed_article_0'}
                with self.assertRaises(HTTPError) as caught:
                    urlopen(Request(base+'/analysis',data=json.dumps(scope).encode(),headers={'Content-Type':'application/json'}))
                self.assertEqual(caught.exception.code,400)
                with patch.dict(os.environ,{'ALFA_INTERNAL_TOKEN':'test-internal-only'}):
                    with self.assertRaises(HTTPError) as caught:urlopen(base+'/health')
                    self.assertEqual(caught.exception.code,403)
            finally:server.shutdown();server.server_close();thread.join();runtime.pool.shutdown(wait=True)
