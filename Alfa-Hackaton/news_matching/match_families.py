"""Conservative topical object tags, explicitly distinct from verified event-specific bt_ labels."""
import json
import re
import csv
import sqlite3
from collections import Counter,defaultdict
import numpy as np
from model_backend import ROOT,OnnxTextModel,sha256
from prepare_embeddings import load
from evidence import sentences,object_aliases,object_positions,norm

POLICY={'candidate_cosine_min':.78,'auto_cosine_min':.83,'auto_reranker_min':0.,'body_cosine_min':.86,'body_reranker_min':1.5,
        'raw_top_k':20,'max_candidates':8,'max_auto_labels':4,'auto_languages':['ru'],'max_body_chars':30000}


def object_evidence(family,records):
    aliases=object_aliases(family)
    for i,r in enumerate(records):
        if family['sector_id']=='crosscut_28' and not re.search(r'(?<!\w)(?:ии|ai|llm)(?!\w)|нейросет|искусственн.{0,20}интеллект|машинн.{0,20}обуч|chatgpt|компьютерн.{0,10}зрен|large language',norm(r['text'])):continue
        if norm(family['object'])=='сталь' and not any(s.startswith(('металл','сталевар','прокат','тонн','стальн')) for s in r['stems']):continue
        if object_positions(r,aliases):return {'evidence':r['text'],'evidence_location':r['where'],'sentence_index':i,'title_object_anchor':i==0}
    return None


def main():
    out=ROOT/'output';families=json.loads((out/'object_families.json').read_text());articles=load(ROOT/'input/data/articles-all.jsonl');by_id={a['id']:a for a in articles}
    chunks=load(out/'article_chunks.jsonl');indices=defaultdict(list)
    for i,c in enumerate(chunks):indices[c['article_id']].append(i)
    vectors=np.load(out/'object_family_embeddings.npy');news=np.load(out/'article_chunk_embeddings.npy')
    found=[];diagnostics={}
    for offset,a in enumerate(articles):
        sims=(news[indices[a['id']]]@vectors.T).max(0);k=POLICY['raw_top_k'];top=np.argpartition(sims,-k)[-k:];top=top[np.argsort(-sims[top])]
        records=sentences(a);candidates=[]
        for i in top:
            if sims[i]<POLICY['candidate_cosine_min']:continue
            f=families[int(i)];e=object_evidence(f,records)
            if not e:continue
            candidates.append({'article_id':a['id'],'title':a['title'],'family_key':f['family_key'],'object':f['object'],'sector_id':f['sector_id'],'sector_name':f['sector_name'],
                'embedding_cosine':round(float(sims[i]),6),'reference_member_topic_ids':f['member_topic_ids'],**e})
        found.extend(candidates[:POLICY['max_candidates']]);diagnostics[a['id']]=len(candidates)
        if (offset+1)%500==0:print('Object-group candidates',offset+1,len(found),flush=True)
    import hashlib
    def key(c):return hashlib.sha256((c['family_key']+'|'+c['title']+'|'+c['evidence']).encode()).hexdigest()
    reranker=OnnxTextModel('reranker',threads=4);model_hash=sha256(reranker.path);cache_path=out/'family_reranker_cache.json'
    cache=json.loads(cache_path.read_text()) if cache_path.exists() else {}
    if cache.get('model_sha256')!=model_hash:cache={'model_sha256':model_hash,'scores':{}}
    pending={key(c):c for c in found if key(c) not in cache['scores']};keys=list(pending)
    if pending:
        pairs=[(pending[k]['object'],pending[k]['title']+'\n'+pending[k]['evidence']) for k in keys]
        logits=reranker.rerank(pairs,max_length=384,batch_size=24,progress='Object-group reranker')
        cache['scores'].update({k:round(float(v),6) for k,v in zip(keys,logits)});cache_path.write_text(json.dumps(cache,ensure_ascii=False)+'\n')
    per_article=defaultdict(list)
    for c in found:c['reranker_logit']=cache['scores'][key(c)];per_article[c['article_id']].append(c)
    eligible={a['id'] for a in load(ROOT/'input/data/ml-input.jsonl')};events={a['article_id']:a for a in load(out/'news_topic_assignments.jsonl')}
    db=sqlite3.connect(out/'news_topics.sqlite');db.executescript('DROP TABLE IF EXISTS object_families;DROP TABLE IF EXISTS family_assignments;DROP TABLE IF EXISTS company_family_mapping;CREATE TABLE object_families(family_key TEXT PRIMARY KEY,object TEXT,sector_id TEXT,sector_name TEXT,reference_member_topic_ids TEXT);CREATE TABLE family_assignments(article_id TEXT,family_key TEXT,embedding_cosine REAL,reranker_logit REAL,evidence TEXT,PRIMARY KEY(article_id,family_key));')
    cols={c[1] for c in db.execute('PRAGMA table_info(articles)')}
    if 'object_eligible_delivery' not in cols:db.execute('ALTER TABLE articles ADD COLUMN object_eligible_delivery INTEGER DEFAULT 0')
    db.execute('UPDATE articles SET object_eligible_delivery=0')
    db.executemany('INSERT INTO object_families VALUES(?,?,?,?,?)',[(f['family_key'],f['object'],f['sector_id'],f['sector_name'],json.dumps(f['member_topic_ids'])) for f in families])
    stats=Counter();reasons=Counter();examples=[]
    fields=['article_id','title','family_key','object','sector_name','embedding_cosine','reranker_logit','evidence','eligible_delivery','specific_event_verified','url']
    with (out/'news_annotations.jsonl').open('w') as jf,(out/'accepted_news_objects.csv').open('w',encoding='utf-8-sig',newline='') as cf,(out/'family_candidate_scores.jsonl').open('w') as candidates_file:
        writer=csv.DictWriter(cf,fieldnames=fields);writer.writeheader()
        for a in articles:
            ranked=sorted(per_article[a['id']],key=lambda c:(-c['reranker_logit'],-c['embedding_cosine']));accepted=[];review=[]
            lang=str(a.get('language') or '').lower().split('-')[0].split('_')[0]
            for c in ranked:
                errors=[]
                if c['embedding_cosine']<POLICY['auto_cosine_min']:errors.append('embedding_below_threshold')
                if c['reranker_logit']<POLICY['auto_reranker_min']:errors.append('reranker_below_threshold')
                if not c['title_object_anchor'] and (c['embedding_cosine']<POLICY['body_cosine_min'] or c['reranker_logit']<POLICY['body_reranker_min'] or c['sentence_index']>8):errors.append('secondary_body_mention')
                if lang not in POLICY['auto_languages']:errors.append('language_needs_review')
                if len(a['text'])>POLICY['max_body_chars']:errors.append('long_document')
                if a.get('text_scope')=='accessible_excerpt':errors.append('excerpt')
                c['specific_event_verified']=False;c['tag_level']='existing_object_group'
                candidates_file.write(json.dumps({**c,'review_reasons':errors},ensure_ascii=False)+'\n')
                if not errors and len(accepted)<POLICY['max_auto_labels']:accepted.append(c)
                else:
                    if not errors:errors=['label_cap']
                    review.append({**c,'review_reasons':errors});reasons.update(errors)
            source_ready=a['id'] in eligible;event=events[a['id']];ready=source_ready and bool(accepted or event['accepted_topics'])
            record=dict(article_id=a['id'],content_hash=a['content_hash'],title=a['title'],url=a.get('canonical_url') or a.get('url'),source=a.get('source_name'),published_at=a.get('published_at'),language=a.get('language'),
                accepted_object_groups=accepted,verified_event_topics=event['accepted_topics'],review_object_candidates=review[:4],review_event_candidates=event['review_candidates'],
                eligible_delivery=ready,status='accepted' if accepted or event['accepted_topics'] else ('needs_review' if ranked or event['review_candidates'] else 'abstained'),
                date_quality_status='snapshot_eligible' if source_ready else 'blocked_unknown_date_excerpt_or_exact_duplicate',
                semantics='Object-group tags assert thematic relevance ONLY. Reference member topic IDs are dictionary references, not assertions that their events occurred.')
            jf.write(json.dumps(record,ensure_ascii=False)+'\n')
            db.execute('UPDATE articles SET object_eligible_delivery=? WHERE article_id=?',(int(source_ready and bool(accepted)),a['id']))
            for c in accepted:
                db.execute('INSERT INTO family_assignments VALUES(?,?,?,?,?)',(a['id'],c['family_key'],c['embedding_cosine'],c['reranker_logit'],c['evidence']))
                writer.writerow({**{k:c[k] for k in fields if k in c},'article_id':a['id'],'title':a['title'],'eligible_delivery':source_ready,'url':record['url']})
            stats['articles_processed']+=1;stats['articles_with_objects']+=bool(accepted);stats['object_links']+=len(accepted);stats['articles_with_verified_events']+=bool(event['accepted_topics']);stats['articles_eligible_delivery']+=ready;stats['articles_'+record['status']]+=1
            if accepted and len(examples)<25:examples.append(record)
    db.executescript('''CREATE INDEX family_assignment_key ON family_assignments(family_key);
CREATE TABLE company_family_mapping AS SELECT DISTINCT m.okved,t.sector_id||'::'||t.object AS family_key,m.relation,b.reason FROM company_mapping m JOIN topics t USING(topic_id) JOIN company_bindings b ON b.binding_id=m.binding_id;
CREATE INDEX company_family_key ON company_family_mapping(family_key,okved);''')
    stats['object_tagged_articles_with_company_mapping']=db.execute('SELECT count(DISTINCT a.article_id) FROM family_assignments a JOIN company_family_mapping m USING(family_key)').fetchone()[0]
    stats['eligible_articles_with_company_mapping']=db.execute('SELECT count(DISTINCT a.article_id) FROM family_assignments a JOIN company_family_mapping m USING(family_key) JOIN articles n USING(article_id) WHERE n.object_eligible_delivery=1').fetchone()[0]
    db.commit();db.close()
    report={'policy':POLICY,'stats':dict(stats),'review_reasons':dict(reasons),'object_families':1000,'original_member_topics':10000,'new_business_topics_created':0,'model_hash':model_hash,
        'quality_claim':'Precision-first thematic retrieval with explicit text anchors. No claim of measured production precision.','event_verification_is_separate':True}
    (out/'report_combined.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');(out/'combined_examples.json').write_text(json.dumps(examples,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
