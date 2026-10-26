import copy
import unittest
from service.verification import apply,claim_items


def sample():
    news='Банк России сохранил ключевую ставку на уровне четырнадцати процентов.'
    bank='Стоимость заимствований зависит от ключевой ставки и условий финансирования.'
    payload={'news':{'id':'news','text':news},'company_facts':[{'id':'loan','evidence_level':'confirmed'}],
             'bank_passages':[{'id':'bank_1','text':bank}]}
    conditional={'text':'Если ставка плавающая, проверьте индекс и дату пересмотра.',
                 'conditional':True,'company_fact_ids':['loan'],'source_ids':['news']}
    draft={'status':'needs_context','title':'Анализ','event':{'text':news,'source_ids':['news']},
           'why_for_company':[copy.deepcopy(conditional)],'actions':[copy.deepcopy(conditional),
              {**conditional,'text':'Расходы точно вырастут на миллион рублей.','conditional':False}],
           'risks':[],'opportunities':[],'ai_application':[],
           'bank_view':{'summary':bank,'source_ids':['bank_1'],'applicability':'Если есть применимые обязательства, проверьте договор.'},
           'missing_context':['Какой индекс и дата пересмотра предусмотрены договором?'],'limitations':[]}
    check={'verdict':'needs_context','event_verdict':'supported','bank_verdict':'supported',
           'claim_reviews':[{'claim_id':r['claim_id'],'verdict':'unsupported' if r['claim_id']=='actions/1' else 'supported',
                            'reason':'Сумма не подтверждена' if r['claim_id']=='actions/1' else 'Подтверждённое условное действие'} for r in claim_items(draft)],
           'context_questions':[],'quotes':[{'source_id':'news','quote':news},{'source_id':'bank_1','quote':bank}]}
    return draft,check,payload


class PartialVerificationTests(unittest.TestCase):
    def test_unknown_amount_drops_only_false_calculation_and_keeps_bank(self):
        draft,check,payload=sample();result,quotes,audit=apply(draft,check,payload)
        self.assertEqual(len(result['why_for_company']),1);self.assertEqual(len(result['actions']),1)
        self.assertTrue(result['actions'][0]['conditional'])
        self.assertIsNotNone(result['bank_view']);self.assertTrue(audit['bank_published'])
        self.assertEqual(result['status'],'ready');self.assertEqual(result['missing_context'],[]);self.assertEqual(audit['kept_claims'],2)
        self.assertEqual(audit['dropped_claims'],1)
        self.assertEqual(len(draft['actions']),2) # No in-place mutation of persisted draft.

    def test_wrong_bank_quote_does_not_erase_news_grounded_claims(self):
        draft,check,payload=sample();check['quotes'][1]['quote']='Несуществующая дословная цитата'
        result,_,audit=apply(draft,check,payload)
        self.assertIsNone(result['bank_view']);self.assertEqual(audit['invalid_quotes'],1)
        self.assertEqual(len(result['actions']),1);self.assertEqual(len(result['why_for_company']),1)

    def test_missing_duplicate_or_unquoted_reviews_fail_closed_per_claim(self):
        draft,check,payload=sample();check['claim_reviews'].append(check['claim_reviews'][0])
        result,_,audit=apply(draft,check,payload)
        self.assertEqual(result['why_for_company'],[]);self.assertEqual(len(result['actions']),1)
        self.assertEqual(audit['claims'][0]['review_verdict'],'missing_or_duplicate')
        check['quotes']=[]
        result,_,audit=apply(draft,check,payload)
        self.assertEqual(audit['kept_claims'],0);self.assertIsNone(result['bank_view'])

    def test_no_automatic_promotion_of_unconfirmed_facts_or_false_claims(self):
        draft,check,payload=sample();payload['company_facts'][0]['evidence_level']='candidate'
        draft['why_for_company'][0]['conditional']=False
        result,_,_=apply(draft,check,payload)
        self.assertEqual(result['why_for_company'],[])
        self.assertEqual(len(result['actions']),1);self.assertTrue(result['actions'][0]['conditional'])

    def test_ready_remains_ready_when_every_claim_is_supported(self):
        draft,check,payload=sample();draft['actions'].pop();draft['status']='ready';draft['missing_context']=[]
        check['claim_reviews'].pop();check['verdict']='supported'
        result,_,audit=apply(draft,check,payload)
        self.assertEqual(result['status'],'ready');self.assertEqual(audit['dropped_claims'],0)

    def test_confirmed_irrelevance_does_not_request_pointless_clarification(self):
        draft,check,payload=sample()
        for key in ('why_for_company','actions'):draft[key]=[]
        draft.update(status='not_relevant',bank_view=None,missing_context=[])
        check.update(verdict='supported',claim_reviews=[],bank_verdict='not_present')
        result,_,_=apply(draft,check,payload)
        self.assertEqual(result['status'],'not_relevant');self.assertEqual(result['missing_context'],[])

    def test_generic_floating_loan_condition_does_not_establish_numeric_benchmark(self):
        draft,check,payload=sample()
        draft['actions'][0]['text']='Если есть плавающий кредит, ставка компании составит 14% + спред.'
        result,_,audit=apply(draft,check,payload)
        self.assertEqual(result['actions'],[])
        self.assertEqual(len(result['why_for_company']),1)
        draft['actions'][0]['text']='Если договор привязан к ключевой ставке, сценарий 14% + спред требует проверки даты пересмотра.'
        result,_,_=apply(draft,check,payload)
        self.assertEqual(len(result['actions']),1)

    def test_only_a_critical_question_blocks_otherwise_useful_estimate(self):
        draft,check,payload=sample();payload['question']='Рассчитай точную сумму платежа';check['context_questions']=['Какой из двух взаимоисключающих видов операции действительно применим?']
        result,_,_=apply(draft,check,payload)
        self.assertEqual(result['status'],'needs_context');self.assertEqual(result['missing_context'],check['context_questions'])
        self.assertEqual(len(result['actions']),1)

    def test_explicit_request_for_parameters_preserves_the_requested_answer(self):
        draft,check,payload=sample();payload['question']='Какие параметры нужно уточнить?'
        result,_,_=apply(draft,check,payload)
        self.assertEqual(result['status'],'ready');self.assertEqual(result['missing_context'],draft['missing_context'])

    def test_generic_estimate_does_not_require_confirming_every_scenario_input(self):
        draft,check,payload=sample();payload['question']='Как событие повлияет на бизнес?'
        check['context_questions']=['Есть ли кредит с плавающей ставкой?']
        result,_,audit=apply(draft,check,payload)
        self.assertEqual(result['status'],'ready');self.assertEqual(result['missing_context'],[])
        self.assertTrue(audit['assessment_available'])

    def test_missing_source_support_is_not_assigned_to_the_customer(self):
        draft,check,payload=sample();check['quotes']=[]
        result,_,audit=apply(draft,check,payload)
        self.assertEqual(audit['kept_claims'],0)
        self.assertEqual(result['status'],'needs_context')
        self.assertEqual(result['missing_context'],[])
        self.assertTrue(any('задачей сервиса' in line for line in result['limitations']))
