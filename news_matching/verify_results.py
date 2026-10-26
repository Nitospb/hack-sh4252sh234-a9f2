"""Full integrity checks; these do not measure semantic precision."""
import csv
import json
import sqlite3
from collections import Counter
from datetime import datetime
import numpy as np
from model_backend import ROOT,sha256
from prepare_embeddings import load


def main():
    output=ROOT/'output';source={a['id']:a for a in load(ROOT/'input/data/articles-all.jsonl')}
    ready={a['id'] for a in load(ROOT/'input/data/ml-input.jsonl')}
    topics={t['topic_id']:t for t in load(ROOT.parent/'taxonomy/output/business_topics.jsonl')}
    assert len(source)==3446 and len(ready)==2155 and len(topics)==10000
    manifest=json.loads((ROOT/'input/metadata/manifest.json').read_text());window=manifest['publication_window']
    lower=datetime.fromisoformat(window['since_inclusive']);upper=datetime.fromisoformat(window['until_exclusive'])
    for aid in ready:
        a=source[aid];assert a['text_scope']!='accessible_excerpt'
        assert lower<=datetime.fromisoformat(a['published_at'])<upper
    assert len({source[i]['text_hash'] for i in ready})==len(ready)
    embedding=json.loads((output/'embedding_metadata.json').read_text())
    arrays=[('topic_embeddings.npy',10000),('article_chunk_embeddings.npy',embedding['chunks'])]
    for name,count in arrays:
        data=np.load(output/name,mmap_mode='r');assert data.shape==(count,384)
        assert np.isfinite(data).all() and np.allclose(np.linalg.norm(data,axis=1),1,atol=2e-4)
    index=json.loads((output/'topic_embedding_index.json').read_text());assert index==list(topics)
    report=json.loads((output/'report.json').read_text());policy=report['policy'];seen=set();stats=Counter();links=set()
    db=sqlite3.connect('file:'+str((output/'news_topics.sqlite').resolve())+'?mode=ro',uri=True)
    for r in load(output/'news_topic_assignments.jsonl'):
        aid=r['article_id'];a=source[aid];assert aid not in seen;seen.add(aid)
        assert r['content_hash']==a['content_hash'] and r['title']==a['title']
        assert r['eligible_delivery']==(aid in ready and bool(r['accepted_topics']))
        assert len({t['topic_id'] for t in r['accepted_topics']})==len(r['accepted_topics'])<=policy['maximum_automatic_topics']
        for t in r['accepted_topics']:
            tid=t['topic_id'];assert tid in topics and tid.startswith('bt_')
            assert t['topic_name']==topics[tid]['name']
            assert t['object']==topics[tid]['object'] and t['signal']==topics[tid]['signal']
            assert t['evidence']==a['title'] or t['evidence'] in a['text']
            assert t['object_anchor'] and t['signal_anchor']
            assert t['embedding_cosine']>=policy['automatic_cosine_min'] and t['reranker_logit']>=policy['automatic_reranker_min']
            assert t['modality']!='conditional_or_forecast'
            assert a.get('text_scope')!='accessible_excerpt'
            assert len(a['text'])<=policy['maximum_body_chars_for_auto']
            assert str(a.get('language')).lower().split('-')[0].split('_')[0] in policy['automatic_languages']
            if not t['title_object_anchor']:
                assert t['embedding_cosine']>=policy['body_only_cosine_min'] and t['reranker_logit']>=policy['body_only_reranker_min']
            assert db.execute('SELECT count(*) FROM assignments WHERE article_id=? AND topic_id=?',(aid,tid)).fetchone()[0]==1
            links.add((aid,tid));stats['accepted_links']+=1
        assert db.execute('SELECT eligible_delivery FROM articles WHERE article_id=?',(aid,)).fetchone()[0]==int(r['eligible_delivery'])
        stats['eligible_articles']+=r['eligible_delivery'];stats[r['status']]+=1
    assert seen==set(source)
    with (output/'accepted_article_topics.csv').open(encoding='utf-8-sig',newline='') as f:
        csv_links={(r['article_id'],r['topic_id']) for r in csv.DictReader(f)}
    assert links==csv_links
    assert db.execute('SELECT count(*) FROM assignments').fetchone()[0]==len(links)
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert db.execute('SELECT count(*) FROM companies').fetchone()[0]==85525
    assert db.execute('SELECT count(DISTINCT company_id) FROM companies').fetchone()[0]==85514
    assert not db.execute('SELECT 1 FROM assignments a LEFT JOIN topics t USING(topic_id) WHERE t.topic_id IS NULL LIMIT 1').fetchone()
    db.close()
    result=dict(status='passed',source_articles=len(source),source_ml_eligible=len(ready),assigned_topic_ids_from_original_catalog=True,
        stats=dict(stats),company_records=85525,unique_companies=85514,embedding_shapes_and_unit_norms_valid=True,
        annotation_csv_sqlite_consistency=True,source_evidence_exactly_present=True,
        semantics='Integrity and gate checks, not a production precision estimate.')
    (output/'verify_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
