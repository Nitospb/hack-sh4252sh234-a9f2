"""Local recommendation service: immutable news catalog, separate feedback store."""
import json
import math
import os
import re
import sqlite3
import time
import threading
from types import MappingProxyType
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = {'company': .60, 'general': .10, 'popular': .10, 'personal': .20}
ROLE_TERMS = {'accountant': 'налог бухгалтер отчетн ндс учет аудит', 'treasurer': 'ставк валют ликвидност платеж кредит облигац', 'director': 'рынок стратеги инвестици экономик бизнес', 'it': 'ии искусствен интеллект технолог программ кибер цифров', 'sales': 'продаж спрос потребител розниц маркетинг экспорт', 'finance':'ставк валют ликвидност платеж кредит облигац', 'procurement':'закуп поставк сырь логист транспорт цен', 'general':'экономик бизнес технолог рынок'}
SIGNALS = {'view': .08, 'open': .15, 'like': 1., 'save': 1.5, 'dislike': -1., 'hide': -2., 'unlike':0., 'unsave':0., 'unhide':0., 'undislike':0.}

def publication_stamp(value):
    date=datetime.fromisoformat(value.replace('Z','+00:00'))
    return date.replace(tzinfo=date.tzinfo or timezone.utc).timestamp()

def tokens(text):
    return set(re.findall(r'\w{3,}', text.lower()))

def jaccard(a, b):
    return len(a & b) / max(1, len(a | b))

class Feed:
    def __init__(self, catalog=None, state=None, embeddings=True):
        default = ROOT / 'pipeline/output/catalog.sqlite'
        self.catalog = Path(catalog or os.environ.get('ALFA_CATALOG') or (default if default.exists() else ROOT / 'news_matching/output/news_topics.sqlite'))
        self.assets = Path(os.getenv('ALFA_ASSETS') or self.catalog.parent/'service-assets.sqlite')
        self.state = Path(state or ROOT / 'recommendations/state.sqlite')
        self.state.parent.mkdir(parents=True, exist_ok=True)
        self._article_cache={};self._article_cache_lock=threading.Lock()
        with self.connect() as db:
            db.executescript('''PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS events(event_id TEXT PRIMARY KEY, company TEXT, user TEXT,
              article TEXT, kind TEXT, ts REAL);
            CREATE INDEX IF NOT EXISTS event_context ON events(company,user,ts);
            CREATE TABLE IF NOT EXISTS deliveries(request_id TEXT PRIMARY KEY,company TEXT,user TEXT,
              ts REAL,response TEXT);
            CREATE TABLE IF NOT EXISTS profiles(company TEXT,user TEXT,topics TEXT,
              PRIMARY KEY(company,user));''')
        with self.connect() as db:
            if 'role' not in {r[1] for r in db.execute('PRAGMA table_info(profiles)')}:
                db.execute("ALTER TABLE profiles ADD COLUMN role TEXT DEFAULT 'director'")
        self.embeddings_enabled = embeddings
        self.encoder_sha = None
        self.vectors = {}
        if embeddings:
            self.load_vectors()

    def __del__(self):
        lease=getattr(self,"_generation_lease",None)
        if lease is not None:lease.close()

    def connect(self):
        return sqlite3.connect(str(self.state), timeout=30)

    def source(self):
        db = sqlite3.connect(self.catalog.resolve().as_uri() + '?mode=ro', uri=True)
        db.row_factory = sqlite3.Row
        return db

    def load_vectors(self):
        directory = self.catalog.parent
        metadata=directory/"embedding_metadata.json"
        if metadata.is_file():self.encoder_sha=json.loads(metadata.read_text())["fingerprint"]["model_sha256"]
        if not (directory / 'article_chunk_embeddings.npy').exists():
            return
        import numpy as np
        matrix = np.load(directory / 'article_chunk_embeddings.npy', mmap_mode='r')
        counts = Counter()
        with (directory / 'article_chunks.jsonl').open() as stream:
            for i, line in enumerate(stream):
                aid = json.loads(line)['article_id']
                self.vectors[aid] = self.vectors.get(aid, np.zeros(matrix.shape[1])) + matrix[i]
                counts[aid] += 1
        for aid, vector in self.vectors.items():
            self.vectors[aid] = vector / max(float(np.linalg.norm(vector)), 1e-12)

    def profile(self, company, user, topic_ids, role="director"):
        if role not in ROLE_TERMS:
            raise ValueError("unknown role")
        if not isinstance(topic_ids, list) or len(topic_ids) > 100 or any(not isinstance(t,str) for t in topic_ids):
            raise ValueError('topic_ids must be a list of at most 100 topic IDs')
        with self.source() as db:
            known = {r[0] for r in db.execute('SELECT topic_id FROM topics')}
        if not set(topic_ids) <= known:
            raise ValueError('unknown topic ID')
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO profiles(company,user,topics,role) VALUES(?,?,?,?)', (company,user,json.dumps(topic_ids),role))

    def event(self, company, user, article_id, kind, event_id):
        if kind not in SIGNALS or not event_id:
            raise ValueError('invalid event kind or missing event_id')
        with self.source() as db:
            if not db.execute('SELECT 1 FROM articles WHERE article_id=?', (article_id,)).fetchone():
                raise ValueError('unknown article')
        payload = (company,user,article_id,kind)
        with self.connect() as db:
            prior = db.execute('SELECT company,user,article,kind FROM events WHERE event_id=?',(event_id,)).fetchone()
            if prior and prior != payload:
                raise ValueError('event_id reused with different payload')
            if not prior:
                db.execute('INSERT INTO events VALUES(?,?,?,?,?,?)',(event_id,*payload,time.time()))
        return {'event_id':event_id, 'recorded':not bool(prior)}

    def similarity(self, a, b):
        if a['article_id'] in self.vectors and b['article_id'] in self.vectors:
            return max(0., float(self.vectors[a['article_id']] @ self.vectors[b['article_id']]))
        return max(jaccard(a['_tokens'],b['_tokens']), jaccard(a['_topics'],b['_topics']))

    def article_rows(self,db,wide=False):
        condition='eligible_delivery=1 OR object_eligible_delivery=1' if wide else 'eligible_delivery=1'
        immutable=bool(re.fullmatch('[0-9a-f]{64}',self.catalog.parent.name)) and (self.catalog.parent/'manifest.json').is_file()
        def read(prepared):
            rows=[]
            for row in db.execute('SELECT * FROM articles WHERE '+condition):
                item=dict(row)
                if prepared:
                    text=re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',item.pop('text','') or '')).strip()
                    item['reading_minutes']=max(1,math.ceil(len(text.split())/200))
                    item['excerpt']=' '.join(re.split(r'(?<=[.!?])\s+',text)[:2])[:420]
                    item['_feed_prepared']=True
                    item.pop('images',None)
                rows.append(MappingProxyType(item) if prepared else item)
            return tuple(rows)
        if not immutable:return {r['article_id']:dict(r) for r in read(False)}
        with self._article_cache_lock:
            if wide not in self._article_cache:self._article_cache[wide]=read(True)
            rows=self._article_cache[wide]
        # Scores, roles, reactions and exclusions always belong to this request.
        return {r['article_id']:dict(r) for r in rows}

    def recommend(self, company, user, limit=20, source_record_id=None, request_id=None, now=None,
                  scope='activity', include_review=False, kind='all', mode='strict', role=None):
        scopes = {'strict': {'declared_activity'}, 'activity': {'declared_activity','activity_scope_candidate'},
                  'interest': {'declared_activity','activity_scope_candidate','operating_exposure'}}
        if mode not in ('strict','ranked') or (role is not None and role not in ROLE_TERMS):
            raise ValueError('invalid mode or role')
        if scope not in scopes or kind not in ('all','news','telegram_post'):
            raise ValueError('invalid scope or kind')
        if not isinstance(limit,int) or not 1 <= limit <= 100:
            raise ValueError('limit must be 1..100')
        request_context={'source_record_id':source_record_id,'scope':scope,'include_review':include_review,'kind':kind,'mode':mode,'role':role,'limit':limit}
        request_context['catalog_version']=f'{self.catalog.stat().st_mtime_ns}:{self.catalog.stat().st_size}'
        request_context['policy']='ranked-v5-story-groups'
        request_context['assets_version']=f'{self.assets.stat().st_mtime_ns}:{self.assets.stat().st_size}' if self.assets.is_file() else None
        now = time.time() if now is None else now
        with self.connect() as state:
            preferences_row=state.execute('SELECT topics,role FROM profiles WHERE company=? AND user=?',(company,user)).fetchone()
            request_context['profile']=list(preferences_row) if preferences_row else None
            if request_id:
                cached = state.execute('SELECT company,user,response,ts FROM deliveries WHERE request_id=?',(request_id,)).fetchone()
                if cached:
                    if cached[:2] != (company,user):
                        raise ValueError('request_id belongs to another context')
                    response=json.loads(cached[2])
                    expected=request_context
                    if response.get('request_context') and any(response['request_context'].get(k)!=expected.get(k) for k in ('source_record_id','scope','include_review','kind','mode','role','limit')):
                        raise ValueError('request_id reused with different parameters')
                    if response.get('request_context')==expected and cached[3]>now-1800 and all(now-30*86400<=publication_stamp(a['published_at'])<=now for a in response['items']):
                        return response
                    state.execute('DELETE FROM deliveries WHERE request_id=?',(request_id,))
            history = state.execute('SELECT article,kind,ts FROM events WHERE company=? AND user=?',(company,user)).fetchall()
            impressions = state.execute('SELECT response FROM deliveries WHERE company=? AND user=? AND ts>?',(company,user,now-1800)).fetchall()
            profile = state.execute('SELECT topics,role FROM profiles WHERE company=? AND user=?',(company,user)).fetchone()
            # One capped contribution per actor/article/kind prevents repeat-event popularity inflation.
            popularity = state.execute('''SELECT e.article,count(DISTINCT e.company || char(0) || e.user)
                FROM events e WHERE e.kind IN ('like','save','open') AND e.ts>?
                AND NOT EXISTS (SELECT 1 FROM events undo WHERE undo.company=e.company AND undo.user=e.user
                  AND undo.article=e.article AND undo.ts>=e.ts AND undo.kind=CASE e.kind WHEN 'like' THEN 'unlike'
                    WHEN 'save' THEN 'unsave' ELSE '__none__' END)
                GROUP BY e.article''',(now-7*86400,)).fetchall()
        # Toggle actions resolve to the latest state; impressions are never fabricated as views.
        toggle_groups = {'like':'like','unlike':'like','save':'save','unsave':'save',
                         'hide':'hide','unhide':'hide','dislike':'dislike','undislike':'dislike'}
        latest = {}
        ordinary = []
        for aid,event_kind,stamp in sorted(history,key=lambda row:row[2]):
            if event_kind in toggle_groups:
                latest[(aid,toggle_groups[event_kind])] = (aid,event_kind,stamp)
            else:
                ordinary.append((aid,event_kind,stamp))
        history = ordinary + [row for row in latest.values() if not row[1].startswith('un')]
        explicit = set(json.loads(profile[0])) if profile else set()
        role = role or (profile[1] if profile else 'director')
        with self.source() as db:
            profiles = db.execute('SELECT * FROM companies WHERE company_id=?',(company,)).fetchall()
            if source_record_id:
                profiles = [p for p in profiles if p['source_record_id']==source_record_id]
            if not profiles:
                raise ValueError('company or source_record_id not found')
            if len(profiles)>1:
                raise ValueError('ambiguous company: supply source_record_id')
            priority = {'declared_activity':3,'activity_scope_candidate':2,'operating_exposure':1}
            interests = {}
            for r in db.execute('SELECT topic_id,relation FROM company_mapping WHERE okved=?',(profiles[0]['okved'],)):
                if r['relation'] in scopes[scope] and priority[r['relation']] > priority.get(interests.get(r['topic_id']),0):
                    interests[r['topic_id']] = r['relation']
            topic_names = {r[0]:r[1] for r in db.execute('SELECT topic_id,name FROM topics')}
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            articles = self.article_rows(db,wide='company_family_mapping' in tables)
            assignments = {}
            for r in db.execute('SELECT * FROM assignments'):
                assignments.setdefault(r['article_id'],set()).add(r['topic_id'])
            family_interests, family_matches, family_names = {}, {}, {}
            explicit_objects = set()
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'company_family_mapping' in tables:
                for r in db.execute('SELECT * FROM company_family_mapping WHERE okved=?',(profiles[0]['okved'],)):
                    if r['relation'] in scopes[scope] and priority[r['relation']] > priority.get(family_interests.get(r['family_key'],{}).get('relation'),0):
                        family_interests[r['family_key']] = dict(r)
                family_names = {r['family_key']:r['object'] for r in db.execute('SELECT * FROM object_families')}
                for r in db.execute('SELECT * FROM object_families'):
                    if 'reference_member_topic_ids' in r.keys() and explicit & set(json.loads(r['reference_member_topic_ids'])):
                        explicit_objects.add(r['family_key'])
                cols = {r[1] for r in db.execute('PRAGMA table_info(family_assignments)')}
                for r in db.execute('SELECT * FROM family_assignments'):
                    r = dict(r)
                    if 'status' in cols and r['status'] != 'accepted' and not include_review and mode != 'ranked':
                        continue
                    family_matches.setdefault(r['article_id'],[]).append(r)
                # New catalogs keep date/text eligibility independent of topic acceptance.
                # Article rows already include independent date/text eligibility above.
        observed = {}
        observed_relationships=[]
        context_path = self.assets
        if context_path.is_file():
            with sqlite3.connect(context_path.resolve().as_uri()+'?mode=ro',uri=True) as context_db:
                if context_db.execute("SELECT 1 FROM sqlite_master WHERE name='raw_profiles'").fetchone():
                    raw=context_db.execute('SELECT facts FROM raw_profiles WHERE record_id=?',(profiles[0]['source_record_id'],)).fetchone()
                    observed=json.loads(raw[0]) if raw else {}
                if scope=='interest' and mode=='ranked' and context_db.execute("SELECT 1 FROM sqlite_master WHERE name='relationships'").fetchone():
                    observed_relationships=[json.loads(row[0]) for row in context_db.execute(
                        "SELECT payload FROM relationships WHERE record_id=? ORDER BY CASE WHEN json_extract(payload,'$.kind') IN ('incoming_payment','outgoing_payment') THEN 0 ELSE 1 END,COALESCE(json_extract(payload,'$.ranking_weight'),0) DESC,json_extract(payload,'$.relationship_id') LIMIT 8",
                        (profiles[0]['source_record_id'],))]

        business_features, industry_matches, relationship_matches = {}, {}, {}
        sidecar = self.catalog.parent / 'ranking.sqlite'
        if mode == 'ranked' and sidecar.exists():
            with sqlite3.connect(sidecar.resolve().as_uri() + '?mode=ro', uri=True) as ranking:
                ranking.row_factory = sqlite3.Row
                ranking_tables = {r[0] for r in ranking.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if {'article_industries','company_industries'} <= ranking_tables:
                    for row in ranking.execute('''SELECT a.article_id,a.sector_id,a.score,a.evidence,
                        c.reason,c.relation FROM article_industries a JOIN company_industries c USING(sector_id)
                        WHERE c.okved=?''',(profiles[0]['okved'],)):
                        industry_matches.setdefault(row['article_id'],[]).append(dict(row))
                    for relationship in observed_relationships:
                        code=relationship.get('related_okved')
                        if not code:continue
                        for row in ranking.execute("SELECT a.article_id,a.sector_id,a.score FROM article_industries a JOIN company_industries c USING(sector_id) WHERE c.okved=? AND c.relation='declared_activity'",(code,)):
                            relationship_matches.setdefault(row['article_id'],[]).append({
                                'relationship_id':relationship['relationship_id'],
                                'related_company_id':relationship.get('related_company_id'),
                                'kind':relationship['kind'],'sector_id':row['sector_id'],
                                'evidence':relationship.get('evidence'),
                                'caveat':relationship.get('role_caveat'),
                                'score':float(row['score']), 'conditional':True})


                business_features = {r['article_id']:dict(r) for r in ranking.execute('SELECT * FROM article_features')}
                if scope == 'interest':
                    inferred = ranking.execute('SELECT operating_families FROM company_profiles WHERE source_record_id=?',
                                               (profiles[0]['source_record_id'],)).fetchone()
                    if inferred:
                        for family in json.loads(inferred[0]):
                            if family not in family_interests:
                                family_interests[family] = dict(relation='operating_exposure',
                                    reason='Общая операционная потребность бизнеса; гипотеза интереса, не специализация компании')

                for row in ranking.execute('SELECT * FROM article_objects'):
                    r = dict(row)
                    if r['family_key'] not in family_names or r['article_id'] not in articles:
                        continue
                    existing = family_matches.setdefault(r['article_id'],[])
                    if not any(m['family_key']==r['family_key'] and (m.get('status')=='accepted' or float(m.get('embedding_cosine') or 0)>=float(r['score'])) for m in existing):
                        existing[:] = [m for m in existing if m['family_key']!=r['family_key']]
                        existing.append(dict(article_id=r['article_id'],family_key=r['family_key'],
                            embedding_cosine=r['score'],reranker_logit=0.,evidence=r['evidence'],
                            status='review',origin=r['origin'],sidecar_supported=True))
        excluded = {aid for aid,event_kind,ts in history if event_kind in ('hide','dislike','like','save') or (event_kind in ('view','open') and ts>now-7*86400)}
        for (response,) in impressions:
            excluded.update(item['article_id'] for item in json.loads(response)['items'])
        recent_articles = [articles[aid] for aid in excluded if aid in articles]
        for a in recent_articles:
            a['_tokens'] = tokens(a['title'])
            a['_topics'] = assignments.get(a['article_id'],set())
        preferences = Counter()
        seen_signals = set()
        for aid,event_kind,ts in sorted(history,key=lambda r:-r[2]):
            if (aid,event_kind) in seen_signals:
                continue
            seen_signals.add((aid,event_kind))
            for topic in assignments.get(aid,()):
                preferences[topic] += SIGNALS[event_kind] * math.exp(-max(0,now-ts)/(30*86400))
            for match in family_matches.get(aid,()):
                preferences[match['family_key']] += SIGNALS[event_kind] * math.exp(-max(0,now-ts)/(30*86400))
            for industry in industry_matches.get(aid,()):
                preferences['industry::'+industry['sector_id']] += SIGNALS[event_kind] * math.exp(-max(0,now-ts)/(30*86400))
        popular = dict(popularity)
        max_pop = max(popular.values(),default=1)
        excluded_hashes = {a.get('text_hash') or a.get('content_hash') for aid,a in articles.items() if aid in excluded} - {None,''}
        from recommendations.stories import membership
        story_members=membership(self)
        excluded_stories={story_members[aid]['story_id'] for aid in excluded if aid in story_members and story_members[aid]['dedup_safe']}
        candidates = []
        relation_weights = {'declared_activity':1.,'activity_scope_candidate':.65,'operating_exposure':.35}
        for aid,a in articles.items():
            story=story_members.get(aid)
            if story and story['dedup_safe'] and story['story_id'] in excluded_stories:continue
            if story:a.update(story_id=story['story_id'],story_publications=story['story_publications'])
            if aid in excluded or (a.get('text_hash') or a.get('content_hash')) in excluded_hashes:
                continue
            if self.vectors and any(aid in self.vectors and old['article_id'] in self.vectors and self.similarity(a,old)>=.96 for old in recent_articles):
                continue
            if kind != 'all' and a.get('kind','news') != kind:
                continue
            try:
                date = datetime.fromisoformat(a['published_at'].replace('Z','+00:00'))
                stamp = date.replace(tzinfo=date.tzinfo or timezone.utc).timestamp()
            except (ValueError,AttributeError):
                continue
            if stamp>now or stamp<now-30*86400:
                continue
            topics = assignments.get(aid,set())
            objects = family_matches.get(aid,[])
            if mode == 'ranked':
                objects = [m for m in objects if m.get('status','accepted') == 'accepted' or m.get('sidecar_supported') or (float(m.get('embedding_cosine') or 0) >= .81 and float(m.get('reranker_logit') or -100) >= -3.0 and bool(m.get('evidence')))]
            matched_objects = [{**m, 'name':family_names[m['family_key']],
                                'relation':family_interests[m['family_key']]['relation'],
                                'company_reason':family_interests[m['family_key']]['reason'],
                                'tag_level':'object_group', 'specific_event_verified':False}
                               for m in objects if m['family_key'] in family_interests]
            a['_topics'],a['_tokens'] = topics | {m['family_key'] for m in objects},tokens(a['title'])
            company_score = max((relation_weights.get(interests.get(t),0) for t in topics),default=0)
            company_score = max(company_score,max((relation_weights[m['relation']] for m in matched_objects),default=0))
            industries = industry_matches.get(aid,[])
            if industries:
                company_score = max(company_score,.75*max(min(1.,float(m['score'])) for m in industries))
            if mode == 'strict' and family_names and not company_score and not (topics & explicit):
                continue
            names = [topic_names.get(t,'') for t in topics] + [m['name'] for m in matched_objects]
            general = float(any(re.search(r'налог|ставк|инфляц|макро|закон|кадр|кибер',name,re.I) for name in names))
            feature = business_features.get(aid,{})
            if feature and feature.get('business_score',0) < .5:
                continue
            headline = (a.get('title') or '') + ' ' + ' '.join(names)
            if mode == 'ranked':
                general = max(general, float(feature.get('general_business',0)), float(bool(re.search(r'налог|инфляц|ключев.{0,8}ставк|экономик|бизнес|предпринимат|кибер|трудов|закон.{0,12}(бизнес|компани)|рубл|экспорт|инвестиц', headline, re.I))))
            exposure_reasons=[]
            if observed.get('CL_PRODUCT_LOA_MARK') in ('1','1.0') and re.search(r'\b(?:ставк|кредит|рефинанс|долгов)',headline,re.I):
                company_score=min(1.,company_score+.12)
                exposure_reasons.append('В исходном профиле есть кредитный флаг; условия финансирования требуют проверки')
            if observed.get('FTS_FLAG') in ('1','1.0') and re.search(r'экспорт|импорт|валют|тамож|санкц|расчёт|расчет',headline,re.I):
                company_score=min(1.,company_score+.12)
                exposure_reasons.append('В исходном профиле есть признак ФТС; валюты и действующие контракты не подтверждены')
            network=relationship_matches.get(aid,[])
            if network:
                # Observed payments/group membership support a small retrieval hint,
                # never a claim about ownership, guarantees or risk transmission.
                network_boost=max((.06 if m['kind'] in ('incoming_payment','outgoing_payment') else .025)*min(1.,m['score']) for m in network)
                company_score=min(1.,company_score+network_boost)
            role_terms = ROLE_TERMS[role].split()
            role_score = min(1., sum(bool(re.search(r'\b'+re.escape(term)+r'\b',headline.lower())) if len(term)<=2 else bool(re.search(r'\b'+re.escape(term),headline.lower())) for term in role_terms) / 2.)
            preference_keys = a['_topics'] | {'industry::'+m['sector_id'] for m in industries}
            personal = max(-1.,min(1.,sum(preferences[t] for t in preference_keys)/max(1,len(preference_keys))))
            personal = max(-1.,min(1.,personal + float(bool(preference_keys & (explicit | explicit_objects))) + .5*role_score))
            if mode == 'ranked' and not company_score and not general and personal <= 0 and popular.get(aid,0) < 2:
                continue
            components = dict(company=company_score,general=general,popular=math.log1p(popular.get(aid,0))/math.log1p(max_pop),personal=personal)
            freshness = math.exp(-max(0,now-stamp)/(7*86400))
            a['components'] = components
            a['score'] = sum(WEIGHTS[k]*v for k,v in components.items())*(.7+.3*freshness)
            a['matched_topics'] = [{'topic_id':t,'name':topic_names[t],'relation':interests[t]} for t in sorted(topics & interests.keys())]
            a['matched_objects'] = matched_objects
            a['matched_industries'] = industries
            a['review_required'] = any(m.get('status')=='review' for m in matched_objects) and not any(m.get('status','accepted')=='accepted' for m in matched_objects)
            if a['review_required']: a['score'] *= .85 if mode == 'ranked' else .5
            a['recommendation_reasons'] = ([{'kind':'company','text':'Связь по ОКВЭД и тематике новости'}] if company_score else []) + ([{'kind':'general','text':'Общая деловая повестка'}] if general else []) + ([{'kind':'personal','text':'Роль и интересы пользователя'}] if personal > 0 else []) + ([{'kind':'popular','text':'Интерес других читателей'}] if popular.get(aid,0) else [])
            a['recommendation_reasons'] += [{'kind':'observed_profile','text':reason} for reason in exposure_reasons]
            if network:
                a['recommendation_reasons'].append({'kind':'observed_relationship',
                    'text':'Отрасль наблюдаемого контрагента или участника группы; влияние на компанию требует проверки',
                    'relationship_ids':list(dict.fromkeys(m['relationship_id'] for m in network))[:3]})
                a['relationship_context']=network[:3]
            if industries:
                a['recommendation_reasons'].append({'kind':'industry_context','text':'Отраслевая связь: ' + industries[0]['reason']})
            a['match_level'] = 'thematic_candidate' if a['review_required'] else ('verified_object' if matched_objects else ('industry_context' if industries else 'business_context'))
            a['recommended_lane'] = max(components,key=lambda key: WEIGHTS[key]*max(0.,components[key]))
            if not a.pop('_feed_prepared',False):
                clean_text = re.sub(r'<[^>]+>', ' ', a.get('text') or '')
                clean_text = re.sub(r'\s+', ' ', clean_text).strip()
                a['reading_minutes'] = max(1, math.ceil(len(clean_text.split())/200))
                a['excerpt'] = ' '.join(re.split(r'(?<=[.!?])\s+',clean_text)[:2])[:420]
            # Full article bodies are available through /article; feed pages stay small.
            a.pop('text',None)
            a.pop('images',None)
            candidates.append(a)
        selected, hashes, selected_stories = [],set(),set()
        while candidates and len(selected)<limit:
            for a in candidates:
                redundancy = max((max(0.,(self.similarity(a,b)-.70)/.30) if self.vectors else self.similarity(a,b) for b in selected),default=0)
                source_penalty = .03*sum(b['source']==a['source'] for b in selected)
                a['mmr_score'] = .75*a['score']-.25*redundancy-source_penalty
            best = max(candidates,key=lambda a:(a['mmr_score'],a['published_at'],a['article_id']))
            candidates.remove(best)
            story=story_members.get(best['article_id'])
            if story and story['dedup_safe'] and story['story_id'] in selected_stories:continue
            content_key = best.get('text_hash') or best.get('content_hash') or best['article_id']
            if content_key in hashes or any((self.similarity(best,b) if self.vectors else jaccard(best['_tokens'],b['_tokens']))>=.94 for b in selected):
                continue
            hashes.add(content_key)
            if story and story['dedup_safe']:selected_stories.add(story['story_id'])
            selected.append(best)
        items = [{k:v for k,v in a.items() if not k.startswith('_')} for a in selected]
        result = dict(request_id=request_id or str(uuid.uuid4()), company_id=company,user_id=user,items=items,
            weights=WEIGHTS,weights_mode='score_blend_not_slot_quotas',similarity='embedding_cosine' if self.vectors else 'topic_title_jaccard',
            eligible_catalog=len(articles),shortfall=max(0,limit-len(items)),company_topic_count=len(interests),
            warnings=['Insufficient eligible news; quality gates were preserved.'] if len(items)<limit else [])
        result.update(scope=scope,include_review=include_review,kind=kind,mode=mode,role=role)
        with self.connect() as db:
            result['request_context']=request_context
            db.execute('INSERT OR IGNORE INTO deliveries VALUES(?,?,?,?,?)',(result['request_id'],company,user,now,json.dumps(result,ensure_ascii=False)))
            actual=db.execute('SELECT company,user,response FROM deliveries WHERE request_id=?',(result['request_id'],)).fetchone()
            if actual[:2]!=(company,user) or json.loads(actual[2]).get('request_context')!=request_context:
                raise ValueError('request_id reused with different parameters')
            result=json.loads(actual[2])
        return result
