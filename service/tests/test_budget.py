from datetime import datetime,timezone
import json
import os
import threading
import unittest
from unittest.mock import patch
from service.tests import test_runtime as fixtures
from service import budget


class BudgetTests(unittest.TestCase):
    setUp=fixtures.AgentTests.setUp
    tearDown=fixtures.AgentTests.tearDown
    finished=fixtures.AgentTests.finished

    def test_new_job_requires_draft_and_verification_before_any_paid_work(self):
        with patch.dict(os.environ,{'ALFA_MAX_CALLS_PER_DAY':'1'}):
            self.assertEqual(self.r.availability()['reason'],'calls')
            with self.assertRaisesRegex(RuntimeError,'лимит'):self.r.submit(self.c,self.a,'u')
        self.assertEqual(self.generated,0)
        with self.r.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM runs').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM job_budgets').fetchone()[0],0)

    def test_cached_completed_answer_remains_available_at_daily_limit(self):
        with patch.dict(os.environ,{'ALFA_MAX_CALLS_PER_DAY':'2'}):
            job=self.r.submit(self.c,self.a,'u');result=self.finished(job)
            self.assertEqual(result['status'],'complete',result['error'])
            self.assertFalse(self.r.availability()['available'])
            self.assertEqual(self.r.submit(self.c,self.a,'u')['run_id'],job['run_id'])
        self.assertEqual(self.generated,1)

    def test_parallel_admission_cannot_spend_verification_reserve(self):
        entered=threading.Event();release=threading.Event();generate=self.r.generator
        def blocked(payload):entered.set();release.wait(3);return generate(payload)
        self.r.generator=blocked
        with patch.dict(os.environ,{'ALFA_MAX_CALLS_PER_DAY':'3'}):
            first=self.r.submit(self.c,self.a,'u')
            try:
                self.assertTrue(entered.wait(2))
                self.assertEqual(self.r.availability()['reason'],'reserved')
                with self.assertRaises(RuntimeError):self.r.submit(self.c,self.a,'u',question='Другой разбор')
            finally:release.set()
            result=self.finished(first);self.assertEqual(result['status'],'complete',result['error'])
        with self.r.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM job_budgets').fetchone()[0],0)

    def test_usage_unknown_errors_and_reset_have_same_policy_for_health_and_calls(self):
        at=datetime(2026,10,26,22,0,tzinfo=timezone.utc)
        with self.r.db() as db:
            db.execute('INSERT INTO calls VALUES(?,?,?,?,?,?)',('used','run','2026-10-26','complete',json.dumps({'total_tokens':250000}),'stamp'))
            db.execute('INSERT INTO calls VALUES(?,?,?,?,?,?)',('unknown','run','2026-10-26','error_unknown_usage',None,'stamp'))
            with patch.dict(os.environ,{'ALFA_MAX_TOKENS_PER_DAY':'300000'}):
                status=budget.snapshot(db,at=at);self.assertFalse(status['available']);self.assertEqual(status['reason'],'tokens')
                self.assertEqual(status['resets_at'],'2026-10-27T00:00:00+00:00')
                self.assertTrue(budget.snapshot(db,at=datetime(2026,10,27,tzinfo=timezone.utc))['available'])

    def test_gateway_block_and_configuration_do_not_leak_ledger_details(self):
        today=datetime.now(timezone.utc).date().isoformat()
        with self.r.db() as db:db.execute("INSERT INTO runtime_meta VALUES('budget_blocked_day',?)",(today,))
        status=self.r.availability();self.assertEqual(status['reason'],'gateway_budget')
        self.assertFalse({'calls','tokens','usage','day'} & status.keys())
        with patch.dict(os.environ,{'ALFA_MAX_CALLS_PER_DAY':'invalid'}):self.assertEqual(self.r.availability()['reason'],'configuration')

    def test_failed_submission_releases_future_budget(self):
        self.r.pool.shutdown(wait=True)
        with self.assertRaises(RuntimeError):self.r.submit(self.c,self.a,'u')
        with self.r.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM job_budgets').fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM runs WHERE status='queued'").fetchone()[0],0)

    def test_unknown_success_usage_keeps_conservative_token_reserve(self):
        at=datetime(2026,10,26,tzinfo=timezone.utc)
        with self.r.db() as db:
            db.execute('INSERT INTO calls VALUES(?,?,?,?,?,?)',('unknown-success','run','2026-10-26','complete','{}','stamp'))
            with patch.dict(os.environ,{'ALFA_MAX_TOKENS_PER_DAY':'60000'}):self.assertEqual(budget.snapshot(db,at=at)['reason'],'tokens')
            db.execute('UPDATE calls SET usage=?',(json.dumps({'total_tokens':-1000}),))
            self.assertEqual(budget.snapshot(db,at=at)['reason'],'ledger')

    def test_optional_refinement_keeps_already_verified_assessment_when_budget_ends(self):
        from service.verification import claim_items
        self.r.verifier=lambda p,d:{'verification':{'verdict':'retrieve','event_verdict':'supported','bank_verdict':'not_present',
            'claim_reviews':[{'claim_id':r['claim_id'],'verdict':'supported','reason':'Поддержано первоисточником'} for r in claim_items(d)],
            'context_questions':[],'issues':[],'query':'Дополнительное исследование банка',
            'quotes':[{'source_id':p['news']['id'],'quote':p['news']['text']}]},'usage':{'total_tokens':8}}
        with patch.dict(os.environ,{'ALFA_MAX_CALLS_PER_DAY':'2'}):
            result=self.finished(self.r.submit(self.c,self.a,'u'))
            self.assertEqual(result['status'],'complete',result['error'])
            self.assertEqual(result['result']['insight']['status'],'ready')
            self.assertTrue(result['result']['insight']['why_for_company'])
            self.assertIn('refinement_skipped',[s['tool'] for s in result['steps']])
            self.assertNotIn('search_bank_refined',[s['tool'] for s in result['steps']])
            self.assertEqual(self.r.metrics('c','u')['llm_calls'],2)

    def test_schema_repair_is_not_paid_without_room_for_its_verifier(self):
        from jsonschema.exceptions import ValidationError
        calls=[]
        def invalid(payload):calls.append(1);raise ValidationError('Bad draft',validator='maxItems')
        self.r.generator=invalid
        with patch.dict(os.environ,{'ALFA_MAX_CALLS_PER_DAY':'2'}):
            result=self.finished(self.r.submit(self.c,self.a,'u'))
            self.assertEqual(result['status'],'error');self.assertEqual(len(calls),1)
            self.assertNotIn('repair_contract',[s['tool'] for s in result['steps']])
