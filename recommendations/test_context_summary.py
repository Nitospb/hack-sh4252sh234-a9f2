import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from context_summary import broad_activity, business_context

class ContextSummaryTests(unittest.TestCase):
    def test_general_activity_and_missing_data(self):
        self.assertEqual(broad_activity('01.11'),'Сельское хозяйство')
        self.assertEqual(broad_activity('62.01'),'IT и технологии')
        self.assertEqual(broad_activity(None),'Деятельность не указана')
        with tempfile.TemporaryDirectory() as folder:
            result=business_context(Path(folder)/'missing.sqlite',{'okved':'01.11','source_record_id':'record'})
            self.assertEqual(result['partner_sectors'],[])
            self.assertFalse((Path(folder)/'missing.sqlite').exists())

    def test_partners_are_scoped_and_payment_sectors_come_first(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'assets.sqlite'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE relationships(record_id TEXT,payload TEXT)')
                for record,code,kind,share in [('record','62.01','same_group',None),('record','49.41','outgoing_payment',.7),('record','46.21','incoming_payment',.5),('other','64.19','incoming_payment',1)]:
                    db.execute('INSERT INTO relationships VALUES(?,?)',(record,json.dumps({'related_okved':code,'kind':kind,'direction_amount_share':share,'related_company_id':code})))
            result=business_context(path,{'okved':'01.11','source_record_id':'record'})
            self.assertEqual([s['label'] for s in result['partner_sectors']],['Транспорт и логистика','Торговля'])
            self.assertEqual(result['partner_sectors'][0]['kinds'],['outgoing_payment'])
            self.assertEqual(result['partner_sectors'][0]['company_count'],1)
