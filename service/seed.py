"""Small explicitly synthetic dataset for a clean-checkout smoke test; not training data."""
import argparse
import json
import sqlite3
from datetime import datetime,timezone,timedelta
from pathlib import Path
from . import bank


def create(target):
    out=Path(target);out.mkdir(parents=True,exist_ok=True);path=out/'catalog.sqlite'
    if path.exists():raise ValueError('Seed already exists; choose a new directory')
    with sqlite3.connect(path) as d:
        d.executescript('''CREATE TABLE companies(source_record_id TEXT,company_id TEXT,source_line INT,okved TEXT,region TEXT,group_id TEXT,status TEXT);
        CREATE TABLE company_activities(okved TEXT,activity TEXT);
        CREATE TABLE topics(topic_id TEXT,name TEXT);
        CREATE TABLE company_mapping(okved TEXT,topic_id TEXT,relation TEXT);
        CREATE TABLE company_family_mapping(okved TEXT,family_key TEXT,relation TEXT,reason TEXT);
        CREATE TABLE object_families(family_key TEXT PRIMARY KEY,object TEXT,sector_id TEXT,sector_name TEXT,reference_member_topic_ids TEXT);
        CREATE TABLE articles(article_id TEXT PRIMARY KEY,content_hash TEXT,text_hash TEXT,title TEXT,text TEXT,url TEXT,source TEXT,published_at TEXT,language TEXT,kind TEXT,ml_export_allowed INTEGER,eligible_delivery INTEGER,object_eligible_delivery INTEGER,status TEXT,images TEXT);
        CREATE TABLE assignments(article_id TEXT,topic_id TEXT,embedding_cosine REAL,reranker_logit REAL,evidence TEXT);
        CREATE TABLE family_assignments(article_id TEXT,family_key TEXT,embedding_cosine REAL,reranker_logit REAL,evidence TEXT,status TEXT,review_reasons TEXT);''')
        for i,code in enumerate(['62.01','47.11'],1):
            d.execute('INSERT INTO companies VALUES(?,?,?,?,?,?,?)',(f'SEED_{i}:line:{i+1}',f'SEED_{i}',i+1,code,'Тестовый регион','seed_group','synthetic'))
            d.execute('INSERT INTO company_activities VALUES(?,?)',(code,'Синтетический профиль для проверки интерфейса'))
        titles=['Тест: обновление правил отчётности','Тест: планирование ликвидности','Тест: защита корпоративных данных','Тест: изменение транспортных расходов','Тест: экспортные расчёты','Тест: сезонные изменения спроса']
        for n,title in enumerate(titles):
            topic=f'seed_topic_{n}';family=f'seed::{n}';aid=f'seed_article_{n}'
            text=title+'. Это синтетическая новость для технической проверки сценария. Она не описывает реальное событие. Перед принятием решений необходимо проверить действующие документы и применимость правил к конкретной компании. Суммы, ставки, сроки и договоры во входных данных не заданы.'
            d.execute('INSERT INTO topics VALUES(?,?)',(topic,title));d.execute('INSERT INTO object_families VALUES(?,?,?,?,?)',(family,title,'seed','Синтетические данные',json.dumps([topic])))
            for code in ['62.01','47.11']:
                d.execute('INSERT INTO company_mapping VALUES(?,?,?)',(code,topic,'declared_activity'))
                d.execute('INSERT INTO company_family_mapping VALUES(?,?,?,?)',(code,family,'declared_activity','Синтетическая связь для теста, не отраслевой факт'))
            stamp=(datetime.now(timezone.utc)-timedelta(hours=n+1)).isoformat()
            d.execute('INSERT INTO articles VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(aid,aid,aid,title,text,'https://example.invalid/synthetic/'+aid,'Синтетический источник',stamp,'ru','news',0,1,1,'synthetic','[]'))
            d.execute('INSERT INTO assignments VALUES(?,?,?,?,?)',(aid,topic,.95,2.,'synthetic'))
            d.execute('INSERT INTO family_assignments VALUES(?,?,?,?,?,?,?)',(aid,family,.95,2.,'synthetic','accepted','[]'))
    (out/'report.json').write_text(json.dumps({'created_at':datetime.now(timezone.utc).isoformat(),'synthetic':True}))
    with sqlite3.connect(out/'service-assets.sqlite') as d:bank.schema(d)
    return path

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();print(create(a.output))
