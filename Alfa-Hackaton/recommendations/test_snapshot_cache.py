import tempfile,time,unittest
from pathlib import Path
from service.seed import create
from pipeline.publication import publish
from recommendations.engine import Feed

class SnapshotCacheTests(unittest.TestCase):
    def test_immutable_article_cache_preserves_scores_scopes_and_original_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);create(root/'seed');manifest=publish(root/'seed',root/'releases',allow_synthetic=True)
            generation=root/'releases'/manifest['version']
            cached=Feed(generation/'catalog.sqlite',root/'cached.sqlite',embeddings=False)
            uncached=Feed(root/'seed/catalog.sqlite',root/'plain.sqlite',embeddings=False)
            stamp=time.time();args=dict(source_record_id='SEED_1:line:2',limit=3,now=stamp,mode='ranked')
            a=cached.recommend('SEED_1','one',**args)['items'];b=uncached.recommend('SEED_1','one',**args)['items']
            self.assertEqual(a,b)
            self.assertEqual(a,cached.recommend('SEED_1','two',**args)['items'])
            cached.event('SEED_1','one',a[0]['article_id'],'hide','hide-1')
            self.assertEqual(a,cached.recommend('SEED_1','three',**args)['items'])
            self.assertNotIn('text',next(iter(cached._article_cache[True])))
            with self.assertRaises(TypeError):cached._article_cache[True][0]['score']=999
            with cached.source() as db:self.assertTrue(db.execute('SELECT text FROM articles LIMIT 1').fetchone()[0])
            self.assertFalse(any(k.startswith('_') for item in a for k in item))
