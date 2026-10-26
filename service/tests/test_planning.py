import unittest
from service.planning import plan


def context(loan='1',fts='1'):
    return {'facts':[{'id':'loan','field':'CL_PRODUCT_LOA_MARK','value':loan,'evidence_level':'confirmed'},
                     {'id':'trade','field':'FTS_FLAG','value':fts,'evidence_level':'confirmed'},
                     {'id':'sector','field':'MAINOKVED_NAME','value':'Производство','evidence_level':'confirmed'}]}


class PlanningTests(unittest.TestCase):
    def test_same_event_different_observed_exposures(self):
        article={'title':'Ставка и валютные расчёты изменились','text':'Новые условия кредита и импорта.'}
        active=plan(article,context(),'','treasurer')
        absent=plan(article,context('0','0'),'','treasurer')
        self.assertIn('loan',active['observed_fact_ids']);self.assertIn('trade',active['observed_fact_ids'])
        self.assertNotIn('loan',absent['observed_fact_ids']);self.assertNotIn('trade',absent['observed_fact_ids'])
        self.assertTrue(all(p['conditional'] for p in active['impact_paths']))
        self.assertLessEqual(len(active['priority_questions']),3)

    def test_role_changes_priority_and_question_changes_tools(self):
        article={'title':'Налоги, кредит и ставка: новые правила','text':'Изменения затрагивают отчётность.'}
        treasurer=plan(article,context(),'','treasurer')
        accountant=plan(article,context(),'','accountant')
        self.assertEqual(treasurer['mechanisms'][0],'financing')
        self.assertEqual(accountant['mechanisms'][0],'tax')
        clarify=plan(article,context(),'Какие параметры нужно уточнить?','treasurer')
        self.assertFalse(clarify['needs_bank_search']);self.assertNotIn('search_bank',clarify['tools'])
        bank=plan(article,context(),'Какие параметры уточнить согласно прогнозу банка?','treasurer')
        self.assertTrue(bank['needs_bank_search'])

    def test_hypothesis_is_not_promoted_to_observed_fact(self):
        data=context();data['facts'][0]['evidence_level']='candidate'
        result=plan({'title':'Снижение ставки','text':''},data,'','finance')
        self.assertNotIn('loan',result['observed_fact_ids'])
        resignation=plan({'title':'Отставка руководителя','text':''},context(),'','director')
        self.assertNotIn('financing',resignation['mechanisms'])
