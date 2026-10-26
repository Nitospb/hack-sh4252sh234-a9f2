import unittest
from evaluation.split import partition,audit

class SplitTests(unittest.TestCase):
    def test_cross_boundary_event_is_quarantined(self):
        rows=[{'article_id':aid,'event_group':group,'published_at':date+'T00:00:00Z'}
              for aid,group,date in [('a','story','2026-10-01'),('b','story','2026-10-15'),
                                     ('c','later','2026-10-22'),('d','early','2026-09-01')]]
        result=partition(rows,'2026-10-10T00:00:00Z','2026-10-20T00:00:00Z')
        self.assertEqual(result['counts'],{'train':1,'test':1})
        self.assertEqual(result['excluded_groups'][0]['article_ids'],['a','b'])
        self.assertTrue(audit(result['assignments'])['ok'])
        self.assertEqual(result,partition(list(reversed(rows)),'2026-10-10T00:00:00Z','2026-10-20T00:00:00Z'))

    def test_leakage_is_reported(self):
        rows=[{'article_id':'a','event_group':'same','split':s} for s in ('train','test')]
        result=audit(rows)
        self.assertFalse(result['ok']);self.assertEqual(result['leaking_articles'],['a'])
        self.assertEqual(result['leaking_groups'],['same'])

    def test_invalid_or_undated_data_fails_closed(self):
        with self.assertRaises(ValueError):partition([],'2026-10-01','2026-10-20T00:00:00Z')
        with self.assertRaises(ValueError):partition([],'2026-10-22T00:00:00Z','2026-10-20T00:00:00Z')
        row={'article_id':'a','event_group':'g','published_at':'2026-10-01T00:00:00Z'}
        with self.assertRaises(ValueError):partition([row,row],'2026-10-10T00:00:00Z','2026-10-20T00:00:00Z')
