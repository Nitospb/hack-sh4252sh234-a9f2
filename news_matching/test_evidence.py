import json
import tempfile
import unittest
from pathlib import Path
from evidence import sentences,evidence_for_topic
from match_news import DEFAULT_POLICY,decide
from prepare_embeddings import load


def topic(obj,signal,sector='industry_17'):
    return dict(topic_id='bt_fixture',object=obj,signal=signal,object_keywords=[obj],sector_id=sector)


def evidence(obj,signal,text,sector='industry_17'):
    return evidence_for_topic(topic(obj,signal,sector),sentences({'title':text,'text':text}))


class EvidenceTests(unittest.TestCase):
    def test_price_increase_alias_and_inflection(self):
        self.assertIsNotNone(evidence('Дизельное топливо','рост отпускных цен','На бирже дизтопливо выросло в цене: рост цен составил 5%.'))

    def test_retail_fuel_price_is_not_producer_price(self):
        self.assertIsNone(evidence('Автомобильный бензин','рост отпускных цен','Бензин вырос в цене на АЗС.'))

    def test_negated_decline_is_not_decline(self):
        self.assertIsNone(evidence('Автомобильный бензин','снижение отпускных цен','На бирже бензин не подешевел.'))

    def test_asserted_price_decline_is_supported(self):
        self.assertIsNotNone(evidence('Автомобильный бензин','снижение отпускных цен','На бирже бензин подешевел.'))

    def test_unchanged_rate_does_not_become_increase(self):
        text='ЦБ сохранил ключевую ставку на фоне роста инфляции.'
        self.assertIsNone(evidence('Ключевая ставка','Повышение показателя',text,'crosscut_33'))
        self.assertIsNotNone(evidence('Ключевая ставка','Сохранение уровня показателя',text,'crosscut_33'))

    def test_slower_growth_is_not_decline_in_level(self):
        self.assertIsNone(evidence('ВВП','Снижение показателя','Темпы роста ВВП сократились.','crosscut_33'))

    def test_refusal_to_increase_is_not_increase(self):
        self.assertIsNone(evidence('Ключевая ставка','Повышение показателя','ЦБ отказался повысить ключевую ставку.','crosscut_33'))

    def test_steel_not_generic_became(self):
        self.assertIsNone(evidence('Сталь','рост объёма производства','Компании стали увеличивать объем производства.','industry_23'))

    def test_macro_forecast_model_is_not_necessarily_ai(self):
        self.assertIsNone(evidence('Прогнозная модель','Увеличение вычислительных затрат','Прогнозная модель потребовала увеличения вычислительных затрат.','crosscut_28'))

    def test_conditional_is_reviewed(self):
        result=evidence('Ключевая ставка','Повышение показателя','ЦБ может повысить ключевую ставку.','crosscut_33')
        self.assertIsNotNone(result)
        self.assertEqual(result['modality'],'conditional_or_forecast')
        candidate={**result,'embedding_cosine':.95,'reranker_logit':9.,'title_object_anchor':True}
        passed,reasons=decide(candidate,{'text':'текст','language':'ru'},DEFAULT_POLICY)
        self.assertFalse(passed);self.assertIn('conditional_or_forecast_needs_review',reasons)

    def test_object_and_event_must_be_in_same_sentence(self):
        r={'title':'Пшеница.','text':'Пшеница. Рост урожайности яблок составил 5%.'}
        self.assertIsNone(evidence_for_topic(topic('Пшеница','рост урожайности'),sentences(r)))

    def test_unicode_line_separator_inside_jsonl_string(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.jsonl';p.write_text(json.dumps({'text':'abc\u2028def'},ensure_ascii=False)+'\n'+json.dumps({'text':'second'})+'\n')
            self.assertEqual(len(load(p)),2)
            self.assertEqual(load(p)[0]['text'],'abc\u2028def')


if __name__=='__main__':unittest.main()
