import unittest
from assign_company_interests import applicable_aspects, build_catalog, active


class CompanyInterestsTests(unittest.TestCase):
    def setUp(self):
        self.rules={'46':{'aspects':[{'key':f'a{i}','name':f'Аспект {i}','why':'Связь с деятельностью'} for i in range(12)]}}
        self.row={'MAINOKVED_CODE':'46.51','MAINOKVED_NAME':'Оптовая торговля компьютерами'}

    def test_base_minimum_and_product_flag_evidence(self):
        self.assertEqual(len(applicable_aspects(self.row,self.rules)),12)
        r={**self.row,'CL_PRODUCT_LOA_MARK':'1.0','FTS_FLAG':'0.0'}
        aspects=applicable_aspects(r,self.rules)
        self.assertEqual(len(aspects),14)
        self.assertEqual({a.get('required_flag') for a in aspects[12:]},{'CL_PRODUCT_LOA_MARK'})
        self.assertFalse(active('0.0'))
        self.assertFalse(active(''))

    def test_exact_activity_context_is_preserved(self):
        other={**self.row,'MAINOKVED_CODE':'46.52','MAINOKVED_NAME':'Оптовая торговля электронным оборудованием'}
        catalog, mapping=build_catalog([self.row,other],self.rules)
        self.assertEqual(len(catalog),24)
        self.assertFalse(set(mapping[('46.51',self.row['MAINOKVED_NAME'])]) & set(mapping[('46.52',other['MAINOKVED_NAME'])]))
        self.assertTrue(all(t['activity_name'] in t['name'] for t in catalog.values()))

    def test_repeated_activity_does_not_duplicate_topics(self):
        catalog,mapping=build_catalog([self.row,self.row],self.rules)
        self.assertEqual(len(catalog),12)
        self.assertEqual(len(next(iter(mapping.values()))),12)

    def test_different_flags_union_catalog_without_losing_base(self):
        catalog,mapping=build_catalog([self.row,{**self.row,'FTS_FLAG':'1'}],self.rules)
        self.assertEqual(len(catalog),14)
        self.assertEqual(sum(t['required_flag']=='FTS_FLAG' for t in catalog.values()),2)


if __name__=='__main__':
    unittest.main()
