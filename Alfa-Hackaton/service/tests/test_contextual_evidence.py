from datetime import datetime,timezone
from pathlib import Path
import sqlite3,tempfile,time,unittest
from unittest.mock import patch
from service.tests import test_runtime as fixtures
from service.seed import create
from recommendations.engine import Feed
from recommendations import catalog

class ContextualEvidenceTests(unittest.TestCase):
    setUp=fixtures.AgentTests.setUp
    tearDown=fixtures.AgentTests.tearDown
    finished=fixtures.AgentTests.finished

    def test_source_comparison_does_not_replace_qualitative_assessment_or_use_unknown_aliases(self):
        self.a.update(title='Банк России сохранил ключевую ставку',text='Банк России сохранил ключевую ставку 14%. Рост индекса составил 6%.')
        self.a['story']={'story_id':'story','items':[{'article_id':'related','content_hash':'r','title':'Ключевая ставка Банка России','text':'Банк России оставил ключевую ставку 14%.','url':'https://example.org/r','published_at':self.a['published_at']}],'numeric_variants':[]}
        original=self.r.generator
        def generator(payload):
            evidence=payload['source_evidence'];self.assertTrue(evidence['comparisons'])
            self.assertTrue(all(f['source_id'] in {'news','related_1'} for f in evidence['facts']))
            self.assertTrue(all(p['status']=='same_value' for p in evidence['comparisons']))
            return original(payload)
        self.r.generator=generator
        result=self.finished(self.r.submit(self.c,self.a,'u'))
        self.assertEqual(result['status'],'complete',result['error'])
        self.assertEqual(result['result']['insight']['why_for_company'][0]['text'],'Проверить применимость правил к деятельности.')
        self.assertEqual(result['result']['source_comparison']['comparisons'][0]['source_ids'],['a','related'])
        self.assertIn('compare_source_facts',[step['tool'] for step in result['steps']])

    def test_forecast_companion_canonical_ids_are_preserved_without_forcing_bank_claim(self):
        text=lambda n:f'Ожидаем инфляцию России на конец 2026 года {n}%.'
        old={'id':'old_p1','document_id':'old','document_title':'old.pdf','published_at':'2026-08-01','page':1,'text':text(6),'method':'pdf_text'}
        with self.r.db():pass
        with sqlite3.connect(self.r.assets) as db:
            for id,date,n in [('old','2026-08-01',6),('new','2026-09-01',7)]:
                db.execute('INSERT INTO bank_documents VALUES(?,?,?,?,?,?)',(id,id+'.pdf','unused','sha',date,1))
                db.execute('INSERT INTO bank_passages VALUES(?,?,?,?,?)',(id+'_p1',id,1,text(n),'pdf_text'))
        original=self.r.generator
        def generator(payload):
            self.assertEqual([p['id'] for p in payload['bank_passages']],['bank_1','bank_2'])
            evidence=payload['source_evidence'];facts={f['id']:f for f in evidence['facts']}
            pair=next(p for p in evidence['comparisons'] if p['preferred_fact_id'])
            self.assertEqual(facts[pair['preferred_fact_id']]['source_id'],'bank_2')
            return original(payload)
        self.r.generator=generator
        with patch('service.bank.search',return_value=[old]):result=self.finished(self.r.submit(self.c,self.a,'u'))
        self.assertEqual(result['status'],'complete',result['error'])
        self.assertEqual([p['id'] for p in result['result']['sources']],['old_p1','new_p1'])
        self.assertIsNone(result['result']['insight']['bank_view'])

class RankingPreservationTests(unittest.TestCase):
    def test_reading_comparison_does_not_change_relevance_scores_or_source_articles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=create(root/'seed');feed=Feed(path,root/'state.sqlite',embeddings=False);stamp=time.time()
            args=dict(source_record_id='SEED_1:line:2',mode='ranked',limit=3,now=stamp)
            before=feed.recommend('SEED_1','reader-before',**args)['items']
            from pipeline.facts import compare
            sources=[{'id':'one','text':'Выручка ПАО «Другой бизнес» за 2025 год составила 1 млрд рублей.','published_at':'2026-10-01'},
                     {'id':'two','text':'Выручка ПАО «Другой бизнес» за 2025 год составила 2 млрд рублей.','published_at':'2026-10-02'}]
            self.assertTrue(compare(sources)['comparisons'])
            after=feed.recommend('SEED_1','reader-after',**args)['items']
            self.assertEqual(before,after)
