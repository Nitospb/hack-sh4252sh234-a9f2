"""Frozen, blinded relevance pool and explicit human adjudication; no LLM calls."""
import argparse
from collections import defaultdict
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import random
import re
import sqlite3
import tempfile
import uuid
from recommendations.engine import Feed
from recommendations.catalog import company
from service.context import get_context
from .score import DIMENSIONS,evaluate


def freeze(catalog,assets,output,queries=20,k=5):
    catalog,assets,output=Path(catalog).resolve(),Path(assets).resolve(),Path(output).resolve()
    if output.exists():raise ValueError('Use a new evaluation directory')
    if not 1<=queries<=100 or not 1<=k<=20:raise ValueError('Invalid pool size')
    with sqlite3.connect(catalog.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        rows=[dict(r) for r in db.execute('SELECT * FROM articles WHERE kind="news" AND (eligible_delivery=1 OR object_eligible_delivery=1)')]
        groups={}
        stories=catalog.parent/'stories.sqlite'
        if stories.exists():
            with sqlite3.connect(stories.as_uri()+'?mode=ro',uri=True) as s:groups=dict(s.execute('SELECT article_id,story_id FROM members'))
        companies=[dict(r) for r in db.execute('SELECT * FROM companies ORDER BY source_record_id')]
        names=dict(db.execute('SELECT okved,activity FROM company_activities'))
        mapping=defaultdict(set)
        for code,family in db.execute('SELECT okved,family_key FROM company_family_mapping'):mapping[code].add(family)
        cosine=defaultdict(dict)
        for aid,family,score in db.execute('SELECT article_id,family_key,embedding_cosine FROM family_assignments'):
            cosine[family][aid]=float(score or 0)
    asof=datetime.now(timezone.utc)
    def dated(row):
        try:
            d=datetime.fromisoformat(row['published_at'].replace('Z','+00:00'))
            return d.tzinfo is not None and 0<=(asof-d).total_seconds()<=30*86400
        except (ValueError,AttributeError,TypeError):return False
    articles={r['article_id']:r for r in rows if dated(r)}
    rng=random.Random(4252);rng.shuffle(companies);selected=[];sectors=set()
    # Sample sector representatives before a second company of the same sector.
    for row in companies:
        sector=row['okved'].split('.')[0]
        if sector not in sectors:sectors.add(sector);selected.append(row)
        if len(selected)>=queries:break
    with catalog.open('rb') as source:sha=hashlib.file_digest(source,'sha256').hexdigest()
    bundle={'dataset_version':'frozen-'+sha[:16],'catalog_version':sha,'rubric_version':'v1','split':'validation','as_of':asof.isoformat(),
            'selection':{'seed':4252,'method':'one company per OKVED sector, shuffled records','news_only':True},'queries':[],'tasks':[]}
    with tempfile.TemporaryDirectory(prefix='evaluation-state-') as tmp:
        feed=Feed(catalog,Path(tmp)/'feedback.sqlite');feed.assets=assets
        # Use the normal schema without creating jobs or paying for generation.
        with sqlite3.connect(Path(tmp)/'service.sqlite') as state:
            state.execute('CREATE TABLE clarifications(id TEXT,company TEXT,record_id TEXT,user TEXT,text TEXT,created_at TEXT)')
        for row in selected:
            c=company(feed,row['company_id'],row['source_record_id']);qid=hashlib.sha256(c['source_record_id'].encode()).hexdigest()[:20]
            context=get_context(assets,Path(tmp)/'service.sqlite',c,'evaluation')
            terms=set(re.findall(r'[а-яa-z]{4,}',names.get(c['okved'],'').lower()))
            lexical=sorted(articles,key=lambda aid:(-len(terms & set(re.findall(r'[а-яa-z]{4,}',articles[aid]['title'].lower()))),aid))[:k]
            scores=defaultdict(float)
            for family in mapping[c['okved']]:
                for aid,score in cosine[family].items():
                    if aid in articles:scores[aid]=max(scores[aid],score)
            e5=sorted(scores,key=lambda aid:(-scores[aid],aid))[:k]
            ranked=feed.recommend(c['company_id'],'evaluation',source_record_id=c['source_record_id'],limit=k,kind='news',mode='ranked',role='director',now=asof.timestamp())['items']
            rankings={'lexical_title':lexical,'e5_assigned_candidates':e5,'personalized_pipeline':[a['article_id'] for a in ranked]}
            ids=sorted(set(a for values in rankings.values() for a in values));rng.shuffle(ids)
            if not ids:continue
            q={'query_id':qid,'company_id':c['company_id'],'source_record_id':c['source_record_id'],'role':'director',
               'event_group':'company-pool-'+qid,'published_at':asof.isoformat(),'rankings':rankings,'judgments':[]}
            bundle['queries'].append(q)
            for aid in ids:
                a=articles[aid];bundle['tasks'].append({'task_id':qid+':'+aid,'query_id':qid,'article_id':aid,
                    'event_group':groups.get(aid,aid),'company':c,'facts':context['facts'],'limitations':context['limitations'],
                    'article':{key:a[key] for key in ('article_id','title','text','url','published_at','content_hash')},
                    'analysis':None})
    bundle['limitations']=['E5 baseline ranks stored assigned candidates, not exhaustive dense search.',
        'Lexical baseline uses title token overlap, no supervised tuning.',
        'All queries belong to validation. Test needs a separate time/event-disjoint snapshot.',
        'This pool has no generated analysis: rate relevance only; analysis quality dimensions remain null.',
        'No labels are generated by this tool. No approved human gold exists until explicit adjudication.']
    output.mkdir(parents=True);(output/'pool.json').write_text(json.dumps(bundle,ensure_ascii=False,indent=2))
    # The reviewer artifact hides system names/rankings, but preserves sources/context.
    blind={key:bundle[key] for key in ('dataset_version','catalog_version','rubric_version','tasks','limitations')}
    blind['pool_sha256']=hashlib.sha256((output/'pool.json').read_bytes()).hexdigest()
    (output/'reviewer.html').write_text(HTML.replace('__POOL__',json.dumps(blind,ensure_ascii=False).replace('<','\\u003c')))
    summary={'queries':len(bundle['queries']),'tasks':len(bundle['tasks']),'approved_labels':0,
             'pool_sha256':blind['pool_sha256'],'catalog_version':sha}
    path=output.parent/'evaluation-pilot-status.json';temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(summary));temporary.replace(path)
    return summary


def adjudicate(pool,ratings,output,reviewer):
    if not reviewer.strip():raise ValueError('Adjudicator name required')
    pool,output=Path(pool),Path(output)
    if output.exists():raise ValueError('Use a new adjudicated file')
    raw=pool.read_bytes();bundle=json.loads(raw);expected=hashlib.sha256(raw).hexdigest()
    votes=defaultdict(dict);tasks={t['task_id']:t for t in bundle['tasks']}
    for path in ratings:
        data=json.loads(Path(path).read_text());actor=data.get('reviewer','').strip()
        if not actor or data.get('pool_sha256')!=expected:raise ValueError('Reviewer or pool mismatch')
        for item in data['ratings']:
            tid=item['task_id']
            if tid not in tasks or actor in votes[tid]:raise ValueError('Unknown or duplicate review')
            if type(item.get('relevance')) is not int or item['relevance'] not in range(4) or not item.get('evidence','').strip():raise ValueError('Invalid rating')
            votes[tid][actor]=item
    queries={q['query_id']:q for q in bundle['queries']};conflicts=[]
    for tid,by_reviewer in votes.items():
        # Agreement of two distinct reviewers is required. Disagreement stays pending.
        if len(by_reviewer)<2 or len({r['relevance'] for r in by_reviewer.values()})>1:conflicts.append(tid);continue
        task=tasks[tid];rows=list(by_reviewer.values())
        queries[task['query_id']]['judgments'].append({'article_id':task['article_id'],'relevance':rows[0]['relevance'],
            'origin':'human','status':'adjudicated','reviewer':reviewer,'reviewers':sorted(by_reviewer),
            'evidence':' | '.join(r['evidence'] for r in rows),**{d:None for d in DIMENSIONS}})
    bundle['adjudication']={'adjudicator':reviewer,'pending_or_disagreement':conflicts,'input_sha256':expected,
        'rating_files':[{ 'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()} for p in ratings]}
    output.write_text(json.dumps(bundle,ensure_ascii=False,indent=2))
    return evaluate(bundle,k=5)


HTML='''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Независимая оценка релевантности</title><style>body{font:16px system-ui;max-width:1000px;margin:30px auto;padding:16px;color:#202939}button,input,select,textarea{font:inherit;padding:10px;margin:6px 0;max-width:100%;box-sizing:border-box}textarea{width:100%;min-height:80px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f7;padding:16px}article{white-space:pre-wrap;max-height:380px;overflow:auto}nav{display:flex;gap:12px;flex-wrap:wrap}.notice{color:#667286}button{cursor:pointer}</style><h1>Оценка новости для компании</h1><p>Не обсуждайте ответы с другим оценщиком до экспорта. 0 — неприменимо; 1 — общий контекст; 2 — полезно при явных условиях; 3 — приоритетное событие с подтверждённой экспозицией. Это оценка релевантности, не точности сгенерированного анализа.</p><label>Ваше имя <input id="reviewer" autocomplete="off"></label><nav><button id="prev">Назад</button><button id="next">Далее</button><button id="export">Выгрузить оценки</button></nav><p id="progress" role="status"></p><h2 id="title"></h2><p id="company"></p><details><summary>Факты и ограничения компании</summary><pre id="facts"></pre></details><a id="url" target="_blank" rel="noreferrer">Первоисточник ↗</a><article id="text"></article><label>Оценка <select id="grade"><option value="">Не оценено</option><option value="0">0</option><option value="1">1</option><option value="2">2</option><option value="3">3</option></select></label><label>Основание оценки: факт компании, фрагмент новости, условия<textarea id="evidence"></textarea></label><p class="notice">Оценки остаются локально в этом окне до выгрузки. Экспортируйте перед закрытием.</p><script>const pool=__POOL__;let index=0;const ratings={};const el=id=>document.getElementById(id);function save(){const t=pool.tasks[index];if(t&&el('grade').value!==''&&el('evidence').value.trim())ratings[t.task_id]={task_id:t.task_id,relevance:Number(el('grade').value),evidence:el('evidence').value.trim()};else if(t)delete ratings[t.task_id]}function show(){const t=pool.tasks[index];if(!t)return;el('title').textContent=t.article.title;el('text').textContent=t.article.text;el('company').textContent=t.company.company_id+' · '+t.company.activity+' · '+t.article.published_at;el('facts').textContent=JSON.stringify({facts:t.facts,limitations:t.limitations},null,2);el('url').removeAttribute('href');if(/^https?:\\/\\//.test(t.article.url))el('url').href=t.article.url;el('grade').value=ratings[t.task_id]?.relevance??'';el('evidence').value=ratings[t.task_id]?.evidence??'';el('progress').textContent=(index+1)+' / '+pool.tasks.length+' · заполнено '+Object.keys(ratings).length;el('prev').disabled=index===0;el('next').disabled=index===pool.tasks.length-1}el('prev').onclick=()=>{save();index--;show()};el('next').onclick=()=>{save();index++;show()};el('export').onclick=()=>{save();if(!el('reviewer').value.trim()){alert('Укажите имя оценщика');return}const blob=new Blob([JSON.stringify({reviewer:el('reviewer').value.trim(),pool_sha256:pool.pool_sha256,ratings:Object.values(ratings)},null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='human-ratings.json';a.click();URL.revokeObjectURL(a.href);show()};show();</script></html>'''


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    f=sub.add_parser('freeze');f.add_argument('--catalog',type=Path,required=True);f.add_argument('--assets',type=Path,required=True);f.add_argument('--output',type=Path,required=True);f.add_argument('--queries',type=int,default=20);f.add_argument('--k',type=int,default=5)
    a=sub.add_parser('adjudicate');a.add_argument('--pool',type=Path,required=True);a.add_argument('--ratings',type=Path,nargs='+',required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--reviewer',required=True)
    args=vars(p.parse_args());command=args.pop('command');print(json.dumps((freeze if command=='freeze' else adjudicate)(**args),ensure_ascii=False,indent=2))
