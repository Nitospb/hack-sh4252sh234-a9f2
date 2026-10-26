"""Explicit numeric statements and conservative, evidence-backed comparisons.

Unknown context stays unknown. This module neither ranks articles nor judges
source credibility, company relevance or the truth of a publication.
"""
from collections import defaultdict
from datetime import date,datetime,timezone
import calendar
from decimal import Decimal
import hashlib
import itertools
import re

POLICY='explicit-source-facts-v1'
METRICS=(
 ('policy_rate','Ключевая ставка',r'ключев\w*\s+ставк\w*|policy\s+rate|key\s+interest\s+rate'),
 ('inflation','Инфляция',r'инфляц\w*|inflation|consumer\s+price\s+index'),
 ('gdp','ВВП',r'\bВВП\b|\bGDP\b|валов\w*\s+внутренн\w*\s+продукт\w*'),
 ('revenue','Выручка',r'выручк\w*|\brevenue\b'),
 ('net_profit','Чистая прибыль',r'чист\w*\s+прибыл\w*|net\s+(?:profit|income)'),
 ('unemployment','Безработица',r'безработиц\w*|unemployment'),
 ('production','Производство',r'объ[её]м\w*\s+производств\w*|industrial\s+production'),
 ('exports','Экспорт',r'экспорт\w*|\bexports\b'),
 ('imports','Импорт',r'импорт\w*|\bimports\b'),
)
N=r'[−-]?\d+(?:[ \u00a0]\d{3})*(?:[.,]\d+)?'
U=r'п\.?\s*п\.?|процентн\w*\s+пункт\w*|percentage\s+points?|%|percent|(?:(?:трлн|млрд|млн|тыс)\.?\s*)?(?:руб(?:лей|ля|ль|\.)?|RUB|доллар(?:ов|а)?|USD|EUR|евро|CNY|юан(?:ей|я)?|тонн(?:ы|а)?|tonnes?)|трлн|млрд|млн'
NUMBER=re.compile(rf'(?<![\w.,])(?P<a>{N})(?:\s*[–—-]\s*(?P<b>{N}))?\s*(?P<unit>{U})(?!\w)',re.I)
COUNTRIES=(('RU',r'росси\w*|\bРФ\b|\bRussia\b'),('CN',r'кита\w*|\bКНР\b|\bChina\b'),
           ('US',r'\bСША\b|\bUS\b|United\s+States'),('EUROZONE',r'еврозон\w*|eurozone'))
ACTORS=(('cbr','Банк России',r'Банк\w*\s+Росси\w*|\bЦБ\s*РФ\b|Центробанк\w*\s+Росси\w*'),
        ('alfa_bank','Альфа-Банк',r'Альфа[ -]Банк\w*|Alfa[ -]Bank'),
        ('rosstat','Росстат',r'Росстат\w*'),('min_economy_ru','Минэкономразвития РФ',r'Минэкономразвития\w*\s+Росси\w*|МЭР\s+РФ'))
MONTHS={'январ':1,'феврал':2,'март':3,'апрел':4,'ма':5,'июн':6,'июл':7,'август':8,'сентябр':9,'октябр':10,'ноябр':11,'декабр':12}


def sentences(text):
    start=0
    for boundary in re.finditer(r'[.!?](?=\s|$)|\n\s*\n',text):
        if boundary.group()=='.':
            previous=re.search(r'([а-яёa-z]+)$',text[:boundary.start()],re.I)
            if previous and previous[1].lower() in {'г','гг','млн','млрд','трлн','тыс','руб','п','рис','стр','см','табл'}:continue
        yield start,boundary.end(),text[start:boundary.end()]
        start=boundary.end()
    if start<len(text):yield start,len(text),text[start:]


def relative_period(text,published_at):
    if re.search(r'20\d{2}',text) or not published_at:return None
    next_year=bool(re.search(r'следующ\w*\s+год',text,re.I))
    this_year=bool(re.search(r'(?:текущ\w*|этом)\s+год|кон(?:ец|ц[аеу])\s+года',text,re.I))
    if next_year==this_year:return None
    try:year=date.fromisoformat(published_at[:10]).year+int(next_year)
    except ValueError:return None
    return {'key':'Y:'+str(year),'raw':'следующий год' if next_year else 'текущий год','anchor_date':published_at[:10]}


def decimal(raw):return Decimal(raw.replace(' ','').replace('\u00a0','').replace(',','.').replace('−','-'))
def text_number(value):return format(value.normalize(),'f')
def stamp(value):
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).timestamp()
    except (ValueError,TypeError,AttributeError):return None


def _month(token):
    token=token.lower()
    if re.fullmatch(r'ма[йяею]',token):return 5
    return next((n for stem,n in MONTHS.items() if stem!='ма' and re.fullmatch(re.escape(stem)+r'[ьяеюау]?',token)),None)


def period(text):
    found=[]
    for m in re.finditer(r'\b([а-яё]+)\s*[–—-]\s*([а-яё]+)\s+(20\d{2})',text,re.I):
        first,last=_month(m[1]),_month(m[2])
        if first and last and first<=last:found.append((f'YTD:{m[3]}-{last}' if first==1 else f'R:{m[3]}-{first:02}/{m[3]}-{last:02}',m.group()))
    if re.search(r'последн\w*\s+\d+\s+месяц|trailing|last\s+\d+\s+months',text,re.I):return None
    # Narrow explicit periods take precedence over their embedded year.
    for m in re.finditer(r'\b(20\d{2})-(\d{2})-(\d{2})\b',text):
        try:found.append(('D:'+date(*map(int,m.groups())).isoformat(),m.group()))
        except ValueError:pass
    for m in re.finditer(r'\b(\d{1,2})\s+([а-яё]+)\s+(20\d{2})',text,re.I):
        month=_month(m[2])
        if month:
            try:found.append(('D:'+date(int(m[3]),month,int(m[1])).isoformat(),m.group()))
            except ValueError:pass
    for m in re.finditer(r'\b(Q[1-4]|(?:[1-4IVX]+|перв\w*|втор\w*|трет\w*|четверт\w*)\s*квартал\w*)\s*(20\d{2})',text,re.I):
        token=m[1].upper().split()[0];q={'I':1,'II':2,'III':3,'IV':4}.get(token)
        if q is None and token.lstrip('Q').isdigit():q=int(token.lstrip('Q'))
        if q is None:q=next((n for stem,n in [('ПЕРВ',1),('ВТОР',2),('ТРЕТ',3),('ЧЕТВЕРТ',4)] if token.startswith(stem)),None)
        if q in (1,2,3,4):found.append((f'Q:{m[2]}-{q}',m.group()))
    for m in re.finditer(r'\b(перв\w*|втор\w*|[12])\s*(?:полугоди\w*|П)\s*(20\d{2})',text,re.I):
        h=1 if m[1].lower().startswith(('перв','1')) else 2;found.append((f'H:{m[2]}-{h}',m.group()))
    for m in re.finditer(r'\b(\d{1,2})\s+месяц\w*\s+(20\d{2})',text,re.I):
        if 1<=int(m[1])<=12:found.append((f'YTD:{m[2]}-{int(m[1])}',m.group()))
    for m in re.finditer(r'\b([а-яё]+)\s+(20\d{2})',text,re.I):
        month=_month(m[1])
        if month and not any(p[0].startswith(('D:','R:','YTD:')) for p in found):found.append((f'M:{m[2]}-{month:02}',m.group()))
    if not found and re.search(r'квартал|полугоди|месяц|quarter|year.to.date',text,re.I):return None
    if found and any(y not in ' '.join(p[0] for p in found) for y in re.findall(r'20\d{2}',text)):return None
    if not found:found=[('Y:'+m.group(),m.group()) for m in re.finditer(r'(?<!\d)20\d{2}(?!\d)',text)]
    keys=set(p[0] for p in found)
    return {'key':next(iter(keys)),'raw':next(p[1] for p in found if p[0]==next(iter(keys)))} if len(keys)==1 else None


def period_end(key):
    try:
        kind,value=key.split(':',1)
        if kind=='Y':return date(int(value),12,31)
        if kind=='D':return date.fromisoformat(value)
        if kind=='R':value=value.split('/')[-1]
        year,part=map(int,value.split('-'))
        month=part*3 if kind=='Q' else part*6 if kind=='H' else part
        return date(year,month,calendar.monthrange(year,month)[1])
    except (ValueError,TypeError):return None


def unit(raw):
    raw=raw.lower().replace('\u00a0',' ').strip()
    if raw in ('%','percent'):return 'percent',Decimal(1)
    if re.search(r'^п\.?\s*п\.?$|процентн|percentage',raw):return 'percentage_point',Decimal(1)
    scale=next((factor for name,factor in [('трлн',10**12),('млрд',10**9),('млн',10**6),('тыс',1000)] if name in raw),1)
    code=next((code for code,pattern in [('RUB',r'руб|rub'),('USD',r'доллар|usd'),('EUR',r'евро|eur'),('CNY',r'юан|cny'),('tonne',r'тонн|tonne')] if re.search(pattern,raw)),None)
    return code,Decimal(scale)


def _subject(clause,title,metric):
    text=clause+' '+title
    if metric=='policy_rate' and re.search(ACTORS[0][2],text,re.I):return {'id':'country:RU','label':'Россия','raw':'Банк России'}
    companies=list(re.finditer(r'(?:ПАО|ООО|АО)\s*[«"]([^»"\n]{2,100})[»"]',clause,re.I))
    if not companies:companies=list(re.finditer(r'(?:ПАО|ООО|АО)\s*[«"]([^»"\n]{2,100})[»"]',title,re.I))
    if metric in ('revenue','net_profit','production','exports','imports') and companies:
        names={re.sub(r'\s+',' ',m[1].lower()).strip() for m in companies}
        if len(names)==1:return {'id':'company:'+next(iter(names)),'label':companies[0][1],'raw':companies[0].group()}
        return None
    found=[{'id':'country:'+key,'label':{'RU':'Россия','CN':'Китай','US':'США','EUROZONE':'Еврозона'}[key],'raw':m.group()} for key,pattern in COUNTRIES if (m:=re.search(pattern,text,re.I))]
    return found[0] if len(found)==1 and metric not in ('revenue','net_profit') else None


def extract(source,max_facts=40):
    text=source.get('text','')[:20000];title=source.get('title') or source.get('document_title','')
    result=[];text_sha=hashlib.sha256(text.encode()).hexdigest()
    for sentence_start,_,sentence in sentences(text):
        # Semicolons clearly separate claims; commas may be decimal separators.
        for clause in re.finditer(r'[^;]+',sentence):
            fragment=clause.group();base=sentence_start+clause.start()
            metrics=[(key,label,m) for key,label,pattern in METRICS for m in re.finditer(pattern,fragment,re.I)]
            numbers=list(NUMBER.finditer(fragment))
            for number_index,number in enumerate(numbers):
                nearby=sorted((x for x in metrics if abs(x[2].end()-number.start())<=140),key=lambda x:(x[2].start()>number.start(),abs(x[2].end()-number.start())))
                chosen=nearby[0] if nearby else None
                if chosen:
                    metric_end=chosen[2].end()
                    if number_index and metric_end<numbers[number_index-1].start():
                        connector=fragment[numbers[number_index-1].end():number.start()]
                        if not re.fullmatch(r'\s*(?:до|с|вместо|–|—)\s*',connector,re.I):chosen=None
                    if chosen and chosen[2].start()>number.end() and number_index+1<len(numbers) and numbers[number_index+1].start()<chosen[2].start():chosen=None
                metric,label=(chosen[0],chosen[1]) if chosen else (None,None)
                normalized,scale=unit(number['unit']);low=decimal(number['a'])*scale;high=decimal(number['b'])*scale if number['b'] else low
                if low>high:low,high=high,low
                # A sentence with several periods cannot assign values to years by proximity alone.
                horizon=period(fragment) or (period(title) if sentence_start==0 and clause.start()==0 and not re.search(r'20\d{2}',fragment) else None) or relative_period(fragment,source.get('published_at'))
                forecast=bool(re.search(r'прогноз\w*|ожидаем|ожидает(?:ся)?|ожидают|составит|forecast|expects?|we expect',fragment,re.I))
                subject=_subject(fragment,title if sentence_start==0 else '',metric)
                if not forecast and metric=='policy_rate' and horizon is None and source.get('published_at'):
                    horizon={'key':'D:'+source['published_at'][:10],'raw':'дата публикации','inferred_from_publication':True}
                measure='change' if normalized=='percentage_point' else 'growth' if normalized=='percent' and metric in ('revenue','net_profit','gdp','production','exports','imports') else 'level'
                aggregation='annual_average' if re.search(r'среднегодов\w*|в среднем за|annual average',fragment,re.I) else 'year_end' if re.search(r'кон(?:ец|ц[аеу])\s+(?:20\d{2}|года)|end.of.year',fragment,re.I) else 'unspecified'
                frequency='yoy' if re.search(r'г/г|год к году|year.on.year',fragment,re.I) else 'mom' if re.search(r'м/м|месяц к месяцу|month.on.month',fragment,re.I) else 'unspecified'
                valuation='real' if re.search(r'реальн\w*|real GDP',fragment,re.I) else 'nominal' if re.search(r'номинальн\w*|nominal',fragment,re.I) else 'unspecified'
                accounting='IFRS' if re.search(r'МСФО|IFRS',fragment,re.I) else 'RAS' if re.search(r'РСБУ',fragment,re.I) else 'unspecified'
                scenario='optimistic' if re.search(r'оптимист\w*|optimistic',fragment,re.I) else 'pessimistic' if re.search(r'пессимист\w*|pessimistic',fragment,re.I) else 'base' if re.search(r'базов\w*\s+сценар\w*|base.case',fragment,re.I) else 'unspecified'
                actors=[key for key,_,pattern in ACTORS if re.search(pattern,fragment,re.I)]
                author=actors[0] if len(actors)==1 else 'alfa_bank' if not actors and source.get('owner')=='alfa_bank' and re.search(r'ожидаем|наш\w* прогноз|we expect|our forecast',fragment,re.I) else None
                revision=bool(re.search(r'пересмотр\w*|повыс\w*\s+прогноз|пониз\w*\s+прогноз|сниз\w*\s+прогноз|уточн\w*|revis\w*',fragment,re.I))
                prefix=fragment[max(0,number.start()-8):number.start()]
                transition_before=bool(re.search(r'\bс\s*$',prefix,re.I)) and bool(re.match(r'\s*до\s*',fragment[number.end():],re.I))
                role='previous' if (revision and re.search(r'\bс\s*$',prefix,re.I)) or transition_before else 'current'
                missing=[name for name,value in [('metric',metric),('subject',subject),('period',horizon),('unit',normalized)] if not value]
                ambiguous_definitions=sum(bool(re.search(p,fragment,re.I)) for p in (r'г/г|год к году|year.on.year',r'м/м|месяц к месяцу|month.on.month'))>1 or (bool(re.search(r'МСФО|IFRS',fragment,re.I)) and bool(re.search(r'РСБУ',fragment,re.I))) or (bool(re.search(r'базов\w*\s+сценар',fragment,re.I)) and bool(re.search(r'оптимист\w*|пессимист\w*',fragment,re.I))) or (bool(re.search(r'среднегодов\w*|annual average',fragment,re.I)) and bool(re.search(r'кон(?:ец|ц[аеу])\s+(?:20\d{2}|года)|end.of.year',fragment,re.I)))
                if ambiguous_definitions:missing.append('ambiguous_definitions')
                if not forecast and horizon and source.get('published_at'):
                    end_date=period_end(horizon['key'])
                    try:
                        if end_date and end_date>date.fromisoformat(source['published_at'][:10]):missing.append('period_not_complete')
                    except ValueError:missing.append('unknown_publication_date')
                if role=='previous' or (not revision and re.search(r'ранее|прежн\w*|предыдущ\w*|previous|earlier',fragment,re.I)):missing.append('previous_value')
                if forecast and len(list(NUMBER.finditer(fragment)))>1 and re.search(r'составил\w*|сохранил\w*|вырос\w*|снизил\w* ставк',fragment,re.I):missing.append('mixed_statement_kind')
                if 'tesseract' in source.get('method','').lower():missing.append('ocr_unverified')
                start=base+number.start();end=base+number.end();quote_start=base+max(0,number.start()-220);quote_end=base+min(len(fragment),number.end()+220)
                result.append({'id':'statement_'+hashlib.sha256(f"{source['id']}:{text_sha}:{start}:{end}:{metric}".encode()).hexdigest()[:24],
                    'source_id':source['id'],'metric':metric,'metric_label':label,'subject':subject,'period':horizon,
                    'unit':normalized,'original_unit':number['unit'],'value_min':text_number(low),'value_max':text_number(high),
                    'raw':number.group(),'start':start,'end':end,'quote':text[quote_start:quote_end],'quote_start':quote_start,'quote_end':quote_end,
                    'measure':measure,'aggregation':aggregation,'frequency':frequency,'accounting':accounting,'valuation':valuation,'scenario':scenario,
                    'kind':'forecast' if forecast else 'reported','author':author,'revision_signal':revision,'value_role':role,
                    'published_at':source.get('published_at'),'owner':source.get('owner'),'document_id':source.get('document_id'),
                    'text_sha256':text_sha,'comparable':not missing,'missing_context':missing})
                if len(result)>=max_facts:return result
    return result


def compare(sources,max_comparisons=80):
    facts=[f for source in sources for f in extract(source)];groups=defaultdict(list);comparisons=[]
    for f in facts:
        if not f['comparable']:continue
        key=(f['metric'],f['subject']['id'],f['period']['key'],f['unit'],f['measure'],f['aggregation'],f['frequency'],f['accounting'],f['valuation'],f['scenario'])
        groups[key].append(f)
    for rows in groups.values():
        for a,b in itertools.combinations(rows,2):
            if a['source_id']==b['source_id'] or (a['document_id'] and a['document_id']==b['document_id']):continue
            amin,amax,bmin,bmax=map(Decimal,(a['value_min'],a['value_max'],b['value_min'],b['value_max']))
            preferred=None
            if a['kind']!=b['kind']:status='forecast_vs_reported';label='Прогноз и опубликованный результат'
            elif (amin,amax)==(bmin,bmax):status='same_value';label='Значения совпадают'
            elif max(amin,bmin)<=min(amax,bmax):status='overlapping_ranges';label='Диапазоны пересекаются'
            elif a['kind']=='forecast':
                dates=(stamp(a['published_at']),stamp(b['published_at']))
                newer=b if None not in dates and dates[1]>dates[0] else a
                own_forecast=a['author'] and a['author']==a.get('owner')==b.get('owner')
                definition_known=a['aggregation']!='unspecified' or a['frequency']!='unspecified' or a['valuation']!='unspecified'
                if a['author'] and a['author']==b['author'] and (own_forecast or newer['revision_signal']) and definition_known and None not in dates and dates[0]!=dates[1]:
                    newer=b if dates[1]>dates[0] else a;preferred=newer['id']
                    status='forecast_revision' if newer['revision_signal'] else 'later_forecast'
                    label='Пересмотр прогноза того же автора' if status=='forecast_revision' else 'Более поздний прогноз того же автора'
                else:status='different_forecasts';label='Разные прогнозные оценки'
            elif a['author'] and a['author']==b['author'] and stamp(a['published_at'])!=stamp(b['published_at']) and None not in (stamp(a['published_at']),stamp(b['published_at'])) and max((a,b),key=lambda f:stamp(f['published_at']))['revision_signal']:
                status='revised_observation';label='Уточнение опубликованного показателя'
                preferred=max((a,b),key=lambda f:stamp(f['published_at']))['id']
            else:status='reported_difference';label='Источники приводят разные значения показателя'
            comparisons.append({'status':status,'label':label,'metric':a['metric'],'metric_label':a['metric_label'],
                'subject':a['subject'],'period':a['period'],'unit':a['unit'],'measure':a['measure'],
                'fact_ids':[a['id'],b['id']],'source_ids':[a['source_id'],b['source_id']],'preferred_fact_id':preferred,
                'basis':'Совпали явно извлечённые показатель, объект, период, единицы и тип величины. Указанные признаки методики и сценария совместимы; отсутствующие не достраиваются.',
                'limitations':'Это сопоставление формулировок источников, не независимое подтверждение истинности. Разные определения показателя могут требовать дополнительных оснований.'})
            if len(comparisons)>=max_comparisons:break
        if len(comparisons)>=max_comparisons:break
    return {'policy':POLICY,'facts':facts,'comparisons':comparisons,'revision_notices':[r for s in sources for r in revision_notices(s)],'unqualified_facts':sum(not f['comparable'] for f in facts),
        'limitations':['Сопоставляются только явно заданные показатели; неизвестные контексты не достраиваются.',
                        'Совпадение значений не доказывает независимость источников или достоверность.',
                        'Сопоставление не изменяет отбор новостей, персонализацию или оценку применимости к компании.']}


def model_context(report,max_pairs=10):
    pairs=report['comparisons'][:max_pairs];ids={fid for pair in pairs for fid in pair['fact_ids']}
    aliases={f['id']:'statement_'+str(n) for n,f in enumerate((f for f in report['facts'] if f['id'] in ids),1)}
    pairs=[{**p,'fact_ids':[aliases[x] for x in p['fact_ids']],'preferred_fact_id':aliases.get(p['preferred_fact_id'])} for p in pairs]
    return {'policy':report['policy'],'comparisons':pairs,'revision_notices':report.get('revision_notices',[])[:3],'facts':[{**{k:f[k] for k in ('source_id','metric_label','subject','period','unit','value_min','value_max','kind','quote')},'id':aliases[f['id']]} for f in report['facts'] if f['id'] in ids],
            'limitations':report['limitations']}


def remap_sources(value,mapping):
    if isinstance(value,dict):
        return {key:mapping.get(item,item) if key=='source_id' else [mapping.get(x,x) for x in item] if key=='source_ids' else remap_sources(item,mapping) for key,item in value.items()}
    if isinstance(value,list):return [remap_sources(item,mapping) for item in value]
    return value


def revision_notices(source):
    """Explicit first-person revision wording, without certifying any OCR number."""
    if source.get('owner')!='alfa_bank':return []
    text=source.get('text','')[:20000];result=[]
    for old in re.finditer(r'\b(?:ранее|прежде|раньше)\b',text,re.I):
        start=max(0,old.start()-40);end=min(len(text),old.end()+500);window=text[start:end]
        if not re.search(r'\b(?:теперь|пересмотр\w*)\b',window,re.I):continue
        if not re.search(r'мы\s+(?:ожидал\w*|ожидаем)|наш\w*\s+прогноз',window,re.I):continue
        metrics=[{'id':key,'label':label} for key,label,pattern in METRICS if re.search(pattern,window,re.I)]
        if not metrics:continue
        result.append({'source_id':source['id'],'quote':window,'start':start,'end':end,'metrics':metrics,
                       'label':'Автор описывает изменение ожиданий','numeric_verification':'not_verified',
                       'limitations':'Явная формулировка пересмотра в тексте; она не подтверждает цифры, горизонт или применимость к компании.'})
        if len(result)>=3:break
    return result
