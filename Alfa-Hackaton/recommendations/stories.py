"""Read version-paired story evidence; never invent source independence or numeric conflicts."""
from collections import defaultdict
from datetime import datetime,timezone,timedelta
import json
import sqlite3
from urllib.parse import urlsplit


def context(feed,article,as_of=None):
    path=feed.catalog.parent/'stories.sqlite'
    if not path.is_file():return None
    cutoff=as_of or datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        story=db.execute('SELECT s.* FROM stories s JOIN members m USING(story_id) WHERE m.article_id=?',(article['article_id'],)).fetchone()
        if not story:return None
        members=[dict(r) for r in db.execute('SELECT article_id,content_hash,rule,cosine FROM members WHERE story_id=?',(story['story_id'],))]
        quantities=defaultdict(list)
        for m in members:
            quantities[m['article_id']]=[json.loads(r[0]) for r in db.execute('SELECT record FROM quantities WHERE article_id=?',(m['article_id'],))]
    items=[]
    with feed.source() as db:
        for member in members:
            row=db.execute('SELECT article_id,content_hash,title,text,url,source,published_at,kind,eligible_delivery FROM articles WHERE article_id=?',(member['article_id'],)).fetchone()
            if not row or row['content_hash']!=member['content_hash']:continue
            item=dict(row)
            # Related evidence has exactly the same date/text gates as serving news.
            if item['kind']!='news' or not item['eligible_delivery'] or not item['published_at']:continue
            try:
                date=datetime.fromisoformat(item['published_at'].replace('Z','+00:00'))
                end=datetime.fromisoformat(cutoff.replace('Z','+00:00'))
                if date.tzinfo is None or end.tzinfo is None or date>end or date<end-timedelta(days=30):continue
            except ValueError:continue
            item.update(match_rule=member['rule'],similarity=member['cosine'],quantities=quantities[item['article_id']])
            items.append(item)
    items.sort(key=lambda x:(x['published_at'],x['article_id']),reverse=True)
    items.sort(key=lambda x:x['article_id']!=article['article_id'])
    items=items[:6]
    variants=defaultdict(lambda:defaultdict(list))
    for item in items:
        for number in item['quantities']:
            variants[number['unit']][number['value']].append({'article_id':item['article_id'],'quote':number['quote']})
    differences=[]
    for unit,values in variants.items():
        per_article=defaultdict(set)
        for value,evidence in values.items():
            for fragment in evidence:per_article[fragment['article_id']].add(value)
        if len(per_article)>=2 and len({tuple(sorted(v)) for v in per_article.values()})>1:
            differences.append({'unit':unit,'values':[{'value':value,'evidence':evidence} for value,evidence in values.items()],
                'status':'needs_comparison','note':'Проверьте показатель, период и единицы; различие чисел само по себе не доказывает противоречие.'})
    return {'story_id':story['story_id'],'member_count':story['member_count'],
        'visible_evidence_count':len(items),'distinct_hosts':len({urlsplit(x['url']).hostname for x in items}),
        'dedup_safe':bool(story['dedup_safe']),'items':items,
        'numeric_variants':differences,
        'limitations':['Автоматическая группа похожих публикаций, не ручное подтверждение общего события.',
            'Разные домены не доказывают независимость редакций или первичных источников.']}


def membership(feed):
    path=feed.catalog.parent/'stories.sqlite'
    if not path.is_file():return {}
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        return {aid:{'story_id':sid,'story_publications':count,'dedup_safe':bool(safe)}
                for aid,sid,count,safe in db.execute('SELECT m.article_id,s.story_id,s.member_count,s.dedup_safe FROM members m JOIN stories s USING(story_id)')}
