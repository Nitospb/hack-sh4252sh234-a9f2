import unittest
from pipeline.facts import extract,compare,period


def source(id,text,date='2026-10-26T12:00:00Z',**kw):return {'id':id,'text':text,'title':'','published_at':date,**kw}

class FactTests(unittest.TestCase):
    def test_equal_forecast_and_result_remain_different_statement_kinds(self):
        rows=[source('a','Прогноз инфляции России на 2025 год: 6%.','2024-12-01'),
              source('b','Инфляция России за 2025 год составила 6%.')]
        self.assertEqual(compare(rows)['comparisons'][0]['status'],'forecast_vs_reported')

    def test_headline_year_does_not_fill_later_paragraph_period(self):
        rows=extract(source('a','Выручка ПАО «Север» составила 1 млрд рублей.\n\nЧистая прибыль ПАО «Юг» составила 2 млрд рублей.',title='Итоги 2025 года'))
        self.assertEqual(rows[0]['period']['key'],'Y:2025')
        self.assertIsNone(rows[1]['period'])

    def test_explicit_money_scales_are_equivalent_and_quotes_are_exact(self):
        a=source('a','Выручка ПАО «Север» за 2025 год составила 1,2 млрд рублей.')
        b=source('b','Выручка ПАО «Север» за 2025 год составила 1 200 млн рублей.')
        report=compare([a,b]);self.assertEqual(report['comparisons'][0]['status'],'same_value')
        self.assertEqual(report['facts'][0]['value_min'],'1200000000')
        for f in report['facts']:
            text=a['text'] if f['source_id']=='a' else b['text']
            self.assertEqual(text[f['start']:f['end']],f['raw'])
            self.assertEqual(text[f['quote_start']:f['quote_end']],f['quote'])

    def test_different_companies_periods_metrics_and_units_do_not_create_conflict(self):
        a=source('a','Выручка ПАО «Север» за 2025 год составила 1 млрд рублей.')
        for text in ['Выручка ПАО «Юг» за 2025 год составила 2 млрд рублей.',
                     'Выручка ПАО «Север» за 2024 год составила 2 млрд рублей.',
                     'Чистая прибыль ПАО «Север» за 2025 год составила 2 млрд рублей.',
                     'Выручка ПАО «Север» за 2025 год составила 2 млрд долларов.']:
            self.assertEqual(compare([a,source('b',text)])['comparisons'],[],text)

    def test_percent_and_percentage_points_are_not_the_same_quantity(self):
        a=source('a','Инфляция России за 2025 год составила 6%.')
        b=source('b','Инфляция России за 2025 год изменилась на 2 п.п.')
        self.assertEqual(compare([a,b])['comparisons'],[])

    def test_different_definitions_and_scenarios_are_kept_separate(self):
        a=source('a','Прогноз инфляции России на конец 2026 года: 6%, базовый сценарий.')
        for text in ['Прогноз среднегодовой инфляции России на 2026 год: 7%, базовый сценарий.',
                     'Прогноз инфляции России на конец 2026 года: 8%, пессимистический сценарий.']:
            self.assertEqual(compare([a,source('b',text)])['comparisons'],[])

    def test_ranges_overlap_without_becoming_contradictions(self):
        a=source('a','Прогноз инфляции России на 2026 год: 6–7%.')
        b=source('b','Прогноз инфляции России на 2026 год: 6,5%.')
        self.assertEqual(compare([a,b])['comparisons'][0]['status'],'overlapping_ranges')

    def test_own_newer_forecast_has_explicit_preference_but_other_author_does_not(self):
        a=source('a','Ожидаем инфляцию России на конец 2026 года 6%.','2026-09-01',owner='alfa_bank')
        b=source('b','Ожидаем инфляцию России на конец 2026 года 7%.','2026-10-01',owner='alfa_bank')
        report=compare([a,b]);pair=report['comparisons'][0]
        self.assertEqual(pair['status'],'later_forecast');self.assertIsNotNone(pair['preferred_fact_id'])
        other=source('c','Банк России прогнозирует инфляцию России на конец 2026 года 8%.','2026-10-02',owner='alfa_bank')
        pair=compare([a,other])['comparisons'][0];self.assertEqual(pair['status'],'different_forecasts');self.assertIsNone(pair['preferred_fact_id'])

    def test_later_report_quoting_external_author_does_not_silently_replace_forecast(self):
        a=source('a','Банк России прогнозирует инфляцию России в 2026 году 6%.','2026-09-01',owner='alfa_bank')
        b=source('b','Банк России прогнозирует инфляцию России в 2026 году 7%.','2026-10-01',owner='alfa_bank')
        self.assertIsNone(compare([a,b])['comparisons'][0]['preferred_fact_id'])

    def test_old_number_in_explicit_revision_does_not_become_current(self):
        row=source('a','Альфа-Банк пересмотрел прогноз инфляции России на 2026 год до 7% с 6%.')
        facts=extract(row);self.assertTrue(facts[0]['comparable']);self.assertFalse(facts[1]['comparable'])
        self.assertEqual(facts[1]['value_role'],'previous')

    def test_unknown_subject_currency_or_period_stays_unqualified(self):
        for text in ['Выручка составила 2 млрд.', 'Инфляция составила 6%.','Рост ВВП в 2025 и 2026 годах: 1% и 2%.']:
            self.assertFalse(any(f['comparable'] for f in extract(source('a',text))),text)

    def test_nearest_preceding_metric_wins_over_following_metric(self):
        row=source('a','Банк России: ключевая ставка 14%, инфляция России за 2025 год 6%.')
        facts=extract(row);self.assertEqual([f['metric'] for f in facts],['policy_rate','inflation'])

    def test_supported_period_forms_and_ambiguous_narrow_periods(self):
        self.assertEqual(period('первый квартал 2026 года')['key'],'Q:2026-1')
        self.assertEqual(period('III квартал 2026')['key'],'Q:2026-3')
        self.assertEqual(period('за 9 месяцев 2026 года')['key'],'YTD:2026-9')
        self.assertEqual(period('за сентябрь 2026')['key'],'M:2026-09')
        self.assertIsNone(period('за неизвестный квартал 2026 года'))
        self.assertEqual(period('маржа 2026')['key'],'Y:2026')

    def test_ocr_and_same_document_pages_do_not_establish_revision(self):
        a=source('a','Ожидаем инфляцию России на конец 2026 года 6%.','2026-09-01',owner='alfa_bank',method='tesseract-rus-eng-unverified')
        b=source('b','Ожидаем инфляцию России на конец 2026 года 7%.','2026-10-01',owner='alfa_bank')
        self.assertEqual(compare([a,b])['comparisons'],[])
        a.pop('method');a['document_id']=b['document_id']='one-pdf'
        self.assertEqual(compare([a,b])['comparisons'],[])

    def test_unknown_forecast_definition_never_gets_automatic_preference(self):
        a=source('a','Ожидаем инфляцию России в 2026 году 6%.','2026-09-01',owner='alfa_bank')
        b=source('b','Ожидаем инфляцию России в 2026 году 7%.','2026-10-01',owner='alfa_bank')
        self.assertIsNone(compare([a,b])['comparisons'][0]['preferred_fact_id'])

    def test_wrapped_lines_abbreviations_and_relative_horizons(self):
        row=source('a','Ожидаем инфляцию России на конец\n2026 г. в диапазоне 6–7%.',owner='alfa_bank')
        f=extract(row)[0];self.assertTrue(f['comparable']);self.assertEqual(f['period']['key'],'Y:2026')
        row=source('b','Ожидаем инфляцию России до конца года 6%.','2026-09-01',owner='alfa_bank')
        self.assertEqual(extract(row)[0]['period']['key'],'Y:2026')

    def test_incomplete_reported_period_is_not_a_finished_outcome(self):
        row=source('a','ВВП России за 2026 год вырос на 2%.','2026-10-26')
        self.assertIn('period_not_complete',extract(row)[0]['missing_context'])

    def test_month_ranges_and_rolling_windows_do_not_become_single_month(self):
        self.assertEqual(period('январь–сентябрь 2026 года')['key'],'YTD:2026-9')
        self.assertIsNone(period('за последние 9 месяцев 2026 года'))
        a=source('a','Выручка ПАО «Север» за январь–сентябрь 2025 года составила 1 млрд рублей.')
        b=source('b','Выручка ПАО «Север» за сентябрь 2025 года составила 2 млрд рублей.')
        self.assertEqual(compare([a,b])['comparisons'],[])

    def test_multiple_frequencies_in_one_clause_do_not_get_assigned_by_guess(self):
        text='Инфляция России за сентябрь 2025 года составила 1% м/м и 6% г/г.'
        self.assertTrue(all(not f['comparable'] for f in extract(source('a',text))))

    def test_comparison_is_pure_and_model_ids_are_short(self):
        from copy import deepcopy
        from pipeline.facts import model_context,remap_sources
        sources=[source('a','Выручка ПАО «Север» за 2025 год составила 1 млрд рублей.'),source('b','Выручка ПАО «Север» за 2025 год составила 2 млрд рублей.')]
        original=deepcopy(sources);report=compare(sources);model=remap_sources(model_context(report),{'a':'news','b':'related_1'})
        self.assertEqual(sources,original);self.assertEqual(report,compare(sources))
        self.assertEqual(model['facts'][0]['id'],'statement_1');self.assertEqual(model['facts'][0]['source_id'],'news')

    def test_textual_revision_is_not_a_verified_number_or_automatic_priority(self):
        row=source('a','Если ранее мы ожидали снижения ключевой ставки до 13%, то теперь мы ожидаем её сохранения на текущем значении 14% до конца года.',owner='alfa_bank',method='tesseract-unverified')
        report=compare([row]);self.assertEqual(report['comparisons'],[])
        notice=report['revision_notices'][0];self.assertEqual(notice['numeric_verification'],'not_verified')
        self.assertEqual(row['text'][notice['start']:notice['end']],notice['quote'])

    def test_headline_does_not_relabel_stock_index_or_price_growth_as_policy_rate(self):
        row=source('a','Совет директоров Банка России 23 октября 2026 года сохранил ключевую ставку на уровне 14%. По оценке ЦБ, рост цен находится в диапазоне 5–6%. Индекс МосБиржи подрос на 6%, на пике — на 9%.',title='Банк России сохранил ключевую ставку 14%')
        facts=extract(row)
        self.assertEqual([(f['raw'],f['metric']) for f in facts],[('14%','policy_rate'),('5–6%',None),('6%',None),('9%',None)])
        other=source('b','Банк России сохранил ключевую ставку 14%.')
        self.assertFalse(any(p['status']=='reported_difference' for p in compare([row,other])['comparisons']))

    def test_metric_does_not_cross_an_intervening_quantity_into_a_new_indicator(self):
        row=source('a','Банк России сохранил ключевую ставку 14%, дефицит бюджета достиг 6%.')
        facts=extract(row);self.assertEqual([f['metric'] for f in facts],['policy_rate',None])

    def test_previous_actual_rate_is_not_compared_as_current(self):
        row=source('a','Банк России снизил ключевую ставку с 15% до 14%.')
        facts=extract(row);self.assertEqual(facts[0]['value_role'],'previous');self.assertFalse(facts[0]['comparable'])
        self.assertEqual(facts[1]['metric'],'policy_rate');self.assertTrue(facts[1]['comparable'])
