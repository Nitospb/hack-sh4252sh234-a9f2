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
                with urlopen(base+'/openapi.json') as response:
                    spec=json.load(response)
                    self.assertEqual(response.headers['Content-Type'],'application/json; charset=utf-8')
                    self.assertEqual(spec['servers'][0]['url'],'/api/live')
                    self.assertIn('post',spec['paths']['/analysis'])
                result=check(base)
                self.assertEqual(result['dataset_kind'],'synthetic');self.assertGreater(result['feed_items'],0)
                scope={'company_id':'SEED_1','source_record_id':'SEED_1:line:2','user_id':'u','article_id':'seed_article_0'}
                with self.assertRaises(HTTPError) as caught:
                    urlopen(Request(base+'/analysis',data=json.dumps(scope).encode(),headers={'Content-Type':'application/json'}))
                self.assertEqual(caught.exception.code,400)
                parameters={'kind':'loan','currency':'RUB','principal':'1000','days':'365','basis':365,'rate_type':'fixed','fixed_rate':'10','acknowledge_assumptions':True}
                with urlopen(Request(base+'/scenario',data=json.dumps({**scope,'parameters':parameters}).encode(),headers={'Content-Type':'application/json'})) as response:
                    self.assertEqual(json.load(response)['delta'],'0.00')
                with urlopen(base+'/scenarios?company_id=SEED_1&source_record_id=SEED_1:line:2&user_id=another') as response:
                    self.assertEqual(json.load(response)['items'],[])
                with patch.dict(os.environ,{'ALFA_API_KEY':'configured-test-key-no-network','ALFA_MAX_CALLS_PER_DAY':'1'}):
                    with urlopen(base+'/health') as response:
                        health=json.load(response);self.assertFalse(health['llm_available'])
                        self.assertEqual(health['analysis_availability']['reason'],'calls')
                    with self.assertRaises(HTTPError) as limited:
                        urlopen(Request(base+'/analysis',data=json.dumps(scope).encode(),headers={'Content-Type':'application/json'}))
                    self.assertEqual(limited.exception.code,503)
                    with runtime.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM calls').fetchone()[0],0)
                    with urlopen(base+'/scenarios?company_id=SEED_1&source_record_id=SEED_1:line:2&user_id=u') as response:
                        self.assertEqual(len(json.load(response)['items']),1)
                with patch.dict(os.environ,{'ALFA_INTERNAL_TOKEN':'test-internal-only'}):
                    with self.assertRaises(HTTPError) as caught:urlopen(base+'/health')
                    self.assertEqual(caught.exception.code,403)
                    with self.assertRaises(HTTPError) as caught:urlopen(base+'/openapi.json')
                    self.assertEqual(caught.exception.code,403)
            finally:server.shutdown();server.server_close();thread.join();runtime.pool.shutdown(wait=True)
