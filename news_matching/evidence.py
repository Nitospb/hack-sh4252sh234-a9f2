"""Conservative text evidence gates. These are rules, not calibrated probabilities."""
import re
from functools import lru_cache
import snowballstemmer

RU=snowballstemmer.stemmer('russian');EN=snowballstemmer.stemmer('english')
STOP=set('в во на по с со из от до для о об про и или а но не к ко при за у под над без как что это the a an of to and in on for with by or is are'.split())
GENERIC=set('показатель уровень изменение динамика объем величина соответствующий новый применение использование процесс работа операция'.split())
ALIASES={
 'ключевая ставка':['ставка цб','ставка банка россии','key interest rate','policy rate','central bank rate'],
 'инфляция':['inflation','рост потребительских цен'], 'ввп':['gdp','валовой внутренний продукт'],
 'курс рубля':['рубль к доллару','usd rub','курс российской валюты'],
 'безработица':['unemployment'], 'бюджетный дефицит':['дефицит бюджета','budget deficit'],
 'платежный баланс':['платежный баланс','balance of payments'],
 'языковая модель':['llm','large language model','большая языковая модель','chatgpt'],
 'компьютерное зрение':['computer vision','распознавание изображений'],
 'рекомендательная система':['рекомендательный алгоритм','recommendation system','recommender system'],
 'прогнозная модель':['predictive model','прогностическая модель'],
 'речевой помощник':['голосовой помощник','голосовой ассистент','voice assistant'],
 'интеллектуальный поиск':['intelligent search'], 'обнаружение аномалий':['anomaly detection'],
 'автоматическое извлечение данных':['data extraction'],
 'дизельное топливо':['дизтопливо','diesel fuel'],
 'автомобильный бензин':['бензин','gasoline','petrol'], 'нефть':['crude oil'],
 'природный газ':['natural gas'], 'сжиженный природный газ':['спг','lng','liquefied natural gas'],
 'корпоративная облигация':['корпоблигации','corporate bond'],
 'пшеница':['wheat'], 'ячмень':['barley'], 'кукуруза':['corn','maize'],
 'золото':['gold'], 'серебро':['silver'], 'карбамид':['urea'],
 'аммиачная селитра':['ammonium nitrate'],
}
GROUPS={
 'up':['рост','вырос','выросли','растет','растут','повысил','повысили','повышение','повысится','увеличился','увеличили','увеличение','подорожал','подорожали','подорожание','подняли','rising','rise','increased','increase','surge'],
 'down':['снизил','снизили','снижение','снизился','снизились','сократил','сократились','сокращение','упал','упали','падение','подешевел','подешевели','уменьшение','уменьшился','decreased','decrease','decline','fall','drop','reduced'],
 'hold':['сохранил','сохранили','сохранение','сохраняется','оставил','оставили','неизменный','unchanged','maintained'],
 'accel':['ускорение','ускорился','ускорилась','ускорили','accelerated','acceleration'],
 'decel':['замедление','замедлился','замедлилась','замедлили','slowed','slowdown'],
 'launch':['запуск','запустил','запустили','ввел','ввели','введение','внедрили','внедрение','начал','начала','начали','стартовал','открыли','открыл','открытие','подключили','создали','launched','launch','introduced','started'],
 'stop':['прекращение','прекратил','прекратили','остановили','остановка','приостановил','приостановили','приостановка','отменил','отменили','закрыли','закрыл','закрытие','запретил','запретили','отказ','отказали','terminated','suspended','cancelled','ban'],
 'resume':['возобновление','возобновил','возобновили','восстановили','восстановление','resumed','restarted'],
 'change':['изменение','изменил','изменили','изменился','изменились','пересмотр','пересмотрел','пересмотрели','обновил','обновили','обновление','поправка','поправки','скорректировал','revised','changed','updated','amended'],
 'shortage':['дефицит','нехватка','недостаток','shortage','scarcity'],
 'strengthen':['ужесточение','ужесточил','ужесточили','усилил','усилили','усиление','tightened','strengthened'],
 'breach':['нарушение','нарушил','нарушили','утечка','утечки','сбой','сбои','взлом','кибератака','cyberattack','leak','breach','outage'],
}


def norm(s):return str(s).casefold().replace('ё','е')


@lru_cache(maxsize=150000)
def stem(word):
    word=norm(word)
    return RU.stemWord(word) if re.search('[а-я]',word) else EN.stemWord(word)


def words(text):return re.findall(r'[а-яёa-z]+',norm(text))


def useful(text):return [stem(w) for w in words(text) if w not in STOP]


GROUP_STEMS={g:{stem(w) for w in ws} for g,ws in GROUPS.items()}
GENERIC_STEMS={stem(w) for w in GENERIC}
ATTRIBUTE_PRIORITY={stem(w) for w in 'цена тариф стоимость комиссия ставка доходность взнос платеж лимит урожайность площадь производство выпуск спрос рейтинг залог покрытие франшиза премия срок объем запас эффективность'.split()}
ATTRIBUTE_SYNONYMS={stem('цена'):{stem(w) for w in ['цена','стоимость','price','подорожал','подорожали','подорожание','подешевел','подешевели']},stem('тариф'):{stem(w) for w in ['тариф','цена','fee']},stem('производство'):{stem(w) for w in ['производство','выпуск','production']},stem('спрос'):{stem(w) for w in ['спрос','demand']},stem('доходность'):{stem(w) for w in ['доходность','yield']},stem('ставка'):{stem(w) for w in ['ставка','rate']}}


def event_group(signal):
    s=norm(signal)
    for prefix,g in [('повыш','up'),('рост','up'),('увелич','up'),('расшир','up'),('сниж','down'),('сокращ','down'),('уменьш','down'),('сохран','hold'),('ускор','accel'),('замедл','decel'),('запуск','launch'),('введен','launch'),('подключ','launch'),('начал','launch'),('создан','launch'),('открыт','launch'),('прекращ','stop'),('приостанов','stop'),('отмен','stop'),('закрыт','stop'),('отказ','stop'),('изъят','stop'),('возобнов','resume'),('измен','change'),('пересмотр','change'),('обнов','change'),('корректиров','change'),('дефицит','shortage'),('недостат','shortage'),('ужесточ','strengthen'),('усилен','strengthen'),('наруш','breach'),('утечк','breach'),('сбой','breach')]:
        if s.startswith(prefix):return g
    return None


def sentences(article):
    records=[{'text':article['title'],'where':'title'}]
    parts=re.split(r'(?<=[.!?;])\s+(?=[A-ZА-Я«„"0-9])|[\n\r\u2028\u2029]+',article['text'])
    for part in parts:
        part=part.strip()
        if not part:continue
        # Keep overlapping segments of exceptionally long sentences, not unrelated paragraphs.
        if len(part)>1600:
            records.extend({'text':part[i:i+1200],'where':'body_long_sentence'} for i in range(0,len(part),1000))
        else:records.append({'text':part,'where':'body'})
    for r in records:
        r['words']=words(r['text']);r['stems']=[stem(w) for w in r['words']];r['stem_set']=set(r['stems'])
    return records


def object_aliases(topic):
    phrases=[topic['object']]+topic.get('object_keywords',[])+ALIASES.get(norm(topic['object']),[])
    found=[];seen=set()
    for p in phrases:
        tokens=tuple(useful(p))
        if tokens and tokens not in seen:seen.add(tokens);found.append(tokens)
    return found


def object_positions(record,aliases):
    tokens=record['stems'];positions=[];token_set=record.get('stem_set')
    if token_set is None:token_set=set(tokens)
    for alias in aliases:
        required=set(alias)
        if not required<=token_set:continue
        starts=[i for i,t in enumerate(tokens) if t in required]
        for start in starts:
            end=min(len(tokens),start+max(8,len(alias)*3))
            if required<=set(tokens[start:end]):
                relevant=[i for i in range(start,end) if tokens[i] in required]
                positions.append((min(relevant),max(relevant)))
                break
    return positions


def negated(raw_words,index):
    previous=raw_words[max(0,index-3):index]
    if any(w.startswith(('отказал','исключ','предотврат','избеж')) for w in previous):return True
    if any(w.startswith(('исключен','исключен','отменен')) for w in raw_words[index+1:index+4]):return True
    return ('не' in previous and 'только' not in previous) or ('not' in previous)


def modality(record,event_index,signal):
    if 'прогноз' in norm(signal):return 'forecast_or_statistics_topic'
    raw=record['words'];window=raw[max(0,event_index-10):event_index+2]
    future={'повысится','вырастет','вырастут','подорожает','подорожают','увеличится','сократится','снизится','снизятся','упадет','будет','будут','запустит','запустят','начнет','начнут','откроет','откроют','создаст','создадут','введет','введут','повысят','увеличат','снизят','приостановит','прекратит','возобновит'}
    if future&set(window):return 'conditional_or_forecast'
    speculative={'может','могут','мог','могла','могли','если','возможно','допускает','предполагает','ожидает','ожидают','ожидается','ожидаются','планирует','планируют','вероятно','may','might','could','expected','forecast','прогноз','прогнозирует','рискует'}
    return 'conditional_or_forecast' if speculative&set(window) else 'asserted_in_source'


def evidence_for_topic(topic,records):
    aliases=object_aliases(topic);group=event_group(topic['signal'])
    signal_words=useful(topic['signal']);core=[x for x in signal_words[1:] if x not in GENERIC_STEMS and not x.startswith(('уров','показател','измен','динамик','величин','объем','соответствующ','применен','использован','процесс','работ','операц'))]
    priority=[x for x in core if x in ATTRIBUTE_PRIORITY]
    if core:
        attribute=priority[-1] if priority else core[-1]
        core=list(ATTRIBUTE_SYNONYMS.get(attribute,{attribute}))
    best=None
    for record_index,record in enumerate(records):
        if topic['sector_id']=='crosscut_28' and not re.search(r'(?<!\w)(?:ии|ai|llm)(?!\w)|нейросет|искусственн.{0,20}интеллект|машинн.{0,20}обуч|chatgpt|компьютерн.{0,10}зрен|large language',norm(record['text'])):
            continue
        obj_positions=object_positions(record,aliases)
        if not obj_positions:continue
        tokens=record['stems'];raw=record['words']
        signal_text=norm(topic['signal'])
        if 'отпускн' in signal_text and not any(t.startswith(('отпуск','оптов','бирж','производител')) for t in tokens):continue
        if 'закупочн' in signal_text and not any(t.startswith(('закуп','покупоч','приемн')) for t in tokens):continue
        if 'розничн' in signal_text and not any(t.startswith(('рознич','розниц','азс','потребител')) for t in tokens):continue
        positions={i for span in obj_positions for i in range(span[0],span[1]+1)}
        # A news item saying companies "стали" do something does not establish steel context.
        if norm(topic['object'])=='сталь' and not any(x.startswith(('металл','сталевар','прокат','тонн','стальн')) for x in tokens):continue
        if group:
            events=[i for i,t in enumerate(tokens) if t in GROUP_STEMS[group] and not negated(raw,i)]
            if group=='hold' and re.search(r'без\s+изменени',norm(record['text'])):events.append(raw.index('без'))
            if not events:continue
            # A specific event needs a specific attribute as well as a directional word.
            core_positions=[i for i,t in enumerate(tokens) if t in core]
            if core and not core_positions:continue
            for event in events:
                distance=min(abs(event-p) for p in positions)
                if distance>12:continue
                if core_positions and min(abs(event-p) for p in core_positions)>6:continue
                if core_positions and min(abs(q-p) for q in core_positions for p in positions)>8:continue
                opposites={'up':('down','hold'),'down':('up','hold'),'hold':('up','down'),'accel':('decel',),'decel':('accel',),'launch':('stop',),'stop':('resume','launch'),'resume':('stop',)}.get(group,())
                blocked=False
                for other in opposites:
                    for j,t in enumerate(tokens):
                        if t not in GROUP_STEMS[other] or negated(raw,j):continue
                        if core_positions and min(abs(j-p) for p in core_positions)>min(abs(event-p) for p in core_positions):continue
                        if min(abs(j-p) for p in positions)<distance:
                            blocked=True;break
                    if blocked:break
                if blocked:continue
                if group=='down' and (any(t in GROUP_STEMS['decel'] for t in tokens) or any(w in raw for w in ('темп','темпы'))) and any(w in raw for w in ('роста','рост')):
                    # Slower growth is not necessarily a decline in the level.
                    continue
                item=dict(evidence=record['text'],evidence_location=record['where'],evidence_sentence_index=record_index,event_group=group,
                          object_anchor=True,signal_anchor=True,modality=modality(record,event,topic['signal']),distance_tokens=distance,
                          evidence_rule='same_sentence_object_event_attribute_nonnegated')
                rank=(record['where']=='title',-distance,-len(record['text']))
                if best is None or rank>best[0]:best=(rank,item)
        else:
            # Events outside the synonym groups need multiple explicit content words.
            required=set(signal_words)
            hits=required&set(tokens)
            if not required or signal_words[0] not in tokens or len(hits)<max(1,len(required)-1) or len(hits)/len(required)<.66:continue
            event=min(i for i,t in enumerate(tokens) if t in hits)
            if negated(raw,event):continue
            distance=min(abs(event-p) for p in positions)
            if distance>12:continue
            item=dict(evidence=record['text'],evidence_location=record['where'],evidence_sentence_index=record_index,event_group='explicit_signal_words',object_anchor=True,signal_anchor=True,
                      modality=modality(record,event,topic['signal']),distance_tokens=distance,evidence_rule='same_sentence_object_explicit_signal_words')
            rank=(record['where']=='title',-distance,-len(record['text']))
            if best is None or rank>best[0]:best=(rank,item)
    return best[1] if best else None
