"""Evaluate frozen ranked pools against explicitly adjudicated human judgments."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import statistics

DIMENSIONS = ('exposure_correct', 'claims_supported', 'numbers_correct',
              'bank_ai_separated', 'action_useful', 'abstention_appropriate')


def mean(values):
    return statistics.mean(values) if values else None


def interval(values):
    if len(values) < 2:return None
    rng=random.Random(4252)
    estimates=sorted(statistics.mean(rng.choices(values,k=len(values))) for _ in range(2000))
    return [estimates[49],estimates[1949]]


def evaluate(bundle, k=10):
    if type(k) is not int or not 1 <= k <= 100:raise ValueError('k must be 1..100')
    for field in ('dataset_version','catalog_version','rubric_version','split'):
        if not isinstance(bundle.get(field),str) or not bundle[field]:raise ValueError('Missing version: '+field)
    if bundle['split'] not in ('validation','test'):raise ValueError('Use an independent validation or test split')
    queries=bundle['queries'];seen=set();results={};labels=0;excluded=Counter()
    for q in queries:
        qid=q['query_id']
        if qid in seen:raise ValueError('Duplicate query')
        seen.add(qid)
        for field in ('company_id','source_record_id','role','event_group','published_at'):
            if not q.get(field):raise ValueError('Missing query context: '+field)
        stamp=datetime.fromisoformat(q['published_at'].replace('Z','+00:00'))
        if stamp.tzinfo is None:raise ValueError('Publication timezone required')
        judged={};all_ids=set()
        for j in q.get('judgments',[]):
            aid=j['article_id']
            if aid in all_ids:raise ValueError('Duplicate judgment')
            all_ids.add(aid)
            if j.get('status') != 'adjudicated' or j.get('origin') != 'human':
                excluded['not_adjudicated_human']+=1;continue
            if not j.get('reviewer') or not j.get('evidence'):
                raise ValueError('Human judgment requires reviewer and evidence')
            grade=j.get('relevance')
            if type(grade) is not int or grade not in range(4):raise ValueError('Relevance must be 0..3')
            for d in DIMENSIONS:
                if j.get(d) is not None and type(j[d]) is not bool:raise ValueError('Rubric dimensions must be bool or null')
            judged[aid]=j;labels+=1
        for system, ranking in q['rankings'].items():
            if len(ranking) != len(set(ranking)):raise ValueError('Duplicate ranked article')
            top=ranking[:k];known=[judged[a] for a in top if a in judged]
            positives=sum(j['relevance']>=2 for j in known)
            unknown=len(top)-len(known)
            ideal=sorted((j['relevance'] for j in judged.values()),reverse=True)[:k]
            idcg=sum((2**grade-1)/math.log2(i+2) for i,grade in enumerate(ideal))
            fully_judged=bool(top) and not unknown
            ndcg=None
            if fully_judged and idcg:
                ndcg=sum((2**judged[a]['relevance']-1)/math.log2(i+2) for i,a in enumerate(top))/idcg
            rows=results.setdefault(system,[])
            rows.append({'query_id':qid,'returned':len(top),'judged':len(known),
                'precision_at_k':positives/k if fully_judged else None,
                'precision_lower_bound':positives/k,
                'precision_upper_bound':(positives+unknown)/k,
                'judgment_coverage':len(known)/len(top) if top else None,
                'ndcg_at_k_judged_pool':ndcg,
                'dimensions':{d:mean([int(j[d]) for j in known if j.get(d) is not None]) for d in DIMENSIONS}})
    systems={}
    for system, rows in results.items():
        metrics={}
        for field in ('precision_at_k','ndcg_at_k_judged_pool','judgment_coverage','precision_lower_bound','precision_upper_bound'):
            values=[r[field] for r in rows if r[field] is not None]
            metrics[field]={'mean':mean(values),'evaluated_queries':len(values),
                            'bootstrap_query_95pct':interval(values)}
        systems[system]={'queries':rows,'metrics':metrics,
            'dimensions':{d:{'mean':mean([r['dimensions'][d] for r in rows if r['dimensions'][d] is not None]),
                             'evaluated_queries':sum(r['dimensions'][d] is not None for r in rows)} for d in DIMENSIONS}}
    return {'versions':{key:bundle[key] for key in ('dataset_version','catalog_version','rubric_version','split')},
        'k':k,'queries':len(queries),'adjudicated_human_pairs':labels,'excluded':dict(excluded),'systems':systems,
        'limitations':['nDCG denominator is the judged candidate pool, not all news.',
          'Missing judgments are unknown; precision is null until the returned top-k is fully judged.',
          'Short results count unfilled slots as non-relevant for precision@k.',
          'Bootstrap resamples queries; fewer than two evaluated queries yields no interval.',
          'Do not choose thresholds or prompts using test results.']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--k',type=int,default=10)
    a=p.parse_args()
    if a.input.resolve()==a.output.resolve():p.error('Output must differ from the frozen input')
    raw=a.input.read_bytes();result=evaluate(json.loads(raw),a.k)
    result['input_sha256']=hashlib.sha256(raw).hexdigest()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
