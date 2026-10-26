"""Versioned client facts. Source flags are observations, never inferred contracts."""
import csv
import hashlib
import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv('ALFA_DATA_DIR', ROOT.parent / 'data'))
FIELDS = {'MAINOKVED_CODE':'ОКВЭД','MAINOKVED_NAME':'Заявленная деятельность','REGION':'Регион',
 'CITY':'Город','FTS_FLAG':'Признак ФТС','FTS_COUNTRY_NAME':'Страны ФТС',
 'CL_PRODUCT_LOA_MARK':'Кредитный флаг','CL_PRODUCT_DEP_MARK':'Депозитный флаг',
 'CL_PRODUCT_GAR_MARK':'Гарантии: флаг','CL_PRODUCT_LEA_MARK':'Лизинг: флаг',
 'CL_PRODUCT_RKO_MARK':'РКО: флаг','CL_PRODUCT_ZPP_MARK':'Зарплатный проект: флаг',
 'FACTORING_MARK':'Факторинг: флаг','REVENUE_COMPANY':'Выручка (единицы не заданы)',
 'AMOUNT_WORKERS_FNS_GRADATION':'Численность ФНС: диапазон',
 'AMOUNT_WORKERS_SPARK_GRADATION':'Численность СПАРК: диапазон',
 'COMPANY_AGE_YEARS_GRADATION':'Возраст: диапазон','ORG_TYPE':'Тип организации',
 'OKFS_NAME':'Форма собственности','ECO_MARK_LABEL':'Стадия','NEGATIVEMARK':'Негативный признак',
 'CL_TYPE':'Тип клиента','GROUP_ID':'Идентификатор группы'}
LIMITATIONS = ['Флаги продуктов не раскрывают суммы, условия, валюту и сроки договоров.',
 'Единицы REVENUE_COMPANY не подтверждены: нельзя пересчитывать в рубли или определять сегмент >15 млрд.',
 'Платёжные доли не являются долями рынка или выручки; период, валюта и назначение платежей неизвестны.',
 'Совпадение GROUP_ID не доказывает владение, гарантии или передачу риска.']


def build_profiles(target, source=None, relationships=None):
    source = Path(source or DATA / 'dataset/df_Uid_data_hack.csv')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    with sqlite3.connect(target) as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS raw_profiles(record_id TEXT PRIMARY KEY,company TEXT,facts TEXT);
        CREATE TABLE IF NOT EXISTS context_meta(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS relationships(record_id TEXT,payload TEXT);
        CREATE INDEX IF NOT EXISTS relationship_record ON relationships(record_id);''')
        old = db.execute("SELECT value FROM context_meta WHERE key='csv_sha256'").fetchone()
        if not old or old[0] != digest:
            db.execute('DELETE FROM raw_profiles')
            with source.open(encoding='utf-8-sig', newline='') as stream:
                db.executemany('INSERT INTO raw_profiles VALUES(?,?,?)',
                  ((f"{r['SYNTHETIC_U']}:line:{n}", r['SYNTHETIC_U'], json.dumps(r,ensure_ascii=False))
                   for n,r in enumerate(csv.DictReader(stream, delimiter=';'),2)))
            db.execute("INSERT OR REPLACE INTO context_meta VALUES('csv_sha256',?)",(digest,))
        relationships = Path(relationships or ROOT/'taxonomy/output/relationship_interests/relationships.jsonl')
        if relationships.exists():
            rdigest = hashlib.sha256(relationships.read_bytes()).hexdigest()
            old = db.execute("SELECT value FROM context_meta WHERE key='relationships_sha256'").fetchone()
            if not old or old[0] != rdigest:
                db.execute('DELETE FROM relationships')
                def rows():
                    with relationships.open() as stream:
                        for line in stream:
                            r=json.loads(line);yield r['source_record_id'],json.dumps(r,ensure_ascii=False)
                db.executemany('INSERT INTO relationships VALUES(?,?)', rows())
                db.execute("INSERT OR REPLACE INTO context_meta VALUES('relationships_sha256',?)",(rdigest,))


def get_context(assets, state, company, user):
    facts=[]; relations=[]; digest=None
    with sqlite3.connect(assets) as db:
        has = db.execute("SELECT 1 FROM sqlite_master WHERE name='raw_profiles'").fetchone()
        row = db.execute('SELECT facts FROM raw_profiles WHERE record_id=?',(company['source_record_id'],)).fetchone() if has else None
        raw=json.loads(row[0]) if row else {}
        if has:
            digest=db.execute("SELECT value FROM context_meta WHERE key='csv_sha256'").fetchone()
        for key,label in FIELDS.items():
            value=raw.get(key,'').strip()
            if value:
                facts.append({'id':'fact_'+key.lower(),'field':key,'label':label,'value':value,'evidence_level':'confirmed',
                 'provenance':{'file':'df_Uid_data_hack.csv','source_record_id':company['source_record_id'],'sha256':digest[0] if digest else None}})
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='relationships'").fetchone():
            relations=[json.loads(r[0]) for r in db.execute('SELECT payload FROM relationships WHERE record_id=? LIMIT 12',(company['source_record_id'],))]
    if not facts:
        facts=[{'id':'fact_okved','field':'okved','label':'ОКВЭД','value':company['okved'],'evidence_level':'confirmed',
                'provenance':{'source_record_id':company['source_record_id'],'file':'catalog.sqlite'}}]
    with sqlite3.connect(state) as db:
        notes=db.execute('SELECT id,text,created_at FROM clarifications WHERE company=? AND record_id=? AND user=? ORDER BY created_at',
                         (company['company_id'],company['source_record_id'],user)).fetchall()
    # User claims are visible but require conditional treatment, not bank-verified facts.
    facts += [{'id':'user_'+r[0],'field':'user_context','label':'Уточнение пользователя','value':r[1],
      'evidence_level':'candidate','provenance':{'kind':'user_declaration','created_at':r[2]}} for r in notes]
    for i,r in enumerate(relations):
        facts.append({'id':f'rel_{i}','field':'observed_relationship','label':r.get('observed_label','Наблюдаемая связь'),
          'value':{k:r.get(k) for k in ('related_company_id','kind','amount','payment_count','direction_amount_share','direction_count_share','role_caveat')},
          'evidence_level':'confirmed','provenance':{'file':'relationships.jsonl','relationship_id':r.get('relationship_id')}})
    version=hashlib.sha256(json.dumps(facts,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return {'facts':facts,'relationships':relations,'limitations':LIMITATIONS,'context_version':version}
