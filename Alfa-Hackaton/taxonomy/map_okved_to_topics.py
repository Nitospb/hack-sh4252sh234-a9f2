"""Many-to-many OKVED → ORIGINAL bt_ vocabulary, with semantic scope and provenance."""
import argparse
import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/okved_topic_mapping'
RELATIONS=('declared_activity','activity_scope_candidate','operating_exposure')
VERSION='okved-to-business-topics.v1'


def normalized(value):
    return re.sub(r'\s+',' ',str(value).casefold().replace('ё','е')).strip()


def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def load_catalog(path=None):
    path=path or ROOT/'output/business_topics.jsonl'
    topics=[json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    assert len(topics)==10000 and len({t['topic_id'] for t in topics})==10000
    assert all(t['topic_id'].startswith('bt_') for t in topics)
    return topics


def expand_mapping(record,topics_by_sector):
    bindings=[];unique=set()
    for m in record['mappings']:
        assert m['relation'] in RELATIONS,(record['okved'],m)
        assert m['reason'].strip(),record['okved']
        candidates=topics_by_sector[m['sector_id']]
        assert m['objects'] and len(set(m['objects']))==len(m['objects']),record['okved']
        assert set(m['objects'])<={t['object'] for t in candidates},(record['okved'],m)
        signals=m.get('signal_names',[])
        assert set(signals)<={t['signal'] for t in candidates},(record['okved'],m)
        ids=[t['topic_id'] for t in candidates if t['object'] in m['objects'] and (not signals or t['signal'] in signals)]
        assert ids,(record['okved'],m)
        signature=(m['sector_id'],tuple(sorted(m['objects'])),m['relation'],tuple(sorted(signals)))
        assert signature not in unique,('duplicate binding',record['okved'],m)
        unique.add(signature)
        bid='ob_'+hashlib.sha256((record['okved']+'|'+repr(signature)).encode()).hexdigest()[:16]
        bindings.append(dict(binding_id=bid,sector_id=m['sector_id'],objects=m['objects'],relation=m['relation'],
                             reason=m['reason'],signal_names=signals,topic_ids=ids))
    return bindings


def build(source):
    OUT.mkdir(parents=True,exist_ok=True)
    topics=load_catalog();topic_lookup={t['topic_id']:t for t in topics};by_sector={}
    for t in topics:by_sector.setdefault(t['sector_id'],[]).append(t)
    with source.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f,delimiter=';'))
    observed={r['MAINOKVED_CODE'].strip():r['MAINOKVED_NAME'].strip() for r in rows}
    company_counts=Counter(r['MAINOKVED_CODE'].strip() for r in rows)
    mappings={};provenance={}
    for path in sorted((ROOT/'okved_mapping').glob('*.json')):
        for r in json.loads(path.read_text()):
            code=r['okved'];assert code in observed,(path,code)
            assert code not in mappings,('duplicate code',code)
            assert r['activity']==observed[code],('activity mismatch',code)
            mappings[code]=r;provenance[code]=path.name
    assert set(mappings)==set(observed),('missing codes',set(observed)-set(mappings))
    db_path=OUT/'okved_topics.sqlite'
    if db_path.exists():db_path.unlink()
    db=sqlite3.connect(db_path)
    db.executescript('''PRAGMA journal_mode=OFF;
CREATE TABLE topics(topic_id TEXT PRIMARY KEY,name TEXT,object TEXT,sector_id TEXT,sector_name TEXT,search_text TEXT);
CREATE TABLE activities(okved TEXT PRIMARY KEY,activity TEXT,companies INTEGER,topic_count INTEGER,activity_topic_count INTEGER,exposure_topic_count INTEGER,gap TEXT);
CREATE TABLE bindings(binding_id TEXT PRIMARY KEY,okved TEXT,sector_id TEXT,relation TEXT,reason TEXT,objects TEXT,signals TEXT);
CREATE TABLE mapping(okved TEXT,topic_id TEXT,relation TEXT,binding_id TEXT,PRIMARY KEY(okved,topic_id,binding_id)) WITHOUT ROWID;
CREATE TABLE companies(source_record_id TEXT PRIMARY KEY,company_id TEXT,source_line INTEGER,okved TEXT,region TEXT,group_id TEXT,status TEXT);
''')
    db.executemany('INSERT INTO topics VALUES(?,?,?,?,?,?)',[(t['topic_id'],t['name'],t['object'],t['sector_id'],t['sector_name'],normalized(' '.join([t['name'],t['sector_name']]+t['object_keywords']+t['signal_keywords']))) for t in topics])
    stats=Counter();gaps=[];bycode={};used_topics=set();relation_counts=Counter()
    with (OUT/'okved_topics.jsonl').open('w') as jf,(OUT/'okved_topic_links.csv').open('w',encoding='utf-8-sig',newline='') as cf:
        writer=csv.DictWriter(cf,fieldnames=['okved','activity','topic_id','topic_name','sector_name','object','relation','reason','binding_id']);writer.writeheader()
        for code in sorted(mappings):
            r=mappings[code];bindings=expand_mapping(r,by_sector)
            ids=sorted({tid for b in bindings for tid in b['topic_ids']})
            activity_ids=sorted({tid for b in bindings if b['relation']!='operating_exposure' for tid in b['topic_ids']})
            exposure_ids=sorted({tid for b in bindings if b['relation']=='operating_exposure' for tid in b['topic_ids']})
            if not activity_ids:
                assert r.get('unmapped_reason'),('silent activity gap',code)
            if r.get('unmapped_reason'):gaps.append({'okved':code,'activity':r['activity'],'reason':r['unmapped_reason'],'activity_topic_count':len(activity_ids)})
            db.execute('INSERT INTO activities VALUES(?,?,?,?,?,?,?)',(code,r['activity'],company_counts[code],len(ids),len(activity_ids),len(exposure_ids),r.get('unmapped_reason')))
            for b in bindings:
                db.execute('INSERT INTO bindings VALUES(?,?,?,?,?,?,?)',(b['binding_id'],code,b['sector_id'],b['relation'],b['reason'],json.dumps(b['objects'],ensure_ascii=False),json.dumps(b['signal_names'],ensure_ascii=False)))
                for tid in b['topic_ids']:
                    t=topic_lookup[tid]
                    db.execute('INSERT INTO mapping VALUES(?,?,?,?)',(code,tid,b['relation'],b['binding_id']))
                    writer.writerow(dict(okved=code,activity=r['activity'],topic_id=tid,topic_name=t['name'],sector_name=t['sector_name'],object=t['object'],relation=b['relation'],reason=b['reason'],binding_id=b['binding_id']))
                    stats['expanded_links']+=1;relation_counts[b['relation']]+=1
            item=dict(okved=code,activity=r['activity'],source_company_rows=company_counts[code],topic_count=len(ids),activity_topic_count=len(activity_ids),
                      operating_exposure_topic_count=len(exposure_ids),topic_ids=ids,activity_topic_ids=activity_ids,operating_exposure_topic_ids=exposure_ids,
                      bindings=bindings,unmapped_reason=r.get('unmapped_reason'),review_source=provenance[code],version=VERSION,
                      interpretation='Themes are news interests; signal occurrence and actual product specialization are not established.')
            jf.write(json.dumps(item,ensure_ascii=False)+'\n');bycode[code]=item;used_topics.update(ids)
    duplicate_ids=Counter(r['SYNTHETIC_U'] for r in rows)
    with (OUT/'company_topic_index.csv').open('w',encoding='utf-8-sig',newline='') as cf,(OUT/'company_topic_index.jsonl').open('w') as jf:
        fields=['source_record_id','company_id','source_line','okved','activity','activity_topic_count','operating_exposure_topic_count','total_unique_topic_count','mapping_key','status']
        w=csv.DictWriter(cf,fieldnames=fields);w.writeheader()
        for line,r in enumerate(rows,2):
            code=r['MAINOKVED_CODE'].strip();item=bycode[code];uid=r['SYNTHETIC_U']
            status='multiple_source_records_review_required' if duplicate_ids[uid]>1 else 'okved_based_mapping'
            entry=dict(source_record_id=f'{uid}:line:{line}',company_id=uid,source_line=line,okved=code,activity=item['activity'],activity_topic_count=item['activity_topic_count'],
                       operating_exposure_topic_count=item['operating_exposure_topic_count'],total_unique_topic_count=item['topic_count'],mapping_key=code,status=status)
            w.writerow(entry);jf.write(json.dumps(entry,ensure_ascii=False)+'\n')
            db.execute('INSERT INTO companies VALUES(?,?,?,?,?,?,?)',(entry['source_record_id'],uid,line,code,r['REGION'],r['GROUP_ID'],status))
            stats['source_company_records']+=1;stats['company_records_with_activity_topics']+=bool(item['activity_topic_count']);stats['company_records_with_any_topics']+=bool(item['topic_count'])
    db.executescript('CREATE INDEX mapping_topic_idx ON mapping(topic_id,relation);CREATE INDEX mapping_code_idx ON mapping(okved);CREATE INDEX company_okved_idx ON companies(okved);CREATE INDEX company_uid_idx ON companies(company_id);')
    db.commit()
    assert db.execute('SELECT count(*) FROM companies').fetchone()[0]==len(rows)
    assert not db.execute('SELECT 1 FROM mapping m LEFT JOIN topics t USING(topic_id) WHERE t.topic_id IS NULL LIMIT 1').fetchone()
    db.close()
    dump(OUT/'gaps.json',gaps)
    report=dict(version=VERSION,status='structural_validation_passed',catalog_topics=len(topics),used_catalog_topics=len(used_topics),observed_okved_codes=len(observed),mapped_okved_codes=len(bycode),
        codes_with_activity_topics=sum(bool(v['activity_topic_count']) for v in bycode.values()),codes_with_any_topics=sum(bool(v['topic_count']) for v in bycode.values()),
        codes_with_reported_gaps=len(gaps),source_unique_companies=len(duplicate_ids),stats=stats,expanded_links_by_relation=relation_counts,
        minimum_topic_count=min(v['topic_count'] for v in bycode.values()),maximum_topic_count=max(v['topic_count'] for v in bycode.values()),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),catalog_sha256=hashlib.sha256((ROOT/'output/business_topics.jsonl').read_bytes()).hexdigest(),
        mapping_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'okved_mapping').glob('*.json'))},
        method='Subagent-authored exact-code object selections expanded ONLY to existing bt_ IDs. No new topics created.',
        limits=['OKVED is declared broad activity, not verified actual products.','Operating exposures do not establish own activity.','Catalog gaps remain explicit.','Signal names denote topics, not observed events.'])
    dump(OUT/'validation.json',report);print(json.dumps(report,ensure_ascii=False,indent=2))


def topic_matches(topic,query):
    q=normalized(query)
    if q in ('ии','ai','искусственный интеллект'):
        return topic['sector_id']=='crosscut_28'
    if q in ('логистика','logistics'):
        return topic['sector_id'] in ('services_08','services_09','services_10','services_11','services_12')
    text=normalized(' '.join([topic['name'],topic['sector_name']]+topic['object_keywords']+topic['signal_keywords']))
    return bool(re.search(r'(?<!\w)'+re.escape(q)+r'(?!\w)',text)) if q else False


def search(query,mode,limit):
    topics=load_catalog();selected=[t for t in topics if topic_matches(t,query)]
    if not selected:
        return dict(query=query,mode=mode,total_records=0,total_unique_companies=0,results=[],reason='No matching topic in the original vocabulary.')
    db=sqlite3.connect('file:'+str((OUT/'okved_topics.sqlite').resolve())+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    db.execute('CREATE TEMP TABLE query_topics(topic_id TEXT PRIMARY KEY)')
    db.executemany('INSERT INTO query_topics VALUES(?)',[(t['topic_id'],) for t in selected])
    allowed={'declared':('declared_activity',),'activity':('declared_activity','activity_scope_candidate'),'interest':RELATIONS}[mode]
    marks=','.join('?' for _ in allowed)
    common=f' FROM companies c JOIN activities a USING(okved) JOIN mapping m ON m.okved=c.okved JOIN query_topics q ON q.topic_id=m.topic_id WHERE m.relation IN ({marks})'
    count=db.execute('SELECT count(DISTINCT c.source_record_id),count(DISTINCT c.company_id)'+common,allowed).fetchone()
    found=db.execute('SELECT c.source_record_id,c.company_id,c.okved,a.activity,c.status,count(DISTINCT m.topic_id) AS matched_topic_count'+common+' GROUP BY c.source_record_id ORDER BY matched_topic_count DESC,c.source_record_id LIMIT ?',(*allowed,limit)).fetchall()
    results=[]
    for r in found:
        item=dict(r)
        evidence=db.execute(f'''SELECT DISTINCT b.relation,b.reason,b.sector_id,b.objects FROM bindings b JOIN mapping m ON m.binding_id=b.binding_id JOIN query_topics q ON q.topic_id=m.topic_id WHERE b.okved=? AND b.relation IN ({marks}) ORDER BY b.relation,b.sector_id''',(r['okved'],*allowed)).fetchall()
        item['evidence']=[{**dict(e),'objects':json.loads(e['objects'])} for e in evidence]
        results.append(item)
    db.close()
    return dict(query=query,mode=mode,matched_catalog_topics=len(selected),total_records=count[0],total_unique_companies=count[1],returned=len(results),results=results,
                interpretation={'declared':'Object explicitly supported by declared OKVED wording.','activity':'Includes possible specialization within broad declared scope; not verified actual specialization.','interest':'Includes indirect operating interests; does not mean the company performs that activity.'}[mode])


def company_details(company_id, limit):
    db=sqlite3.connect('file:'+str((OUT/'okved_topics.sqlite').resolve())+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    records=[]
    for row in db.execute('SELECT c.*,a.activity,a.topic_count,a.activity_topic_count,a.exposure_topic_count,a.gap FROM companies c JOIN activities a USING(okved) WHERE c.company_id=? ORDER BY c.source_line',(company_id,)).fetchall():
        item=dict(row)
        topics=db.execute('SELECT DISTINCT t.topic_id,t.name,t.object,t.sector_name FROM topics t JOIN mapping m USING(topic_id) WHERE m.okved=? ORDER BY t.name LIMIT ?',(row['okved'],limit)).fetchall()
        item['topics']=[]
        for topic in topics:
            value=dict(topic)
            supports=db.execute('SELECT DISTINCT m.relation,b.reason,b.binding_id FROM mapping m JOIN bindings b USING(binding_id) WHERE m.okved=? AND m.topic_id=? ORDER BY m.relation',(row['okved'],topic['topic_id'])).fetchall()
            value['supports']=[dict(r) for r in supports]
            item['topics'].append(value)
        item['returned_topics']=len(topics);item['truncated']=len(topics)<row['topic_count']
        records.append(item)
    db.close()
    return dict(company_id=company_id,records=records,source_record_count=len(records),catalog='original 10000 bt_ topics',version=VERSION)


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    b=sub.add_parser('build');b.add_argument('--source',type=Path,required=True)
    s=sub.add_parser('search');s.add_argument('query');s.add_argument('--mode',choices=['declared','activity','interest'],default='activity');s.add_argument('--limit',type=int,default=20)
    c=sub.add_parser('company');c.add_argument('company_id');c.add_argument('--limit',type=int,default=30)
    a=p.parse_args()
    if a.command=='build':build(a.source)
    elif a.command=='search':print(json.dumps(search(a.query,a.mode,a.limit),ensure_ascii=False,indent=2))
    else:print(json.dumps(company_details(a.company_id,a.limit),ensure_ascii=False,indent=2))
