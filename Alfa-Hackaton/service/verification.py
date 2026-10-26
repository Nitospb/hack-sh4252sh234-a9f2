"""Independent publication gates for each claim, the primary event and bank position."""
import copy
import re
from collections import Counter
from insight_generation.prompt import obj,TEXT

FIELDS=('why_for_company','ai_application','risks','opportunities','actions')
ASSESSMENT={'type':'string','enum':['supported','needs_context','unsupported']}
VERIFICATION_SCHEMA=obj({
    'verdict':{'type':'string','enum':['supported','retrieve','needs_context','reject']},
    'event_verdict':ASSESSMENT,
    'bank_verdict':{'type':'string','enum':['supported','needs_context','unsupported','not_present']},
    'claim_reviews':{'type':'array','maxItems':10,'items':obj({'claim_id':TEXT,'verdict':ASSESSMENT,'reason':TEXT})},
    'context_questions':{'type':'array','maxItems':1,'items':TEXT},
    'issues':{'type':'array','items':TEXT},'query':TEXT,
    'quotes':{'type':'array','items':obj({'source_id':TEXT,'quote':TEXT})}})


def claim_items(draft):
    return [{'claim_id':f'{field}/{i}','claim':claim} for field in FIELDS for i,claim in enumerate(draft[field])]


def apply(draft,check,payload):
    result=copy.deepcopy(draft);sources={payload['news']['id']:payload['news']['text']}
    sources.update({p['id']:p['text'] for p in payload.get('bank_passages',[])})
    sources.update({p['id']:p['text'] for p in payload.get('related_news',[])})
    quotes=[];invalid_quotes=0
    for q in check.get('quotes',[]):
        quote=q.get('quote','');sid=q.get('source_id')
        if sid in sources and len(quote.strip())>=10 and re.sub(r'\s+',' ',quote).strip() in re.sub(r'\s+',' ',sources[sid]):quotes.append(q)
        else:invalid_quotes+=1
    quoted={q['source_id'] for q in quotes}
    # Legacy injected verifiers remain supported for existing offline integrations;
    # the production LLM schema always requires explicit per-item reviews.
    per_item='claim_reviews' in check
    reviews=check.get('claim_reviews',[])
    counts=Counter(r.get('claim_id') for r in reviews)
    by_id={r.get('claim_id'):r for r in reviews if counts[r.get('claim_id')]==1}
    event_supported=(check.get('event_verdict')=='supported' if per_item else check.get('verdict')=='supported') and payload['news']['id'] in quoted
    valid_facts={f['id']:f for f in payload['company_facts']}
    audit=[]
    for field in FIELDS:
        kept=[]
        for i,claim in enumerate(draft[field]):
            cid=f'{field}/{i}';review=by_id.get(cid)
            supported=review.get('verdict')=='supported' if review else not per_item and check.get('verdict')=='supported'
            reason=(review.get('reason') or 'Нет пояснения проверки') if review else ('Legacy supported verdict' if supported else 'Нет однозначной проверки этого тезиса')
            ids=set(claim['company_fact_ids']);source_ids=set(claim['source_ids'])
            if not event_supported:supported=False;reason='Не подтверждено основание первичного события'
            elif not source_ids or not source_ids<=quoted:supported=False;reason='Не для всех источников тезиса есть точная подтверждённая цитата'
            elif not ids or not ids<=valid_facts.keys():supported=False;reason='Нет проверяемого основания в профиле компании'
            elif any(valid_facts[f].get('evidence_level')!='confirmed' for f in ids) and not claim['conditional']:
                supported=False;reason='Неподтверждённое условие выдано за факт'
            # A generic conditional flag does not establish the benchmark of a loan.
            # Macro key rate + unknown spread is only a valid symbolic scenario
            # when that benchmark condition is explicitly stated in the claim.
            text=claim['text'].lower()
            numeric_loan_formula=bool(re.search(r'\d+(?:[.,]\d+)?\s*%?\s*\+\s*спред',text))
            explicit_benchmark=bool(re.search(r'если[^.!?]{0,180}(?:привязан|индексир)[^.!?]{0,80}(?:ключев|кс\b)',text))
            if supported and numeric_loan_formula and not explicit_benchmark:
                supported=False;reason='Не задан индекс договора: нельзя подставлять ключевую ставку в ставку компании без явного условия привязки'
            if supported:kept.append(claim)
            audit.append({'claim_id':cid,'published':bool(supported),'reason':reason,
                          'review_verdict':review.get('verdict') if review else 'legacy_global' if not per_item else 'missing_or_duplicate'})
        result[field]=kept
    bank=result.get('bank_view');bank_published=False
    if bank:
        bank_ids=set(bank['source_ids']);available_bank={b['id'] for b in payload.get('bank_passages',[])}
        verdict=check.get('bank_verdict') if per_item else 'supported' if check.get('verdict')=='supported' else 'unsupported'
        bank_published=verdict=='supported' and bool(bank_ids) and bank_ids<=available_bank and bank_ids<=quoted
        if not bank_published:
            result['bank_view']=None
            result['limitations'].append('Позиция банка не приведена: её содержание или основания не прошли отдельную проверку. Остальные выводы проверены независимо.')
    kept_count=sum(len(result[f]) for f in FIELDS);dropped=sum(not row['published'] for row in audit)
    draft_questions=list(dict.fromkeys(q.strip() for q in draft.get('missing_context',[]) if isinstance(q,str) and q.strip()))[:3]
    critical_questions=list(dict.fromkeys(q.strip() for q in check.get('context_questions',[]) if isinstance(q,str) and q.strip()))[:1]
    explicit_parameters=bool(re.search(r'какие.{0,35}(?:параметр|данн|уточн|условия)|что.{0,20}уточнить',payload.get('question','').lower()))
    questions=critical_questions if per_item else draft_questions
    confirmed_baseline=any(valid_facts[f].get('evidence_level')=='confirmed'
        for field in FIELDS for claim in result[field] for f in claim['company_fact_ids'] if f in valid_facts)
    assessment_available=any(result[field] for field in ('why_for_company','ai_application','risks','opportunities'))
    question=payload.get('question','').lower()
    precise_request=bool(re.search(r'точн[а-я]*[^.!?]{0,60}(?:сумм|эффект|расч[её]т|дат|срок|услов|ставк)|сколько[^.!?]{0,60}(?:руб|доллар|евро|плат|расход)|рассчита[йть][^.!?]{0,60}(?:плат|расход|руб|эффект)',question))
    useful_estimate=event_supported and confirmed_baseline and kept_count>0 and (assessment_available or explicit_parameters)
    # A supported scenario is already an answer to a general impact question.
    # Contract details refine its scale; they are not a mandatory gate to show it.
    if per_item and useful_estimate and not precise_request:questions=[]

    if dropped:result['limitations'].append(f'Неподтверждённые тезисы исключены: {dropped}. '+('Обоснованные выводы и действия сохранены.' if kept_count else 'Подтверждённых персональных выводов пока недостаточно; исходное событие и источники доступны.'))
    if invalid_quotes:result['limitations'].append('Цитаты, не совпавшие с первоисточниками, исключены.')
    if not kept_count and not bank_published and (check.get('verdict')=='reject' or (draft['status']=='not_relevant' and check.get('verdict')=='supported' and event_supported)):
        result['status']='not_relevant';result['missing_context']=[]
    elif per_item and useful_estimate and not questions:
        result['status']='ready';result['missing_context']=draft_questions if explicit_parameters else []
        if draft_questions and not explicit_parameters:
            result['limitations'].append('Оценка дана при явно указанных допущениях; точный денежный эффект без параметров договоров не рассчитан.')
    elif per_item and not event_supported:
        result['status']='needs_context';result['missing_context']=[]
        result['limitations'].append('Сервису не удалось подтвердить достаточные основания в первоисточниках. Проверка источников остаётся задачей сервиса, дополнительные действия клиента не требуются.')
    elif (draft['status']!='ready' or dropped or questions or not event_supported or not result['why_for_company']):
        result['status']='needs_context'
        result['missing_context']=questions or draft_questions[:1] or ['Какие сведения о затронутых операциях или условиях договоров компании можно уточнить?']
    else:result['missing_context']=[]
    publication={'mode':'per_claim' if per_item else 'legacy_global','event_supported':event_supported,
        'bank_published':bank_published,'kept_claims':kept_count,'dropped_claims':dropped,
        'invalid_quotes':invalid_quotes,'claims':audit,'status':result['status'],'assessment_ready':bool(useful_estimate),'critical_questions':questions,'precise_request':precise_request,'assessment_available':assessment_available}
    return result,quotes,publication
