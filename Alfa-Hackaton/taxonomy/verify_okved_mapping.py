"""Independent checks of exact-source IDs, code coverage, bindings and company index."""
import argparse
import csv
import json
import sqlite3
from itertools import zip_longest
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/okved_topic_mapping'


def verify(source):
    topics={t['topic_id']:t for t in map(json.loads,(ROOT/'output/business_topics.jsonl').read_text().splitlines())}
    assert len(topics)==10000 and all(t.startswith('bt_') for t in topics)
    raw={}
    for path in (ROOT/'okved_mapping').glob('*.json'):
        for item in json.loads(path.read_text()):
            assert item['okved'] not in raw
            raw[item['okved']]=item
    compiled={t['okved']:t for t in map(json.loads,(OUT/'okved_topics.jsonl').read_text().splitlines())}
    assert set(raw)==set(compiled)
    for code,item in compiled.items():
        original=raw[code];expected=set();activity=set();exposure=set()
        assert item['activity']==original['activity']
        for binding in original['mappings']:
            found={tid for tid,t in topics.items() if t['sector_id']==binding['sector_id'] and t['object'] in binding['objects'] and (not binding.get('signal_names') or t['signal'] in binding['signal_names'])}
            assert found
            expected.update(found)
            (exposure if binding['relation']=='operating_exposure' else activity).update(found)
        assert expected==set(item['topic_ids'])
        assert activity==set(item['activity_topic_ids'])
        assert exposure==set(item['operating_exposure_topic_ids'])
        assert item['topic_count']==len(expected)
        if not activity:assert item['unmapped_reason']
    db=sqlite3.connect('file:'+str((OUT/'okved_topics.sqlite').resolve())+'?mode=ro',uri=True)
    count=0;companies=set();source_codes=set()
    with source.open(encoding='utf-8-sig',newline='') as f,(OUT/'company_topic_index.csv').open(encoding='utf-8-sig',newline='') as cf,(OUT/'company_topic_index.jsonl').open() as jf:
        for count,(r,c,j) in enumerate(zip_longest(csv.DictReader(f,delimiter=';'),csv.DictReader(cf),jf),1):
            assert r is not None and c is not None and j is not None
            j=json.loads(j);code=r['MAINOKVED_CODE'].strip();uid=r['SYNTHETIC_U'];rid=f'{uid}:line:{count+1}'
            assert j['source_record_id']==c['source_record_id']==rid
            assert j['company_id']==c['company_id']==uid
            assert j['okved']==c['okved']==code
            assert compiled[code]['activity']==r['MAINOKVED_NAME'].strip()==j['activity']==c['activity']
            assert j['mapping_key']==c['mapping_key']==code
            assert j['total_unique_topic_count']==int(c['total_unique_topic_count'])==compiled[code]['topic_count']
            assert db.execute('SELECT company_id,source_line,okved FROM companies WHERE source_record_id=?',(rid,)).fetchone()==(uid,count+1,code)
            companies.add(uid);source_codes.add(code)
    assert source_codes==set(compiled)
    assert db.execute('SELECT count(*) FROM companies').fetchone()[0]==count
    links=0
    with (OUT/'okved_topic_links.csv').open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            tid=r['topic_id'];code=r['okved'];t=topics[tid]
            assert r['topic_name']==t['name'] and r['object']==t['object'] and r['sector_name']==t['sector_name']
            assert tid in compiled[code]['topic_ids']
            expected=db.execute('SELECT b.relation,b.reason,b.okved FROM mapping m JOIN bindings b USING(binding_id) WHERE m.okved=? AND m.topic_id=? AND m.binding_id=?',(code,tid,r['binding_id'])).fetchone()
            assert expected==(r['relation'],r['reason'],code)
            links+=1
    assert db.execute('SELECT count(*) FROM mapping').fetchone()[0]==links
    db.close()
    report=dict(status='passed',source_company_rows=count,unique_companies=len(companies),okved_codes=len(source_codes),expanded_links=links,
                original_catalog_topics=len(topics),all_topic_ids_from_original_catalog=True,new_topic_ids=0,checks=['exact object and signal expansion','all source company records','all code names','CSV/JSONL/SQLite consistency','explicit activity coverage gaps'])
    (OUT/'verify_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);a=p.parse_args();verify(a.source)
