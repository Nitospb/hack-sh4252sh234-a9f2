"""Read-only catalog queries shared by the local API and web UI."""
import json
import os
import sqlite3
import re
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
RELATION_RANK = {'declared_activity':3,'activity_scope_candidate':2,'operating_exposure':1}

def health(feed):
    with feed.source() as db:
        kinds = {r[0]:r[1] for r in db.execute('SELECT kind,count(*) FROM articles GROUP BY kind')}
        counts = dict(articles=sum(kinds.values()), **{'news':0,'telegram_post':0,**kinds})
        counts['companies'] = db.execute('SELECT count(DISTINCT company_id) FROM companies').fetchone()[0]
        counts['accepted_articles'] = db.execute('SELECT count(DISTINCT article_id) FROM family_assignments WHERE status=\'accepted\'').fetchone()[0]
        counts['review_articles'] = db.execute('SELECT count(DISTINCT article_id) FROM family_assignments WHERE status=\'review\'').fetchone()[0]
    report_path = feed.catalog.parent / 'report.json'
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    ranking_path=feed.catalog.parent/'ranking_report.json'
    ranking_report=json.loads(ranking_path.read_text()) if ranking_path.exists() else {}
    story_path=feed.catalog.parent/'stories_report.json'
    story_report=json.loads(story_path.read_text()) if story_path.exists() else {}
    return {'story_groups':story_report.get('multi_publication_stories',0),'multi_host_story_groups':story_report.get('multi_host_stories',0),'ok':True,'counts':counts,'catalog_updated_at':report.get('created_at'),'llm_available':bool(os.getenv('ALFA_API_KEY')),
            'ranking_version':ranking_report.get('built_at','original'),'business_candidates':ranking_report.get('business_eligible_articles',0),
            'measured_precision':None,'dataset_kind':'synthetic' if report.get('synthetic') else 'collected','mode':'local_prototype','semantic_model':'multilingual-e5-small + mMiniLM reranker'}

def companies(feed, query='', limit=25):
    limit = max(1,min(int(limit),100))
    ranking = feed.catalog.parent / 'ranking.sqlite'
    with feed.source() as db:
        has_ranking = ranking.exists()
        if has_ranking:
            db.execute('ATTACH DATABASE ? AS rank', (ranking.resolve().as_uri()+'?mode=ro',))
            extra = 'COALESCE(r.matched_articles,0) AS available_count,COALESCE(r.direct_articles,0) AS industry_count,COALESCE(p.topic_count,0) AS topic_count'
            joins = ' LEFT JOIN rank.company_coverage r USING(source_record_id) LEFT JOIN rank.company_profiles p USING(source_record_id)'
        else:
            extra = '0 AS available_count,0 AS industry_count,0 AS topic_count'
            joins = ''
        base = 'SELECT c.company_id,c.source_record_id,c.okved,c.region,c.group_id,a.activity,'+extra+' FROM companies c LEFT JOIN company_activities a USING(okved)'+joins
        if query.strip():
            rows = db.execute(base+' WHERE c.company_id LIKE ? OR c.okved LIKE ? OR a.activity LIKE ? ORDER BY (c.company_id=?) DESC,industry_count DESC,available_count DESC,c.company_id LIMIT ?',
                ('%'+query+'%',query+'%','%'+query+'%',query,limit)).fetchall()
        else:
            rows=[]
            # Distinct real sectors, selected for corpus coverage, never invented brands.
            for prefix in ['62.01','47.11','01.11','41.20','49.41']:
                row=db.execute(base+' WHERE c.okved LIKE ? ORDER BY industry_count DESC,available_count DESC,c.company_id LIMIT 1',(prefix+'%',)).fetchone()
                if row and row['available_count']>=40 and row['source_record_id'] not in {r['source_record_id'] for r in rows}: rows.append(row)
            rows=rows[:limit]
            if not rows:
                rows=db.execute(base+' ORDER BY industry_count DESC,available_count DESC,c.company_id LIMIT ?',(limit,)).fetchall()
    items=[]
    for row in rows:
        item=dict(row)
        code=item['okved'] or ''
        item['display_label']=next((label for prefix,label in [('62','Разработка ПО'),('46','Оптовая торговля'),('41','Строительство'),('49','Перевозки'),('01','Растениеводство'),('10','Производство продуктов'),('69','Деловые услуги'),('47','Розничная торговля')] if code.startswith(prefix)),item['activity'])
        item['accepted_count']=item['industry_count']
        items.append(item)
    return {'items':items,'coverage_note':'Candidate pool includes company, sector and general business context. Counts are before personal history and MMR.'}

def company(feed, uid, source_record_id=None):
    with feed.source() as db:
        rows = db.execute('SELECT c.*,a.activity FROM companies c LEFT JOIN company_activities a USING(okved) WHERE company_id=?',(uid,)).fetchall()
        if source_record_id: rows = [r for r in rows if r['source_record_id']==source_record_id]
        if not rows: raise ValueError('company not found')
        if len(rows)>1: raise ValueError('ambiguous company: supply source_record_id')
        result = dict(rows[0]); objects = {}
        for r in db.execute('SELECT m.*,f.object,f.sector_name FROM company_family_mapping m JOIN object_families f USING(family_key) WHERE okved=?',(result['okved'],)):
            r = dict(r); key = r['family_key']
            if key not in objects or RELATION_RANK[r['relation']] > RELATION_RANK[objects[key]['relation']]: objects[key]=r
        ranking=feed.catalog.parent/'ranking.sqlite'
        families={r['family_key']:dict(r) for r in db.execute('SELECT * FROM object_families')}
        if ranking.exists():
            with sqlite3.connect(ranking.resolve().as_uri()+'?mode=ro',uri=True) as rank:
                rank.row_factory=sqlite3.Row
                profile=rank.execute('SELECT operating_families FROM company_profiles WHERE source_record_id=?',(result['source_record_id'],)).fetchone()
                defaults={r['family_key']:dict(r) for r in rank.execute('SELECT * FROM operating_defaults')}
                for key in json.loads(profile[0]) if profile else defaults:
                    if key not in objects and key in families:
                        f=families[key]
                        objects[key]={'okved':result['okved'],'family_key':key,'object':f['object'],'sector_name':f['sector_name'],
                            'relation':'operating_exposure','reason':defaults.get(key,{}).get('reason','Возможный операционный интерес по профилю ОКВЭД; не подтверждённая специализация.')}
        for key,item in objects.items():
            item['topic_ids']=json.loads(families.get(key,{}).get('reference_member_topic_ids') or '[]')
        result['interests'] = sorted(objects.values(),key=lambda r:(-RELATION_RANK[r['relation']],r['object']))
        result['interest_method'] = 'inferred_from_okved'
        result['names_available'] = False
        result['interest_counts']={relation:sum(i['relation']==relation for i in objects.values()) for relation in RELATION_RANK}
    from recommendations.context_summary import business_context
    result['business_context']=business_context(feed.assets,result)
    return result

def profile_state(feed, uid, user):
    with feed.connect() as db:
        cols={r[1] for r in db.execute('PRAGMA table_info(profiles)')}
        row=db.execute('SELECT topics'+(',role' if 'role' in cols else '')+' FROM profiles WHERE company=? AND user=?',(uid,user)).fetchone()
        events=db.execute('SELECT article,kind,ts FROM events WHERE company=? AND user=? ORDER BY ts,rowid',(uid,user)).fetchall()
    states={};views=set()
    toggle={'like':('liked',True),'unlike':('liked',False),'save':('saved',True),'unsave':('saved',False),
            'hide':('hidden',True),'unhide':('hidden',False),'dislike':('disliked',True),'undislike':('disliked',False)}
    for aid,kind,stamp in events:
        state=states.setdefault(aid,{})
        if kind in toggle:
            field,value=toggle[kind];state[field]=value
        if kind in ('view','open'):state['viewed']=True;views.add(aid)
    return {**feed.feed_settings(uid,user),'company_id':uid,'user_id':user,'topic_ids':json.loads(row[0]) if row else [],
            'role':row[1] if row and len(row)>1 else 'general','article_states':states,
            'stats':{'viewed':len(views),'saved':sum(bool(s.get('saved')) for s in states.values()),'liked':sum(bool(s.get('liked')) for s in states.values())}}

def saved(feed, uid, user):
    state=profile_state(feed,uid,user)
    ids=[aid for aid,s in state['article_states'].items() if s.get('saved')]
    items=[]
    with feed.source() as db:
        for aid in ids:
            row=db.execute('SELECT article_id,title,source,url,published_at,kind,text FROM articles WHERE article_id=?',(aid,)).fetchone()
            if row:
                item=dict(row);item['excerpt']=re.sub(r'\s+',' ',item.pop('text'))[:420];items.append(item)
    items.sort(key=lambda a:a['published_at'] or '',reverse=True)
    return {'items':items,'total':len(items)}

def article(feed, aid):
    with feed.source() as db:
        a = db.execute('SELECT * FROM articles WHERE article_id=?',(aid,)).fetchone()
        if not a: raise ValueError('article not found')
        result = dict(a); result['images'] = json.loads(result.get('images') or '[]')
        result['object_matches'] = [dict(r) for r in db.execute('SELECT a.*,f.object,f.sector_name FROM family_assignments a JOIN object_families f USING(family_key) WHERE article_id=? ORDER BY reranker_logit DESC',(aid,))]
    from recommendations.stories import context
    result["story"]=context(feed,result)
    return result

def news(feed, query='', kind='all', offset=0, limit=30):
    if kind not in ('all','news','telegram_post'): raise ValueError('invalid kind')
    limit=max(1,min(int(limit),100));offset=max(0,int(offset))
    where=[];args=[]
    if query: where.append('(title LIKE ? OR text LIKE ?)');args += ['%'+query+'%']*2
    if kind!='all':where.append('kind=?');args.append(kind)
    clause=' WHERE '+' AND '.join(where) if where else ''
    with feed.source() as db:
        total=db.execute('SELECT count(*) FROM articles'+clause,args).fetchone()[0]
        rows=db.execute('SELECT article_id,title,url,source,published_at,kind,status,eligible_delivery FROM articles'+clause+' ORDER BY published_at DESC,article_id LIMIT ? OFFSET ?',(*args,limit,offset)).fetchall()
    return {'items':[dict(r) for r in rows],'total':total,'offset':offset,'limit':limit}

def insight(feed, uid, aid, source_record_id=None, generate=False, role='general'):
    c = company(feed,uid,source_record_id); a = article(feed,aid)
    interests = {r['family_key']:r for r in c['interests']}
    matches = [{**r,'company_reason':interests[r['family_key']]['reason'],'relation':interests[r['family_key']]['relation']}
               for r in a['object_matches'] if r['family_key'] in interests]
    sys.path.insert(0,str(ROOT))
    from insight_generation.explanation import build_explanation
    industries=[]
    ranking=feed.catalog.parent/'ranking.sqlite'
    if ranking.exists():
        with sqlite3.connect(ranking.resolve().as_uri()+'?mode=ro',uri=True) as rank:
            rank.row_factory=sqlite3.Row
            if rank.execute("SELECT 1 FROM sqlite_master WHERE name='article_industries'").fetchone():
                industries=[dict(r) for r in rank.execute('SELECT a.*,c.reason FROM article_industries a JOIN company_industries c USING(sector_id) WHERE a.article_id=? AND c.okved=?',(aid,c['okved']))]
    result=build_explanation(c,a,viewer_role=role,matches=matches,industries=industries)
    result.update(company_id=uid,article_id=aid,llm_available=bool(os.getenv('ALFA_API_KEY')))
    if generate:
        if not os.getenv('ALFA_API_KEY'): raise ValueError('ALFA_API_KEY is not configured on the server')
        if not matches: raise ValueError('no evidence of company relevance')
        if not a['eligible_delivery']: raise ValueError('article fails date or text quality gates')
        if not any(r['status']=='accepted' for r in matches): raise ValueError('semantic candidates require review before LLM analysis')
        sys.path.insert(0,str(ROOT))
        from insight_generation.client import generate as llm_generate
        facts=[{'id':'company_okved','field':'okved','value':c['okved'],'evidence_level':'confirmed'},
               {'id':'company_activity','field':'declared_activity','value':c['activity'],'evidence_level':'confirmed'}]
        payload={'as_of':datetime.now(timezone.utc).isoformat(),'company_facts':facts,'news':{'id':aid,'title':a['title'],'text':a['text'],'published_at':a['published_at'],'url':a['url']},'bank_passages':[],'viewer_role':role}
        result=llm_generate(payload)
    return result
