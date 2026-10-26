"""Inspectable event-to-exposure plans; pathways are conditional hypotheses, never facts."""
import re

# name, event vocabulary, bank query, observed fields, transmission, required inputs
MECHANISMS=(
 ('financing',r'\b(?:ставк|кредит|рефинанс|облигац|долгов|ликвид)',
  'ключевая ставка ликвидность финансирование',('CL_PRODUCT_LOA_MARK','CL_PRODUCT_DEP_MARK','CL_PRODUCT_GAR_MARK'),
  'Изменение стоимости денег может повлиять на проценты и рефинансирование при применимых условиях договора.',
  ('Есть ли плавающая ставка: какой индекс, спред и дата пересмотра?', 'Каковы остаток долга, валюта и срок погашения?')),
 ('foreign_trade',r'валют|экспорт|импорт|тамож|санкц|междунар',
  'валютный курс экспорт импорт расчеты',('FTS_FLAG','FTS_COUNTRY_NAME'),
  'Курс и ограничения расчётов могут изменить стоимость или сроки внешнеторгового потока при наличии действующих контрактов.',
  ('В какой валюте и стране действует контракт, каковы сумма и дата платежа?', 'Есть ли естественное покрытие или хеджирование валютного потока?')),
 ('demand',r'спрос|потребл|розниц|продаж|инфляц|\bцен',
  'потребление спрос инфляция',('MAINOKVED_NAME','REGION'),
  'Изменение спроса или цен может передаться в продажи и маржу в зависимости от клиентского сегмента и возможности менять цены.',
  ('Какова доля затронутого товара и сегмента в продажах?', 'Как меняются закупочная цена, отпускная цена и объём продаж?')),
 ('tax',r'\bналог|\bндс\b|отч[её]т|страхов.{0,8}взнос',
  'налоги бюджет компании НДС',('MAINOKVED_NAME','ORG_TYPE'),
  'Новая норма влияет на расчёт и сроки обязательств только если распространяется на режим и операции компании.',
  ('Какой налоговый режим и какая операция затронуты?', 'Когда норма вступает в силу и предусмотрен ли переходный период?')),
 ('logistics',r'логист|транспорт|перевоз|порт|фрахт|маршрут',
  'транспорт логистика издержки',('MAINOKVED_NAME','REGION','FTS_COUNTRY_NAME'),
  'Изменение тарифа или доступности маршрута может повлиять на себестоимость и оборотный капитал через сроки поставок.',
  ('Какие маршруты и виды транспорта использует компания?', 'Каковы доля перевозки в себестоимости, запас и альтернативные поставщики?')),
 ('labor',r'кадр|зарплат|рын.{0,5}труда|персонал|работник',
  'рынок труда зарплата издержки',('AMOUNT_WORKERS_FNS_GRADATION','AMOUNT_WORKERS_SPARK_GRADATION','CL_PRODUCT_ZPP_MARK'),
  'Дефицит кадров или изменение оплаты может повлиять на расходы и производственные мощности при соответствующей структуре персонала.',
  ('Какие профессии дефицитны и какова доля фонда оплаты труда в расходах?', 'Каковы текучесть, вакантные позиции и сроки пересмотра оплаты?')),
 ('cyber',r'кибер|утечк|персональн.{0,8}данн|информационн.{0,8}безопас',
  'цифровизация информационная безопасность бизнес',('MAINOKVED_NAME','ORG_TYPE'),
  'Угроза или регулирование данных может потребовать мер защиты для конкретной системы и категории данных.',
  ('Какая система и какие данные компании затронуты?', 'Есть ли подтверждённый инцидент или речь о предупреждении общего риска?')),
 ('technology',r'искусственн.{0,10}интеллект|\bии\b|\bai\b|нейросет|автоматизац',
  'технологии инвестиции производительность',('MAINOKVED_NAME','AMOUNT_WORKERS_FNS_GRADATION'),
  'Технология может изменить затраты или продукт только при совместимости с процессом и подтверждённом эффекте внедрения.',
  ('Какой процесс предполагается менять и каковы его текущие затраты?', 'Есть ли пилот с измеримым эффектом, требованиями к данным и стоимостью внедрения?')),
)
FLAG_FIELDS={'CL_PRODUCT_LOA_MARK','CL_PRODUCT_DEP_MARK','CL_PRODUCT_GAR_MARK','FTS_FLAG','CL_PRODUCT_ZPP_MARK'}
ROLE_ORDER={'treasurer':('financing','foreign_trade','logistics'), 'finance':('financing','tax','demand'),
 'accountant':('tax','labor','foreign_trade'),'procurement':('logistics','foreign_trade','demand'),
 'it':('cyber','technology'),'sales':('demand','foreign_trade'),'director':('demand','financing','technology')}


def plan(article,context,question,role):
    event=(article['title']+' '+article['text'][:1600]).lower()
    question=question or ''
    priorities=ROLE_ORDER.get(role,())
    matches=[m for m in MECHANISMS if re.search(m[1],event)]
    matches.sort(key=lambda m:(0 if re.search(m[1],question.lower()) else 1,
                               priorities.index(m[0]) if m[0] in priorities else len(priorities)))
    paths=[];facts=context['facts']
    for name,pattern,query,fields,transmission,questions in matches:
        observed=[f for f in facts if f['field'] in fields and f.get('evidence_level')=='confirmed'
                  and (f['field'] not in FLAG_FIELDS or str(f['value']).strip() in ('1','1.0'))]
        # A real flag identifies a channel worth checking, not a debt amount or contract.
        paths.append({'mechanism':name,'event_evidence':article['title'],
          'company_fact_ids':[f['id'] for f in observed],
          'transmission_hypothesis':transmission,'conditional':True,
          'limitations':['Флаг продукта не задаёт сумму, ставку, срок или валюту договора.'] if any(f['field'] in FLAG_FIELDS for f in observed) else ['Отраслевой признак не доказывает конкретную экспозицию.'],
          'questions':list(questions)})
    questions=[]
    for path in paths:
        # First question per relevant mechanism avoids spending every slot on one factor.
        if path['questions'][0] not in questions:questions.append(path['questions'][0])
    if paths:
        for q in paths[0]['questions'][1:]:
            if q not in questions:questions.append(q)
    if not questions:questions=['Какая операция или статья доходов/расходов компании может быть затронута этим событием?']
    # A narrow follow-up about missing client parameters is answered from context;
    # bank research is queried when the user asks for its position or an event claim.
    clarify=bool(re.search(r'какие.{0,30}(параметр|данн|уточнен|уточнить)|что.{0,20}уточнить',question.lower()))
    asks_bank=bool(re.search(r'банк|прогноз|эксперт|исследован|источник',question.lower()))
    needs_bank=not clarify or asks_bank
    return {'objective':'Связать наблюдаемый факт с условным механизмом влияния и проверить недостающие основания',
      'mechanisms':[m[0] for m in matches], 'observed_fact_ids':list(dict.fromkeys(fid for p in paths for fid in p['company_fact_ids'])),
      'impact_paths':paths,'priority_questions':questions[:3],
      'query':question+' '+article['title']+' '+' '.join(m[2] for m in matches[:2]),
      'unknowns':['Суммы, ставки, сроки и валюты договоров не установлены исходными флагами',
                  'Единицы выручки и рыночный знаменатель не подтверждены'],
      'max_generation_calls':2,'max_verification_calls':2,'needs_bank_search':needs_bank,
      'bank_search_reason':'Проверка применимой позиции банка' if needs_bank else 'Адресное уточнение клиентских параметров; новый тезис банка не требуется',
      'viewer_role':role,'tools':['get_company_context']+(['search_bank'] if needs_bank else [])+['draft','verify_sources'],
      'refinement_condition':'Повторный поиск только по решению проверяющего инструмента retrieve',
      'planner_kind':'deterministic_evidence_rules_v2'}
