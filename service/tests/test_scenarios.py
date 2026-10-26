import unittest
from service.scenarios import calculate
from service.tests import test_runtime as fixtures

class ScenarioTests(unittest.TestCase):
    setUp=fixtures.AgentTests.setUp
    tearDown=fixtures.AgentTests.tearDown
    def loan(self,**extra):return {'kind':'loan','currency':'RUB','principal':'1000000','days':'365','basis':365,'rate_type':'floating','benchmark_base':'14','benchmark_scenario':'12','spread':'2','acknowledge_assumptions':True,**extra}
    def test_interest_and_fixed_contract(self):
        result=calculate(self.loan());self.assertEqual(result['base'],'160000.00');self.assertEqual(result['scenario'],'140000.00');self.assertEqual(result['delta'],'-20000.00')
        result=calculate(self.loan(rate_type='fixed',fixed_rate='16'));self.assertEqual(result['delta'],'0.00')
    def test_invalid_numbers_and_no_implicit_assumptions(self):
        for extra in [{'principal':'NaN'},{'principal':'Infinity'},{'days':'1.5'},{'basis':True},{'currency':'unknown'},{'acknowledge_assumptions':False},{'spread':'-20'}]:
            with self.assertRaises(ValueError):calculate(self.loan(**extra))
    def test_fx_sign_and_input_provenance(self):
        result=calculate({'kind':'fx','currency':'USD','amount':'1000','rate_base':'90','rate_scenario':'100','flow':'expense','acknowledge_assumptions':True})
        self.assertEqual(result['delta'],'10000.00');self.assertEqual(result['cash_effect_delta'],'-10000.00')
        self.assertEqual(result['inputs']['foreign_currency'],'USD')
    def test_history_is_scoped(self):
        self.r.scenario(self.c,'u',self.loan())
        self.assertEqual(len(self.r.scenarios(self.c,'u')['items']),1)
        self.assertEqual(self.r.scenarios(self.c,'other')['items'],[])
        self.assertEqual(self.r.scenarios({**self.c,'source_record_id':'another'},'u')['items'],[])
