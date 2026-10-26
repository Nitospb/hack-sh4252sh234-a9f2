import copy
import math
import unittest
from evaluation.score import evaluate


def bundle():
    return {'dataset_version':'v1','catalog_version':'sha','rubric_version':'1','split':'test','queries':[
        {'query_id':'q1','company_id':'c','source_record_id':'line:2','role':'director',
         'event_group':'event1','published_at':'2026-10-25T12:00:00Z',
         'rankings':{'baseline':['a','b'],'candidate':['b','a']},
         'judgments':[{'article_id':aid,'status':'adjudicated','origin':'human','reviewer':'expert',
                       'evidence':'Reviewed source and observed company exposure','relevance':grade,
                       'claims_supported':True} for aid,grade in [('a',3),('b',0)]]}]}

class MetricsTests(unittest.TestCase):
    def test_known_order_and_versions(self):
        result=evaluate(bundle(),2)
        self.assertEqual(result['adjudicated_human_pairs'],2)
        self.assertEqual(result['systems']['baseline']['metrics']['precision_at_k']['mean'],.5)
        self.assertEqual(result['systems']['baseline']['metrics']['ndcg_at_k_judged_pool']['mean'],1.)
        self.assertAlmostEqual(result['systems']['candidate']['metrics']['ndcg_at_k_judged_pool']['mean'],1/math.log2(3))
        self.assertIsNone(result['systems']['baseline']['metrics']['precision_at_k']['bootstrap_query_95pct'])

    def test_unknown_is_not_negative_and_machine_is_not_gold(self):
        data=bundle();data['queries'][0]['judgments'][0]['origin']='llm'
        result=evaluate(data,2)
        metrics=result['systems']['baseline']['metrics']
        self.assertIsNone(metrics['precision_at_k']['mean'])
        self.assertIsNone(metrics['ndcg_at_k_judged_pool']['mean'])
        self.assertEqual(metrics['precision_upper_bound']['mean'],.5)
        self.assertEqual(result['adjudicated_human_pairs'],1)

    def test_short_results_and_bad_inputs(self):
        data=bundle();data['queries'][0]['rankings']['baseline']=['a']
        self.assertEqual(evaluate(data,2)['systems']['baseline']['metrics']['precision_at_k']['mean'],.5)
        for change in ('duplicate','grade','timezone','evidence'):
            data=copy.deepcopy(bundle());q=data['queries'][0]
            if change=='duplicate':q['rankings']['baseline']=['a','a']
            elif change=='grade':q['judgments'][0]['relevance']=True
            elif change=='timezone':q['published_at']='2026-10-25'
            else:q['judgments'][0]['evidence']=''
            with self.assertRaises(ValueError):evaluate(data)

    def test_reproducibility(self):
        data=bundle();q=copy.deepcopy(data['queries'][0]);q['query_id']='q2';data['queries'].append(q)
        self.assertEqual(evaluate(data,2),evaluate(data,2))
