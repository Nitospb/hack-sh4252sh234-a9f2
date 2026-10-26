"""Conservative, versioned publication groups. Similarity is a candidate link, not corroboration."""
import argparse
from collections import defaultdict, Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit
import numpy as np

POLICY={'version':'anchored-story-v2','window_hours':36,'cosine_min':.94,'title_overlap_min':.40,
        'dedup_cosine_min':.985,'dedup_title_overlap':.85,'dedup_window_hours':6}
STOP={'котор','после','также','росси','новос','сообщ','сегод','будет','будут','стало','новый','новые','своих','своей','этого','этой'}
QUANTITY=re.compile(r'(?<![\w.,])(?P<value>\d+(?:[ \u00a0]\d{3})*(?:[.,]\d+)?)\s*(?P<unit>%|млрд(?:\s+руб(?:лей|ля|\.)?)?|млн(?:\s+руб(?:лей|ля|\.)?)?|трлн(?:\s+руб(?:лей|ля|\.)?)?|руб(?:лей|ля|\.)?|доллар(?:ов|а)?|евро|тонн(?:ы|а)?)(?!\w)',re.I)


def stamp(value):
    try:
        d=datetime.fromisoformat((value or '').replace('Z','+00:00'))
        return d.timestamp() if d.tzinfo else None
    except (ValueError,AttributeError):return None


def words(title):return {w[:6] for w in re.findall(r'[а-яёa-z]{4,}',title.lower().replace('ё','е')) if w[:5] not in STOP}


def quantities(text):
    result=[]
    for m in QUANTITY.finditer(text[:1800]):
        unit=m['unit'].lower().strip()
        value=format(Decimal(m['value'].replace(' ','').replace('\u00a0','').replace(',','.')).normalize(),'f')
        # Keep original unit/scale: no inference or currency conversion.
        result.append({'value':value,'unit':unit,'quote':text[max(0,m.start()-80):min(len(text),m.end()+100)],
                       'start':m.start(),'end':m.end(),'raw':m.group(0)})
    return result


def file_sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def mean_vectors(directory):
    matrix=np.load(directory/'article_chunk_embeddings.npy',mmap_mode='r',allow_pickle=False)
    sums={}
    with (directory/'article_chunks.jsonl').open() as stream:
        for i,line in enumerate(stream):
            aid=json.loads(line)['article_id']
            if aid not in sums:sums[aid]=np.zeros(matrix.shape[1],dtype=np.float32)
            sums[aid]+=matrix[i]
    for aid in sums:sums[aid]/=max(float(np.linalg.norm(sums[aid])),1e-12)
    return sums


def group(records,vectors,previous=None):
    records={r['article_id']:r for r in records};previous=previous or {}
    clusters={};members={};inverted=defaultdict(set)
    anchors=[a for a in previous if a in records]
    ordered=list(dict.fromkeys(anchors+sorted(records,key=lambda a:(records[a].get('published_at') or '',a))))
    titles={aid:words(r['title']) for aid,r in records.items()}
    numbers={aid:quantities(r['text']) for aid,r in records.items()}
    for aid in ordered:
        a=records[aid];t=stamp(a.get('published_at'));tokens=titles[aid]
        choices=set().union(*(inverted[w] for w in tokens)) if tokens else set()
        choices=[sid for sid in choices if t is not None and clusters[sid]['stamp'] is not None
                 and abs(t-clusters[sid]['stamp'])<=POLICY['window_hours']*3600
                 and a.get('kind')=='news' and records[clusters[sid]['anchor']]['kind']=='news']
        best=None
        for sid in sorted(choices):
            anchor=clusters[sid]['anchor'];b=records[anchor]
            overlap=len(tokens&titles[anchor])/max(1,len(tokens|titles[anchor]))
            cosine=float(vectors[aid]@vectors[anchor]) if aid in vectors and anchor in vectors else 0.
            exact=bool(a.get('text_hash')) and a.get('text_hash')==b.get('text_hash')
            if not exact and not (cosine>=POLICY['cosine_min'] and overlap>=POLICY['title_overlap_min']):continue
            if best is None or (exact,cosine,overlap,sid)>best[0]:best=((exact,cosine,overlap,sid),sid)
        if best:
            (exact,cosine,overlap,_),sid=best
            anchor=clusters[sid]['anchor']
            rule='exact_text' if exact else 'semantic_title_candidate'
            strong=exact or (cosine>=POLICY['dedup_cosine_min'] and overlap>=POLICY['dedup_title_overlap']
                            and abs(t-clusters[sid]['stamp'])<=POLICY['dedup_window_hours']*3600)
            # Different quantities can be updates, different indicators or errors; never silently hide them.
            if {(n['value'],n['unit']) for n in numbers[aid]}!={(n['value'],n['unit']) for n in numbers[anchor]}:strong=False
        else:
            sid=previous.get(aid) or 'story_'+hashlib.sha256(aid.encode()).hexdigest()[:32]
            if sid in clusters:sid='story_'+hashlib.sha256(aid.encode()).hexdigest()[:32]
            clusters[sid]={'anchor':aid,'stamp':t,'members':[],'dedup_safe':True}
            for word in tokens:inverted[word].add(sid)
            rule='anchor';cosine=1.;strong=True
        clusters[sid]['members'].append(aid);clusters[sid]['dedup_safe'] &= strong
        members[aid]={'story_id':sid,'rule':rule,'cosine':cosine}
    return clusters,members,numbers


def build(directory,previous=None):
    directory=Path(directory).resolve();target=directory/'stories.sqlite';temp=directory/'stories.building.sqlite'
    prior={};path=Path(previous)/'stories.sqlite' if previous else target
    if path.exists():
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
            prior={aid:sid for sid,aid in db.execute('SELECT story_id,anchor_id FROM stories')}
    with sqlite3.connect((directory/'catalog.sqlite').as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row;records=[dict(r) for r in db.execute('SELECT * FROM articles')]
    vectors=mean_vectors(directory);clusters,members,numbers=group(records,vectors,prior)
    by_id={r['article_id']:r for r in records};temp.unlink(missing_ok=True)
    with sqlite3.connect(temp) as db:
        db.executescript('''CREATE TABLE stories(story_id TEXT PRIMARY KEY,anchor_id TEXT,member_count INT,dedup_safe INT,distinct_hosts INT);
        CREATE TABLE members(article_id TEXT PRIMARY KEY,story_id TEXT,content_hash TEXT,rule TEXT,cosine REAL);
        CREATE INDEX story_members ON members(story_id);
        CREATE TABLE quantities(article_id TEXT,record TEXT);
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);''')
        for sid,c in clusters.items():
            hosts={urlsplit(by_id[a].get('url') or '').hostname for a in c['members']}-{None}
            db.execute('INSERT INTO stories VALUES(?,?,?,?,?)',(sid,c['anchor'],len(c['members']),int(c['dedup_safe']),len(hosts)))
        db.executemany('INSERT INTO members VALUES(?,?,?,?,?)',[(aid,m['story_id'],by_id[aid]['content_hash'],m['rule'],m['cosine']) for aid,m in members.items()])
        db.executemany('INSERT INTO quantities VALUES(?,?)',[(aid,json.dumps(n,ensure_ascii=False)) for aid,rows in numbers.items() for n in rows])
        report={'built_at':datetime.now(timezone.utc).isoformat(),'catalog_sha256':file_sha(directory/'catalog.sqlite'),
            'policy':POLICY,'articles':len(records),'stories':len(clusters),
            'multi_publication_stories':sum(len(c['members'])>1 for c in clusters.values()),
            'multi_host_stories':sum(len({urlsplit(by_id[a].get('url') or '').hostname for a in c['members']}-{None})>1 for c in clusters.values()),
            'deduplicated_groups':sum(len(c['members'])>1 and c['dedup_safe'] for c in clusters.values()),
            'limitations':['Groups are automatic candidate links, not independent corroboration.',
                'Different quantities need manual comparison of indicators/periods; they are not automatically contradictions.']}
        db.execute('INSERT INTO metadata VALUES(?,?)',('report',json.dumps(report,ensure_ascii=False)))
    temp.replace(target)
    (directory/'stories_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True);p.add_argument('--previous',type=Path)
    a=p.parse_args();print(json.dumps(build(a.directory,a.previous),ensure_ascii=False,indent=2))
