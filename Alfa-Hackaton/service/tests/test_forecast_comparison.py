import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from service import bank


class ForecastComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.assets=Path(self.temp.name)/'assets.sqlite'
        with sqlite3.connect(self.assets) as db:bank.schema(db)
        self.old=self.add('old','2026-08-01','Ожидаем инфляцию России на конец 2026 года 6%.')
    def tearDown(self):self.temp.cleanup()
    def add(self,id,date,text,method='pdf_text'):
        with sqlite3.connect(self.assets) as db:
            db.execute('INSERT INTO bank_documents VALUES(?,?,?,?,?,?)',(id,id+'.pdf','unused','hash',date,1))
            db.execute('INSERT INTO bank_passages VALUES(?,?,?,?,?)',(id+'_p1',id,1,text,method))
            db.execute('INSERT INTO bank_fts VALUES(?,?)',(id+'_p1',text))
        return {'id':id+'_p1','document_id':id,'document_title':id+'.pdf','published_at':date,'page':1,'text':text,'method':method}
    def test_matching_later_forecast_is_companion_without_changing_retrieval(self):
        newer=self.add('new','2026-09-01','Ожидаем инфляцию России на конец 2026 года 7%.')
        original=[dict(self.old)]
        result=bank.compare_forecasts(self.assets,original,'2026-10-26')
        self.assertEqual(original,[self.old]);self.assertTrue(result['retrieval_order_unchanged'])
        self.assertEqual([p['id'] for p in result['additional_passages']],[newer['id']])
        pair=result['report']['comparisons'][0]
        self.assertEqual(pair['status'],'later_forecast')
        self.assertEqual(result['additional_passages'][0]['retrieval_methods'],['forecast_context_companion'])
    def test_wrong_scope_future_old_ocr_and_external_forecaster_do_not_expand_sources(self):
        for id,date,text,method in [
            ('wrong-year','2026-09-01','Ожидаем инфляцию России на конец 2027 года 7%.','pdf_text'),
            ('wrong-country','2026-09-01','Ожидаем инфляцию США на конец 2026 года 7%.','pdf_text'),
            ('wrong-definition','2026-09-01','Ожидаем среднегодовую инфляцию России в 2026 году 7%.','pdf_text'),
            ('future','2026-12-01','Ожидаем инфляцию России на конец 2026 года 7%.','pdf_text'),
            ('too-old','2025-01-01','Ожидаем инфляцию России на конец 2026 года 7%.','pdf_text'),
            ('ocr','2026-09-01','Ожидаем инфляцию России на конец 2026 года 7%.','tesseract-unverified'),
            ('external','2026-09-01','Банк России прогнозирует инфляцию России на конец 2026 года 7%.','pdf_text')]:self.add(id,date,text,method)
        result=bank.compare_forecasts(self.assets,[self.old],'2026-10-26')
        self.assertEqual(result['additional_passages'],[])
    def test_historical_number_and_same_day_differences_do_not_become_new_forecast(self):
        self.add('history','2026-09-01','Ранее ожидали инфляцию России на конец 2026 года 7%.')
        self.add('same-day','2026-08-01','Ожидаем инфляцию России на конец 2026 года 7%.')
        self.assertEqual(bank.compare_forecasts(self.assets,[self.old],'2026-10-26')['additional_passages'],[])
    def test_limit_and_empty_search_do_not_add_unrelated_bank_materials(self):
        self.add('new','2026-09-01','Ожидаем инфляцию России на конец 2026 года 7%.')
        self.assertEqual(bank.compare_forecasts(self.assets,[],'2026-10-26')['additional_passages'],[])
        self.assertEqual(bank.compare_forecasts(self.assets,[self.old],'2026-10-26',max_extra=0)['additional_passages'],[])
