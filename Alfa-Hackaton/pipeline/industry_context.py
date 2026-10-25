"""Broad industry-context retrieval using existing E5 vectors + explicit anchors.
Does not label products produced by company or assert news event types.
"""
import json
from collections import defaultdict
from pathlib import Path
import re
import numpy as np

GROUPS = [
 ([f'crosscut_{i:02d}' for i in range(24,30)]+['services_04','services_32'],r'искусственн.{0,12}интеллект|нейросет|кибер|программирован|программист|программн.{0,20}(обеспеч|продукт|код|решени|платформ)|программ.{0,18}\b(PHP|Python|Java|C\\+\\+|JavaScript)\b|разработчик[а-я]*\s+(?:программного\s+обеспечения|софта|приложен|сайтов)|\bИИ\b|\bIT\b|облачн|цифровизац|сервер|дата.центр|софт|роботизац|микроэлектрон|\bчип(?:ы|ов|ам|ами|ах)?\b|полупроводник|телеком|мобильн.{0,10}связ'),
 ([f'services_{i:02d}' for i in range(1,8)]+['services_33'],r'ритейл|рознич|оптов.{0,15}торгов|торговл.{0,18}(товар|продукт|рознич|оптов)|маркетплейс|магазин|продаж.{0,18}(товар|продукт|одежд|обув|электроник|автомобил|молок|мяс)|дистрибьютор|супермаркет|Wildberries|\bOzon\b|пятерочк'),
 ([f'industry_{i:02d}' for i in range(1,11)]+['industry_19','industry_34','services_06'],r'аграр|агропром|сельскохозяй|урожай|фермер|зерн|пшениц|мук[аиу]|молочн|животновод|растениевод|рыбопром|рыболов|пищев.{0,12}промышлен|удобрени|сахар|мясоперераб|свиновод|птицевод|кондитер|продовольств'),
 (['services_15','services_16','services_17','services_18','services_19','industry_26'],r'строитель|застройщик|девелопер|недвижим|жилищ|ипотек|квартир|аренд.{0,10}(офис|склад|помещен)|коммерческ.{0,15}помещен|стройматериал|цемент|бетон'),
 ([f'services_{i:02d}' for i in range(8,15)],r'логист|грузоперевоз|грузов|транспортн|контейнер|судоход|морск.{0,10}(порт|перевоз)|железнодорож|склад|доставк|курьер|авиаперевоз|авиакомпани|ржд'),
 (['industry_12','industry_13','industry_16','industry_17'],r'нефт|газодоб|газов|нефтеперераб|бензин|дизель|электроэнерг|энергетик|электростанц|уголь|угля|топлив'),
 (['industry_23','industry_24','industry_25','industry_30','industry_31','industry_32','industry_33'],r'металлург|сталелит|металлообраб|машиностро|станк|автозавод|автопром|судостро|авиастро|промышленн.{0,12}оборудован|электротехник|производств.{0,12}(автомобил|самолет|судов|оборудован)'),
 (['industry_22','services_07','services_23','services_24','services_25'],r'фармацевт|лекарств|медицинск|здравоохран|аптек|клиник|стоматолог'),
 (['services_20','services_21','services_22'],r'туризм|турист|туроператор|гостиниц|отел[ьяей]|ресторан|общественн.{0,8}питани'),
]

def industry_anchors(title, lead):
    matched={}
    for group,pattern in GROUPS:
        mt=re.search(pattern,title,re.I)
        if not mt and len(re.findall(pattern,lead,re.I))<2:
            continue
        for sector in group:
            matched[sector]=title if mt else lead[:400]
    return matched

def enrich(db, source, articles, features, out):
    families = json.loads((out.parents[1]/'news_matching/output/object_families.json').read_text())
    family_vectors = np.load(out.parents[1]/'news_matching/output/object_family_embeddings.npy')
    sectors=sorted({f['sector_id'] for f in families})
    centroids=np.asarray([family_vectors[[i for i,f in enumerate(families) if f['sector_id']==sector]].mean(0) for sector in sectors])
    centroids/=np.linalg.norm(centroids,axis=1,keepdims=True)
    chunks=[]
    with (out/'article_chunks.jsonl').open() as stream:
        for line in stream: chunks.append(json.loads(line))
    vectors=np.load(out/'article_chunk_embeddings.npy',mmap_mode='r')
    indices=defaultdict(list)
    for i,c in enumerate(chunks):
        if c['chunk_index']<2:indices[c['article_id']].append(i)
    rows=[]
    for aid,a in articles.items():
        if not a['eligible_delivery'] or features[aid][0]==0:continue
        title=a['title'];lead=a['text'][:1000]
        matched=industry_anchors(title,lead)
        if not matched or not indices[aid]:continue
        sims=(vectors[indices[aid]]@centroids.T).max(0)
        valid=[(sectors.index(s),s) for s in matched]
        # Retain broad sector context; event/object specificity remains elsewhere.
        for ix,sector in valid:
            sim=float(sims[ix])
            if sim<.79:continue
            score=min(.85,max(.3,(sim-.70)*3))
            rows.append((aid,sector,round(score,5),matched[sector],'industry_context'))
            if features[aid][0]<.5:
                old=features[aid]; features[aid]=(.55,old[1],old[2],'anchored_business_industry_context')
    db.executescript('''CREATE TABLE article_industries(article_id TEXT,sector_id TEXT,score REAL,evidence TEXT,relation TEXT,PRIMARY KEY(article_id,sector_id));CREATE INDEX industry_sector ON article_industries(sector_id);
    CREATE TABLE company_industries(okved TEXT,sector_id TEXT,relation TEXT,reason TEXT,PRIMARY KEY(okved,sector_id,relation));''')
    db.executemany('INSERT INTO article_industries VALUES(?,?,?,?,?)',rows)
    company_rows=[]
    for r in source.execute("SELECT DISTINCT okved,substr(family_key,1,instr(family_key,'::')-1) sector_id,relation FROM company_family_mapping WHERE relation IN ('declared_activity','activity_scope_candidate')"):
        company_rows.append((r['okved'],r['sector_id'],r['relation'],'Широкий отраслевой контекст существующего отображения ОКВЭД; не подтверждает специализацию на каждом продукте отрасли.'))
    db.executemany('INSERT OR IGNORE INTO company_industries VALUES(?,?,?,?)',company_rows)
    by_sector=defaultdict(set)
    for aid,sector,*_ in rows:by_sector[sector].add(aid)
    by_code=defaultdict(set)
    for code,sector,*_ in company_rows:by_code[code].update(by_sector[sector])
    return by_code, {'industry_context_links':len(rows),'industry_context_articles':len({r[0] for r in rows}),'company_codes_with_20_industry_articles':sum(len(v)>=20 for v in by_code.values())}
