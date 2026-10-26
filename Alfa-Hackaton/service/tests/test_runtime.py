import json
import os
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
from recommendations.engine import Feed
from service.runtime import Runtime
from service import bank

class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.feed=Feed(self.root/'catalog.sqlite',self.root/'feedback.sqlite',embeddings=False)
        self.c={'company_id':'c','source_record_id':'c:line:2','okved':'62.01'}
        self.a={'article_id':'a','content_hash':'h','title':'Налоговые изменения','text':'Закон изменил порядок отчётности для компаний.',
         'published_at':datetime.now(timezone.utc).isoformat(),'url':'https://example.org/a','eligible_delivery':1}
        self.generated=0
        def generate(p):
            self.generated+=1
            return {'insight':{'status':'ready','title':'Разбор','event':{'text':p['news']['text'],'source_ids':[p['news']['id']]},
             'why_for_company':[{'text':'Проверить применимость правил к деятельности.','company_fact_ids':['fact_okved'],'source_ids':[p['news']['id']],'conditional':True}],
             'ai_application':[],'risks':[],'opportunities':[],'actions':[],'bank_view':None,'missing_context':[],'limitations':[]},'usage':{'total_tokens':12},'model':'test'}
        def verifier(p,d):return {'verification':{'verdict':'supported','issues':[],'query':'','quotes':[{'source_id':p['news']['id'],'quote':p['news']['text']}]},'usage':{'total_tokens':8}}
        self.r=Runtime(self.feed,self.root/'assets.sqlite',generator=generate,verifier=verifier)
    def tearDown(self):self.r.pool.shutdown(wait=True);self.tmp.cleanup()
    def finished(self,job):
        for _ in range(200):
            r=self.r.get_run(job['run_id'],'c','u','c:line:2')
            if r['status'] not in ('running','queued'):return r
            time.sleep(.01)
        self.fail('job timed out')
    def test_full_run_idempotency_and_trace(self):
        job=self.r.submit(self.c,self.a,'u');result=self.finished(job)
        self.assertEqual(result['status'],'complete',result['error'])
        self.assertEqual(result['result']['insight']['status'],'ready')
        self.assertEqual(result['result']['insight']['event']['source_ids'],['a'])
        self.assertEqual(result['result']['quotes'][0]['source_id'],'a')
        self.assertEqual([s['tool'] for s in result['steps']],['get_company_context','plan','search_bank','extract_event','source_aliases','draft','verify_sources','validate_output'])
        self.assertEqual(self.r.submit(self.c,self.a,'u')['run_id'],job['run_id']);self.assertEqual(self.generated,1)
        self.assertEqual(self.r.metrics('c','u')['tokens'],20)
        with self.assertRaises(ValueError):self.r.get_run(job['run_id'],'c','other')
        with self.assertRaises(ValueError):self.r.get_run(job['run_id'],'c','u','other-record')
    def test_user_context_is_scoped_and_invalidates_cache(self):
        first=self.finished(self.r.submit(self.c,self.a,'u'))
        self.r.add_note(self.c,'u','Экспортируем в Индию')
        self.assertTrue(any(f['evidence_level']=='candidate' for f in self.r.context(self.c,'u')['facts']))
        self.assertFalse(any(f['field']=='user_context' for f in self.r.context(self.c,'other')['facts']))
        second=self.finished(self.r.submit(self.c,self.a,'u'))
        self.assertNotEqual(first['id'],second['id'])
    def test_unverified_quote_suppresses_personal_claims(self):
        self.r.verifier=lambda p,d:{'verification':{'verdict':'supported','issues':[],'query':'','quotes':[{'source_id':'a','quote':'Такой цитаты в источнике нет.'}]},'usage':{}}
        r=self.finished(self.r.submit(self.c,self.a,'u'))
        self.assertEqual(r['result']['insight']['status'],'needs_context');self.assertFalse(r['result']['insight']['why_for_company'])
    def test_invalid_bank_quote_does_not_erase_supported_news_only_claims(self):
        self.r.verifier=lambda p,d:{'verification':{'verdict':'supported','issues':[],'query':'','quotes':[
            {'source_id':p['news']['id'],'quote':p['news']['text']},
            {'source_id':'unknown_bank','quote':'Не существующий в источнике банковский тезис'}]},'usage':{}}
        r=self.finished(self.r.submit(self.c,self.a,'u'))
        self.assertEqual(r['result']['insight']['status'],'ready')
        self.assertEqual(len(r['result']['quotes']),1)
    def test_followup_requires_owned_completed_parent(self):
        first=self.finished(self.r.submit(self.c,self.a,'u'))
        with self.assertRaises(ValueError):self.r.submit(self.c,self.a,'other',question='Что проверить?',parent_run_id=first['id'])
        second=self.finished(self.r.submit(self.c,self.a,'u',question='Что проверить?',parent_run_id=first['id']))
        self.assertEqual(second['status'],'complete')
    def test_one_schema_repair_is_bounded_and_preserves_validation(self):
        from jsonschema.exceptions import ValidationError
        original=self.r.generator;attempts=[]
        def broken_once(p):
            attempts.append(1)
            if len(attempts)==1:raise ValidationError('maxItems',validator='maxItems',path=['actions'])
            return original(p)
        self.r.generator=broken_once
        r=self.finished(self.r.submit(self.c,self.a,'u'))
        self.assertEqual(r['status'],'complete',r['error']);self.assertEqual(len(attempts),2)
        self.assertIn('repair_contract',[s['tool'] for s in r['steps']])
    def test_failed_tool_is_recorded_without_exception_payload(self):
        def broken(p):raise ConnectionError('private-provider-body')
        self.r.generator=broken
        r=self.finished(self.r.submit(self.c,self.a,'u'))
        self.assertEqual(r['status'],'error')
        step=r['steps'][-1]
        self.assertEqual(step['tool'],'draft');self.assertEqual(step['output']['error_type'],'ConnectionError')
        self.assertNotIn('private-provider-body',json.dumps(r))
    def test_review_is_scoped_and_not_a_training_label(self):
        r=self.finished(self.r.submit(self.c,self.a,'u'))
        self.r.review(r['id'],'c','u','incorrect',record_id='c:line:2')
        self.assertEqual(self.r.metrics('c','u')['human_reviews']['incorrect'],1)
        with self.assertRaises(ValueError):self.r.review(r['id'],'c','other','useful')
    def test_verifier_diagnostics_do_not_replace_client_context_questions(self):
        original=self.r.generator
        def missing(p):
            r=original(p);r['insight']['status']='needs_context';r['insight']['missing_context']=['Каков срок до погашения кредита?'];return r
        self.r.generator=missing
        self.r.verifier=lambda p,d:{'verification':{'verdict':'needs_context','issues':['В черновике есть проблема проверки'],'query':'','quotes':[]},'usage':{}}
        r=self.finished(self.r.submit(self.c,self.a,'u'))
        self.assertEqual(r['result']['insight']['missing_context'],['Каков срок до погашения кредита?'])
    def test_daily_limit_and_freshness_fail_closed(self):
        with patch.dict(os.environ,{'ALFA_MAX_CALLS_PER_DAY':'1'}):
            r=self.finished(self.r.submit(self.c,self.a,'u'));self.assertEqual(r['status'],'error');self.assertIn('лимит',r['error'])
        with self.assertRaises(ValueError):self.r.submit(self.c,{**self.a,'published_at':(datetime.now(timezone.utc)-timedelta(days=31)).isoformat()},'u')
    def test_adaptive_search_never_silently_publishes_unverified_revision(self):
        self.r.verifier=lambda p,d:{'verification':{'verdict':'retrieve','issues':['Нужен другой тезис банка'],'query':'инфляция','quotes':[]},'usage':{}}
        r=self.finished(self.r.submit(self.c,self.a,'u'))
        self.assertIn('search_bank_refined',[s['tool'] for s in r['steps']]);self.assertIn('revise',[s['tool'] for s in r['steps']])
        self.assertEqual(r['result']['insight']['status'],'needs_context')

    def test_related_publication_quotes_and_cache_use_canonical_versions(self):
        related={'article_id':'related-canonical','content_hash':'v1','title':'Дополнительная публикация',
                 'text':'Срок введения нового правила указан в дополнительной публикации.',
                 'url':'https://another.example/news','published_at':datetime.now(timezone.utc).isoformat()}
        self.a['story']={'story_id':'story-test','items':[related],'numeric_variants':[]}
        generate=self.r.generator
        def generator(payload):
            result=generate(payload)
            result['insight']['actions']=[{'text':'Проверить срок применимости.',
                'company_fact_ids':['fact_okved'],'source_ids':[payload['related_news'][0]['id']],'conditional':True}]
            return result
        self.r.generator=generator
        self.r.verifier=lambda p,d:{'verification':{'verdict':'supported','issues':[],'query':'','quotes':[
            {'source_id':p['news']['id'],'quote':p['news']['text']},
            {'source_id':p['related_news'][0]['id'],'quote':p['related_news'][0]['text']}]},'usage':{}}
        first=self.finished(self.r.submit(self.c,self.a,'u'))
        self.assertEqual(first['status'],'complete',first['error'])
        self.assertEqual(first['result']['insight']['actions'][0]['source_ids'],['related-canonical'])
        self.assertEqual(first['result']['related_news'][0]['id'],'related-canonical')
        self.assertIn('compare_publications',[step['tool'] for step in first['steps']])
        related['content_hash']='v2'
        second=self.finished(self.r.submit(self.c,self.a,'u'))
        self.assertNotEqual(first['id'],second['id'])

    def test_global_needs_context_preserves_individually_supported_actions(self):
        from service.verification import claim_items
        generate=self.r.generator
        def partial(payload):
            result=generate(payload);draft=result['insight'];draft['status']='needs_context'
            draft['missing_context']=['Какова сумма и тип ставки по договору?']
            claim=draft['why_for_company'][0]
            draft['actions']=[{**claim,'text':'Если ставка плавающая, проверьте индекс и дату пересмотра.'},
                              {**claim,'text':'Расходы точно вырастут на миллион.'}]
            return result
        self.r.generator=partial
        self.r.verifier=lambda p,d:{'verification':{'verdict':'needs_context','event_verdict':'supported',
            'bank_verdict':'not_present','claim_reviews':[{'claim_id':row['claim_id'],
             'verdict':'unsupported' if row['claim_id']=='actions/1' else 'supported','reason':'Проверено отдельно'} for row in claim_items(d)],
             'context_questions':[],'issues':['Сумма неизвестна'],'query':'',
             'quotes':[{'source_id':p['news']['id'],'quote':p['news']['text']}]},'usage':{}}
        result=self.finished(self.r.submit(self.c,self.a,'u'))
        self.assertEqual(result['status'],'complete',result['error'])
        insight=result['result']['insight']
        self.assertEqual(insight['status'],'ready')
        self.assertEqual(insight['missing_context'],[])
        self.assertEqual(len(insight['why_for_company']),1)
        self.assertEqual(len(insight['actions']),1)
        self.assertIn('проверьте индекс',insight['actions'][0]['text'])
        self.assertEqual(result['result']['verification']['publication']['kept_claims'],2)
        self.assertEqual(result['result']['verification']['publication']['dropped_claims'],1)

class BankTests(unittest.TestCase):
    def test_dated_retrieval_excludes_future_old_and_undated(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bank.sqlite'
            with sqlite3.connect(p) as d:
                bank.schema(d)
                for did,date in [('now','2026-10-01'),('future','2027-01-01'),('old','2021-01-01'),('unknown',None)]:
                    d.execute('INSERT INTO bank_documents VALUES(?,?,?,?,?,1)',(did,did,'path','hash',date))
                    d.execute('INSERT INTO bank_passages VALUES(?,?,1,?,?)',(did,did,'Ключевая ставка влияет на ликвидность','ocr'))
                    d.execute('INSERT INTO bank_fts VALUES(?,?)',(did,'Ключевая ставка влияет на ликвидность'))
            results=bank.search(p,'ключевая ставка','2026-10-26T00:00:00+00:00',5)
            self.assertEqual([r['document_id'] for r in results],['now'])

if __name__=='__main__':unittest.main()
