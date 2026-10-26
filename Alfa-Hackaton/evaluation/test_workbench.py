import json
from pathlib import Path
import tempfile
import unittest
from service.seed import create
from evaluation.workbench import freeze,adjudicate
import hashlib

class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);create(self.root/'catalog');self.out=self.root/'pool'
    def tearDown(self):self.temp.cleanup()
    def pool(self):return freeze(self.root/'catalog/catalog.sqlite',self.root/'catalog/service-assets.sqlite',self.out,queries=2,k=2)
    def test_blind_pool_contains_no_automatic_judgments(self):
        result=self.pool();self.assertGreater(result['tasks'],0)
        b=json.loads((self.out/'pool.json').read_text());self.assertTrue(all(not q['judgments'] for q in b['queries']))
        html=(self.out/'reviewer.html').read_text();self.assertNotIn('personalized_pipeline',html)
        self.assertNotIn('lexical_title',html);self.assertIn('Первоисточник',html)
    def test_two_review_files_required_and_disagreement_is_pending(self):
        self.pool();pool=self.out/'pool.json';b=json.loads(pool.read_text());tid=b['tasks'][0]['task_id'];sha=hashlib.sha256(pool.read_bytes()).hexdigest()
        paths=[]
        for actor,grade in [('one',2),('two',1)]:
            p=self.root/(actor+'.json');p.write_text(json.dumps({'reviewer':actor,'pool_sha256':sha,'ratings':[{'task_id':tid,'relevance':grade,'evidence':'Source quotation'}]}));paths.append(p)
        report=adjudicate(pool,paths,self.root/'disagreement.json','expert');self.assertEqual(report['adjudicated_human_pairs'],0)
        data=json.loads(paths[1].read_text());data['ratings'][0]['relevance']=2;paths[1].write_text(json.dumps(data))
        report=adjudicate(pool,paths,self.root/'agreement.json','expert');self.assertEqual(report['adjudicated_human_pairs'],1)
        with self.assertRaises(ValueError):adjudicate(pool,[paths[0],paths[0]],self.root/'duplicate.json','expert')
    def test_wrong_pool_is_rejected(self):
        self.pool();p=self.root/'rating.json';p.write_text(json.dumps({'reviewer':'one','pool_sha256':'wrong','ratings':[]}))
        with self.assertRaises(ValueError):adjudicate(self.out/'pool.json',[p],self.root/'bad.json','expert')
