"""Reproducible thematic recommendation sidecar; never changes source labels.

Existing 10k event topics are grouped into their existing 1000 object families.
Operational defaults are hypotheses, not company specialisations. Scores are
ranking heuristics, never probabilities or verified event labels.
"""
import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from industry_context import enrich

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'pipeline/output'
BUSINESS = re.compile(r'экономик|бизнес|компани|предприяти|производств|промышлен|инвестиц|инвестор|выручк|прибыл|рентабель|банк|кредит|налог|ндс|инфляц|ключев.{0,10}ставк|экспорт|импорт|поставщик|закупк|контракт|тариф|нефт|газов|энерг|электр|ритейл|торгов|рынок|маркетплейс|искусственн.{0,12}интеллект|нейросет|технолог|кибер|облачн|цифровизац|персонал|работодател|зарплат|бухгалтер|отчетност|логистик|грузоперевоз|агропром|урожай|фермер|строитель|девелопер|недвижим|туроператор|туристическ|медицинск.{0,15}(рынок|бизнес|оборудован)|фармацевт', re.I)
JUNK = re.compile(r'поухаживайте|на даче|огород|студент.{0,30}(вуз|ИИ)|как студенту|приглашаем|анонс форума|пресс.релиз выставки|тылов.{0,12}логист|военн.{0,12}(логист|снабжен|транспорт)|гороскоп|знак.{0,5}зодиак|маникюр|рецепт.{0,20}(суп|салат|пирог)|футбол|хокке|матч|чемпионат|сборная|дтп|авари[яи]|погиб|убий|задержал|задержан|арест|обстрел|атак.{0,10}дрон|беспилотник|военн.{0,12}(операц|удар)|пожар|взрыв|парад.{0,10}планет|звезд.{0,10}шоу', re.I)
ROLES = {
 'accountant': r'налог|ндс|бухгалтер|отчетност|страхов.{0,10}взнос|аудит|фнс|учетн',
 'treasurer': r'ключев.{0,10}ставк|инфляц|валют|курс.{0,10}(рубл|доллар)|ликвидност|кредит|облигац|депозит|казнач',
 'director': r'стратег|выручк|прибыл|инвестиц|компани|бизнес|экономик|слияни|поглощени',
 'it': r'искусственн.{0,12}интеллект|нейросет|кибер|программирован|программист|программн.{0,20}(обеспеч|продукт|код|решени)|разработчик[а-я]*\s+(софта|программного\s+обеспечения|приложен)|\bit\b|\bии\b|облачн|цифровизац|сервер',
 'hr': r'персонал|кадр|работодател|сотрудник|зарплат|оплат.{0,5}труда|трудов.{0,8}(договор|кодекс|рынок)',
}
# Cross-company operating contexts. Being interested does not mean producing these.
OPERATING_NAMES = ['Ключевая ставка','Инфляция','Курс рубля','Потребительский спрос',
 'Налог на прибыль','Налог на добавленную стоимость','Страховой взнос','Налоговая льгота',
 'Бухгалтерский баланс','Учетная политика','Фонд оплаты труда','Кадровый документооборот',
 'Корпоративное обучение','Закупочная процедура','Реестр поставщиков','Рамочный договор',
 'Расчетный счет','Платежный календарь','Кассовый разрыв','Персональные данные',
 'Защита от утечек данных','Система электронного документооборота']

def article_quality(title, text):
    """Conservative business pool based on substantive headline/lead vocabulary."""
    headline = title.lower()
    lead = text[:1200].lower()
    hits = len(BUSINESS.findall(headline))
    body_hits = len(BUSINESS.findall(lead))
    if JUNK.search(headline):
        return 0., False, [], 'excluded_non_business_or_incident_headline'
    roles = [role for role, expr in ROLES.items() if re.search(expr, headline + ' ' + lead[:400], re.I)]
    score = min(.98, .22 + .22 * min(hits, 3) + .04 * min(body_hits, 4)) if hits else .25
    general = hits >= 1 and body_hits >= 2 and (bool(roles) or hits >= 2)
    return round(score, 4), general, roles, 'business_headline_and_lead' if general else 'sector_context_only'

def literal_object_anchor(name, text):
    words = re.findall(r'[а-яa-z0-9]+', name.lower().replace('ё','е'))
    meaningful = [w for w in words if len(w)>=4 and w not in {'система','управление','корпоративный'}]
    target = text.lower().replace('ё','е')
    return bool(meaningful) and all(re.search(r'(?<!\w)' + re.escape(w[:max(4,len(w)-2)]), target) for w in meaningful)

def thematic_candidate(c, quality):
    # Lower semantic thresholds support retrieval only, not accepted extraction.
    return quality >= .5 and c['embedding_cosine'] >= .81 and c['reranker_logit'] >= -3.

def export_coverage(source, profiles, coverages, output):
    activities={r['okved']:r['activity'] for r in source.execute('SELECT okved,activity FROM company_activities')}
    cov={r[0]:r for r in coverages}
    by_code={}
    for r in profiles:
        if r[2] in by_code:continue
        c=cov[r[0]]
        by_code[r[2]]={'company_id':r[1],'source_record_id':r[0],'okved':r[2],
          'activity':activities.get(r[2],''),'direct_articles':c[2],
          'matched_articles':c[1],'topic_count':r[6]}
    rows=sorted(by_code.values(),key=lambda r:-r['direct_articles'])
    with output.with_name('company_ranking_coverage.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    cohort=[by_code[code] for code in ['62.01','47.11','01.11','41.20','49.41'] if code in by_code]
    output.with_name('ranking_company_examples.json').write_text(json.dumps(cohort,ensure_ascii=False,indent=2))

def build(catalog=OUT/'catalog.sqlite', output=OUT/'ranking.sqlite'):
    source = sqlite3.connect(f'file:{catalog}?mode=ro', uri=True)
    source.row_factory = sqlite3.Row
    articles = {r['article_id']: dict(r) for r in source.execute('SELECT * FROM articles')}
    features = {}
    for aid, a in articles.items():
        score, general, roles, reason = article_quality(a['title'], a['text'])
        features[aid] = (score, int(general and a['eligible_delivery']), roles, reason)
    objects = []
    family_names = {r['family_key']:r['object'] for r in source.execute('SELECT * FROM object_families')}
    for row in source.execute('SELECT * FROM family_assignments'):
        c = dict(row)
        a = articles[c['article_id']]
        score, general, roles, reason = features[c['article_id']]
        name = family_names[c['family_key']]
        title_anchor = literal_object_anchor(name,a['title'])
        lead_anchor = literal_object_anchor(name,a['text'][:400])
        supported = not JUNK.search(a['title']) and (
            (title_anchor and c['embedding_cosine']>=.82) or
            (lead_anchor and c['embedding_cosine']>=.84 and c['reranker_logit']>=-6.))
        if supported and score<.5:
            score = .56
            features[c['article_id']] = (score,general,roles,'business_object_headline_or_lead')
        if c['status'] != 'accepted' and not thematic_candidate(c, score) and not supported:
            continue
        if score < .5 or not articles[c['article_id']]['eligible_delivery']:
            continue
        rank_score = min(.98, max(.2, (c['embedding_cosine']-.75)*3 + (c['reranker_logit']+3)*.055))
        objects.append((c['article_id'], c['family_key'], round(rank_score, 5),
                        'accepted' if c['status']=='accepted' else ('semantic_supported' if supported else 'review_supported'), c['evidence']))
    families = {r['object']: r['family_key'] for r in source.execute('SELECT * FROM object_families')}
    operating = [families[n] for n in OPERATING_NAMES]
    mapping = defaultdict(lambda: defaultdict(set))
    for r in source.execute('SELECT DISTINCT okved,family_key,relation FROM company_family_mapping'):
        mapping[r['okved']][r['relation']].add(r['family_key'])
    by_family = defaultdict(set)
    for aid, family, *_ in objects: by_family[family].add(aid)
    general_ids = {aid for aid, f in features.items() if f[1]}
    role_ids = {aid for aid, f in features.items() if f[0]>=.5 and f[2] and articles[aid]['eligible_delivery']}
    temp = output.with_suffix('.building.sqlite')
    if temp.exists(): temp.unlink()
    db = sqlite3.connect(temp)
    db.executescript('''
    CREATE TABLE article_features(article_id TEXT PRIMARY KEY,business_score REAL,general_business INTEGER,role_topics TEXT,quality_reason TEXT);
    CREATE TABLE article_objects(article_id TEXT,family_key TEXT,score REAL,origin TEXT,evidence TEXT,PRIMARY KEY(article_id,family_key));
    CREATE INDEX object_family ON article_objects(family_key);
    CREATE TABLE company_profiles(source_record_id TEXT PRIMARY KEY,company_id TEXT,okved TEXT,direct_families TEXT,adjacent_families TEXT,operating_families TEXT,topic_count INTEGER);
    CREATE INDEX profile_company ON company_profiles(company_id);
    CREATE TABLE operating_defaults(family_key TEXT PRIMARY KEY,relation TEXT,reason TEXT);
    CREATE TABLE company_coverage(source_record_id TEXT PRIMARY KEY,matched_articles INTEGER,direct_articles INTEGER,role_articles INTEGER,general_articles INTEGER);
    CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
    ''')
    industry_by_code, industry_report = enrich(db,source,articles,features,output.parent)
    db.executemany('INSERT INTO article_features VALUES(?,?,?,?,?)', [(aid,f[0],f[1],json.dumps(f[2]),f[3]) for aid,f in features.items()])
    db.executemany('INSERT INTO article_objects VALUES(?,?,?,?,?)', objects)
    db.executemany('INSERT INTO operating_defaults VALUES(?,?,?)',[(f,'operating_exposure','Общий операционный контекст бизнеса: финансы, налоги, персонал, закупки и данные. Предполагаемый интерес, не подтвержденная специализация компании.') for f in operating])
    def union(keys):
        result = set()
        for key in keys: result.update(by_family[key])
        return result
    profiles, coverages = [], []
    code_stats = {}
    for code, rels in mapping.items():
        direct = sorted(rels['declared_activity'])
        adjacent = sorted(rels['activity_scope_candidate'] - set(direct))
        operations = sorted((rels['operating_exposure'] | set(operating)) - set(direct) - set(adjacent))
        own_ids = union(direct + adjacent) | industry_by_code[code]
        company_ids = own_ids | union(operations)
        code_stats[code] = (direct, adjacent, operations, own_ids, company_ids)
    for c in source.execute('SELECT * FROM companies'):
        direct, adjacent, operations, own_ids, company_ids = code_stats.get(c['okved'],([],[],operating,set(),union(operating)))
        profiles.append((c['source_record_id'],c['company_id'],c['okved'],json.dumps(direct),json.dumps(adjacent),json.dumps(operations),len(set(direct+adjacent+operations))))
        coverages.append((c['source_record_id'],len(company_ids | general_ids),len(own_ids),len(role_ids),len(general_ids)))
    db.executemany('INSERT INTO company_profiles VALUES(?,?,?,?,?,?,?)',profiles)
    db.executemany('INSERT INTO company_coverage VALUES(?,?,?,?,?)',coverages)
    report = {**industry_report,'catalog_sha256':hashlib.sha256(catalog.read_bytes()).hexdigest(),
      'built_at':datetime.now(timezone.utc).isoformat(), 'articles':len(articles),
      'business_eligible_articles':sum(1 for aid,f in features.items() if f[0]>=.5 and articles[aid]['eligible_delivery']),
      'general_business_articles':len(general_ids),'thematic_links':len(objects),
      'thematic_articles':len({r[0] for r in objects}),'company_records':len(profiles),
      'company_records_with_20_plus_candidates':sum(r[1]>=20 for r in coverages),
      'company_records_with_20_plus_activity_candidates':sum(r[2]>=20 for r in coverages),
      'minimum_operational_profile_topics':min(r[6] for r in profiles),
      'minimum_candidates':min(r[1] for r in coverages),
      'score_semantics':'retrieval heuristics; no measured precision; no new event labels',
      'operational_defaults':'22 generic business hypotheses, not observed company specialisations',
      'warnings':['20+ coverage includes general business; actual feed can shrink after duplicate, source and seen-item filters.', 'role_topics are content categories; employee role must be selected, never inferred from company data.']}
    db.executemany('INSERT INTO metadata VALUES(?,?)', [('report',json.dumps(report,ensure_ascii=False))])
    export_coverage(source,profiles,coverages,output)
    db.commit(); db.close();source.close();temp.replace(output)
    output.with_name('ranking_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--catalog',type=Path,default=OUT/'catalog.sqlite');p.add_argument('--output',type=Path,default=OUT/'ranking.sqlite')
    a=p.parse_args();build(a.catalog,a.output)
