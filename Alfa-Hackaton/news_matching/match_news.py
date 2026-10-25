"""Multi-label precision-first tagging: E5 retrieval → explicit evidence → multilingual rerank → abstain."""
import argparse
import csv
import hashlib
import json
import sqlite3
import time
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
from model_backend import ROOT,OnnxTextModel,sha256
from evidence import sentences,evidence_for_topic,object_aliases,object_positions
from prepare_embeddings import load

VERSION='news-to-business-topics.v1'
DEFAULT_POLICY={'candidate_cosine_min':.77,'automatic_cosine_min':.82,'automatic_reranker_min':2.,
 'body_only_cosine_min':.85,'body_only_reranker_min':3.,'raw_top_k':100,'rerank_limit_per_article':12,
 'maximum_automatic_topics':6,'automatic_languages':['ru'],'maximum_body_chars_for_auto':30000,
 'score_interpretation':'Cosine and reranker logits are NOT calibrated probabilities.'}


def candidates(output,topics,articles,policy):
    vectors=np.load(output/'topic_embeddings.npy');news_vectors=np.load(output/'article_chunk_embeddings.npy')
    chunks=load(output/'article_chunks.jsonl');indices=defaultdict(list)
    for i,c in enumerate(chunks):indices[c['article_id']].append(i)
    all_candidates=[];diagnostics=[]
    for offset,a in enumerate(articles):
        ids=indices[a['id']];cosines=(news_vectors[ids]@vectors.T).max(axis=0)
        k=policy['raw_top_k'];top=np.argpartition(cosines,-k)[-k:];top=top[np.argsort(-cosines[top])]
        records=sentences(a);found=[];raw=[];object_only=[];object_checked={}
        for i in top:
            score=float(cosines[i]);t=topics[int(i)]
            if score<policy['candidate_cosine_min']:continue
            if len(raw)<3:raw.append({'topic_id':t['topic_id'],'topic_name':t['name'],'embedding_cosine':round(score,6)})
            evidence=evidence_for_topic(t,records)
            if not evidence:
                key=(t['sector_id'],t['object'])
                if key not in object_checked:
                    aliases=object_aliases(t);object_checked[key]=any(object_positions(r,aliases) for r in records)
                    if object_checked[key] and len(object_only)<5:object_only.append({'sector_id':t['sector_id'],'object':t['object'],'status':'object_present_event_unverified_or_not_in_catalog'})
                continue
            title_anchor=bool(object_positions(records[0],object_aliases(t)))
            found.append(dict(article_id=a['id'],content_hash=a['content_hash'],title=a['title'],topic_id=t['topic_id'],topic_name=t['name'],
                sector_id=t['sector_id'],object=t['object'],signal=t['signal'],embedding_cosine=round(score,6),title_object_anchor=title_anchor,**evidence))
        found=found[:policy['rerank_limit_per_article']]
        all_candidates.extend(found)
        diagnostics.append({'article_id':a['id'],'top_semantic_candidates':raw,'evidence_candidates':len(found),'object_only_candidates':object_only})
        if (offset+1)%300==0:print('Evidence candidates:',offset+1,'/',len(articles),'pairs',len(all_candidates),flush=True)
    return all_candidates,diagnostics


def candidate_key(c):
    return hashlib.sha256((c['topic_id']+'|'+c['title']+'|'+c['evidence']).encode()).hexdigest()


def rerank(output,found,topics_by_id):
    model=OnnxTextModel('reranker',threads=4);model_hash=sha256(model.path)
    cache_file=output/'reranker_cache.json';cache=json.loads(cache_file.read_text()) if cache_file.exists() else {}
    if cache.get('model_sha256')!=model_hash:cache={'model_sha256':model_hash,'scores':{}}
    pending={candidate_key(c):c for c in found if candidate_key(c) not in cache['scores']}
    keys=list(pending);pairs=[]
    for key in keys:
        c=pending[key];t=topics_by_id[c['topic_id']]
        query=f"{t['object']}: {t['signal']}. {t['sector_name']}."
        pairs.append((query,c['title']+'\n'+c['evidence']))
    if pending:
        print('Rerank uncached pairs:',len(pairs),flush=True)
        scores=model.rerank(pairs,max_length=384,batch_size=24,progress='Multilingual reranker')
        cache['scores'].update({key:round(float(score),6) for key,score in zip(keys,scores)})
        cache_file.write_text(json.dumps(cache,ensure_ascii=False)+'\n')
    for c in found:c['reranker_logit']=cache['scores'][candidate_key(c)]
    return model_hash


def decide(candidate,article,policy):
    reasons=[]
    if candidate['embedding_cosine']<policy['automatic_cosine_min']:reasons.append('embedding_below_auto_threshold')
    if candidate['reranker_logit']<policy['automatic_reranker_min']:reasons.append('reranker_below_auto_threshold')
    if candidate['modality']=='conditional_or_forecast':reasons.append('conditional_or_forecast_needs_review')
    if not candidate['title_object_anchor'] and (candidate['embedding_cosine']<policy['body_only_cosine_min'] or candidate['reranker_logit']<policy['body_only_reranker_min']):reasons.append('body_only_topic_needs_stronger_support')
    if len(article['text'])>policy['maximum_body_chars_for_auto']:reasons.append('long_document_needs_editorial_review')
    language=str(article.get('language') or '').lower().split('-')[0].split('_')[0]
    if language not in policy['automatic_languages']:reasons.append('language_not_in_auto_validated_set')
    if article.get('text_scope')=='accessible_excerpt':reasons.append('accessible_excerpt')
    return not reasons,reasons


def write_outputs(output,topics,articles,found,diagnostics,policy,reranker_hash):
    by_article=defaultdict(list)
    for c in found:by_article[c['article_id']].append(c)
    topic_lookup={t['topic_id']:t for t in topics}
    ready_ids={r['id'] for r in load(ROOT/'input/data/ml-input.jsonl')}
    diag={r['article_id']:r for r in diagnostics}
    db_path=output/'news_topics.sqlite'
    if db_path.exists():db_path.unlink()
    db=sqlite3.connect(db_path,uri=True)
    db.executescript('''CREATE TABLE articles(article_id TEXT PRIMARY KEY,content_hash TEXT,title TEXT,url TEXT,source TEXT,published_at TEXT,language TEXT,eligible_delivery INTEGER,status TEXT,text_hash TEXT);
CREATE TABLE assignments(article_id TEXT,topic_id TEXT,embedding_cosine REAL,reranker_logit REAL,evidence TEXT,modality TEXT,PRIMARY KEY(article_id,topic_id));
CREATE TABLE topics(topic_id TEXT PRIMARY KEY,name TEXT,sector_id TEXT,object TEXT,signal TEXT);
''')
    db.executemany('INSERT INTO topics VALUES(?,?,?,?,?)',[(t['topic_id'],t['name'],t['sector_id'],t['object'],t['signal']) for t in topics])
    stats=Counter();sectors=Counter();review_reasons=Counter();examples=[]
    fields=['article_id','content_hash','title','topic_id','topic_name','sector_id','embedding_cosine','reranker_logit','evidence','modality','eligible_delivery','published_at','url']
    with (output/'news_topic_assignments.jsonl').open('w') as jf,(output/'accepted_article_topics.csv').open('w',encoding='utf-8-sig',newline='') as cf,(output/'candidate_scores.jsonl').open('w') as candidate_file:
        writer=csv.DictWriter(cf,fieldnames=fields);writer.writeheader()
        for a in articles:
            ranked=sorted(by_article[a['id']],key=lambda c:(-c['reranker_logit'],-c['embedding_cosine'],c['topic_id']))
            accepted=[];review=[];per_object=Counter()
            for c in ranked:
                candidate_file.write(json.dumps(c,ensure_ascii=False)+'\n')
                passed,reasons=decide(c,a,policy)
                if passed and len(accepted)<policy['maximum_automatic_topics'] and per_object[(c['sector_id'],c['object'])]<2:
                    accepted.append(c);per_object[(c['sector_id'],c['object'])]+=1
                else:
                    if passed:reasons=['automatic_topic_cap_or_object_diversity_cap']
                    review.append({**c,'review_reasons':reasons});review_reasons.update(reasons)
            eligible=a['id'] in ready_ids
            status='accepted' if accepted else ('needs_review' if review else 'abstained_no_supported_topic')
            record=dict(article_id=a['id'],content_hash=a['content_hash'],text_hash=a['text_hash'],title=a['title'],url=a.get('canonical_url') or a.get('url'),
                source=a.get('source_name'),published_at=a.get('published_at'),language=a.get('language'),status=status,
                eligible_delivery=eligible and bool(accepted),delivery_block_reason=None if eligible else 'not_in_dated_non_excerpt_deduplicated_snapshot_set',
                accepted_topics=accepted,review_candidates=review[:5],semantic_candidates_for_review=diag[a['id']]['top_semantic_candidates'] if not accepted else [],
                object_only_candidates=diag[a['id']].get('object_only_candidates',[]) if not accepted else [],
                version=VERSION,score_semantics='Retrieval similarity and reranker logits, NOT relevance probabilities.',
                interpretation='Text-supported topic; does not establish financial impact on a particular company.')
            jf.write(json.dumps(record,ensure_ascii=False)+'\n')
            db.execute('INSERT INTO articles VALUES(?,?,?,?,?,?,?,?,?,?)',(a['id'],a['content_hash'],a['title'],record['url'],record['source'],a.get('published_at'),a.get('language'),int(record['eligible_delivery']),status,a['text_hash']))
            for c in accepted:
                db.execute('INSERT INTO assignments VALUES(?,?,?,?,?,?)',(a['id'],c['topic_id'],c['embedding_cosine'],c['reranker_logit'],c['evidence'],c['modality']))
                writer.writerow(dict(article_id=a['id'],content_hash=a['content_hash'],title=a['title'],topic_id=c['topic_id'],topic_name=c['topic_name'],sector_id=c['sector_id'],
                    embedding_cosine=c['embedding_cosine'],reranker_logit=c['reranker_logit'],evidence=c['evidence'],modality=c['modality'],eligible_delivery=record['eligible_delivery'],published_at=a.get('published_at'),url=record['url']))
                sectors[c['sector_id']]+=1
            stats['articles_processed']+=1;stats['articles_'+status]+=1;stats['accepted_topic_links']+=len(accepted)
            stats['articles_eligible_delivery']+=record['eligible_delivery'];stats['articles_excluded_by_snapshot_quality']+=not eligible
            if accepted and len(examples)<30:examples.append(record)
    db.executescript('CREATE INDEX assignments_topic ON assignments(topic_id);CREATE INDEX articles_delivery ON articles(eligible_delivery,published_at);')
    # Join the original bt_ company mapping without creating any new company-topic labels.
    company_map=ROOT.parent/'taxonomy/output/okved_topic_mapping/okved_topics.sqlite'
    db.execute('ATTACH DATABASE ? AS company_map',('file:'+str(company_map.resolve())+'?mode=ro',))
    db.executescript('CREATE TABLE companies AS SELECT * FROM company_map.companies;CREATE TABLE company_mapping AS SELECT * FROM company_map.mapping;CREATE TABLE company_bindings AS SELECT * FROM company_map.bindings;CREATE TABLE company_activities AS SELECT * FROM company_map.activities;CREATE INDEX company_code ON companies(okved);CREATE INDEX company_uid ON companies(company_id);CREATE INDEX company_mapping_topic ON company_mapping(topic_id,okved);CREATE INDEX company_binding_id ON company_bindings(binding_id);')
    stats['accepted_topics_with_company_mapping']=db.execute('SELECT count(DISTINCT a.topic_id) FROM assignments a JOIN company_mapping m USING(topic_id)').fetchone()[0]
    stats['accepted_articles_with_any_company_mapping']=db.execute('SELECT count(DISTINCT a.article_id) FROM assignments a JOIN company_mapping m USING(topic_id)').fetchone()[0]
    db.commit();assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok';db.close()
    report=dict(version=VERSION,stats=dict(stats),accepted_links_by_sector=dict(sectors),review_reason_counts=dict(review_reasons),policy=policy,
        embedding_metadata=json.loads((output/'embedding_metadata.json').read_text()),reranker={'model':'cross-encoder/mmarco-mMiniLMv2-L12-H384-v1','onnx_sha256':reranker_hash},
        quality_claim='Precision-first gates. No measured production precision without independent labelled evaluation.',
        existing_heuristic_topics_used_as_labels=False,all_source_article_ids_processed=True,all_assigned_topic_ids_from_original_10000=True,
        automatic_delivery_rule='accepted topic plus membership in snapshot dated/full/exact-deduplicated ML set; firm scope checked at recommendation time.')
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (output/'examples.json').write_text(json.dumps(examples,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'stats':stats,'review_reasons':review_reasons,'sector_counts':sectors},ensure_ascii=False,indent=2),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--policy',type=Path);p.add_argument('--reuse-scores',action='store_true');a=p.parse_args()
    output=ROOT/'output';policy={**DEFAULT_POLICY,**(json.loads(a.policy.read_text()) if a.policy else {})}
    topics=load(ROOT.parent/'taxonomy/output/business_topics.jsonl');articles=load(ROOT/'input/data/articles-all.jsonl')
    if a.reuse_scores:
        found=load(output/'candidate_scores.jsonl');diagnostics=load(output/'retrieval_diagnostics.jsonl');reranker_hash=sha256(ROOT/'models/reranker-int8.onnx')
    else:
        found,diagnostics=candidates(output,topics,articles,policy)
        with (output/'retrieval_diagnostics.jsonl').open('w') as f:
            for d in diagnostics:f.write(json.dumps(d,ensure_ascii=False)+'\n')
        reranker_hash=rerank(output,found,{t['topic_id']:t for t in topics})
    write_outputs(output,topics,articles,found,diagnostics,policy,reranker_hash)


if __name__=='__main__':main()
