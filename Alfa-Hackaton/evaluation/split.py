"""Assign complete event groups to temporal partitions, quarantining boundary overlaps."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path


def timestamp(value):
    stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
    if stamp.tzinfo is None:raise ValueError('Timezone is required')
    return stamp


def partition(records, validation_start, test_start):
    validation_start, test_start = timestamp(validation_start), timestamp(test_start)
    if validation_start >= test_start:raise ValueError('validation_start must precede test_start')
    grouped=defaultdict(list);seen=set()
    for record in records:
        if not record.get('event_group') or not record.get('article_id'):raise ValueError('Event group and article ID required')
        if record['article_id'] in seen:raise ValueError('Duplicate article ID')
        seen.add(record['article_id'])
        date=timestamp(record['published_at'])
        split='train' if date < validation_start else 'validation' if date < test_start else 'test'
        grouped[record['event_group']].append((record,split))
    assignments=[];excluded=[]
    for group, rows in sorted(grouped.items()):
        splits={split for _,split in rows}
        if len(splits)>1:
            excluded.append({'event_group':group,'reason':'event_spans_temporal_boundary',
                             'article_ids':sorted(r['article_id'] for r,_ in rows)})
        else:
            assignments.extend({'article_id':r['article_id'],'event_group':group,'split':split}
                               for r,split in sorted(rows,key=lambda row:row[0]['article_id']))
    return {'validation_start':validation_start.isoformat(),'test_start':test_start.isoformat(),
            'assignments':assignments,'excluded_groups':excluded,
            'counts':dict(Counter(a['split'] for a in assignments)),
            'limitation':'Requires independently verified event groups; automatic clustering can miss duplicates.'}


def audit(assignments):
    groups=defaultdict(set);articles=defaultdict(set)
    for row in assignments:
        if row['split'] not in ('train','validation','test'):raise ValueError('Unknown split')
        groups[row['event_group']].add(row['split']);articles[row['article_id']].add(row['split'])
    leaking_groups=sorted(g for g,parts in groups.items() if len(parts)>1)
    leaking_articles=sorted(a for a,parts in articles.items() if len(parts)>1)
    return {'ok':not (leaking_groups or leaking_articles),
            'leaking_groups':leaking_groups,'leaking_articles':leaking_articles}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--validation-start',required=True);p.add_argument('--test-start',required=True)
    a=p.parse_args()
    if a.input.resolve()==a.output.resolve():p.error('Output must differ from input')
    result=partition(json.loads(a.input.read_text()),a.validation_start,a.test_start)
    result['audit']=audit(result['assignments'])
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
