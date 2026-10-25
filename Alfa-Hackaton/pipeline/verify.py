"""Integrity checks on the published catalog; not a semantic accuracy evaluation."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'recommendations'))
from engine import Feed
from catalog import health,companies,company

out=ROOT/'pipeline/output'
db=sqlite3.connect((out/'catalog.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
db.row_factory=sqlite3.Row
assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
assert db.execute('SELECT count(*) FROM assignments').fetchone()[0]==0, 'Object groups must not assert ten event labels'
assert db.execute('SELECT count(*) FROM topics').fetchone()[0]==10000
assert db.execute('SELECT count(*) FROM object_families').fetchone()[0]==1000
assert db.execute('SELECT count(DISTINCT company_id) FROM companies').fetchone()[0]==85514
assert db.execute("SELECT count(*) FROM articles WHERE kind='telegram_post' AND ml_export_allowed!=0").fetchone()[0]==0
assert db.execute('SELECT count(*) FROM family_assignments m LEFT JOIN articles a USING(article_id) LEFT JOIN object_families f USING(family_key) WHERE a.article_id IS NULL OR f.family_key IS NULL').fetchone()[0]==0
accepted=0
for r in db.execute('SELECT m.*,a.title,a.text,a.eligible_delivery FROM family_assignments m JOIN articles a USING(article_id)'):
    assert r['evidence'] in r['title'] or r['evidence'] in r['text'], r['article_id']
    if r['status']=='accepted':
        accepted+=1
        assert r['eligible_delivery']==1
        assert r['embedding_cosine']>=.83 and r['reranker_logit']>=0
        assert json.loads(r['review_reasons'])==[]
vectors=np.load(out/'article_chunk_embeddings.npy',mmap_mode='r')
assert np.isfinite(vectors).all()
assert np.max(np.abs(np.linalg.norm(vectors,axis=1)-1))<.005
chunks=[json.loads(line) for line in (out/'article_chunks.jsonl').open()]
assert vectors.shape==(len(chunks),384)
articles={r['article_id']:r['content_hash'] for r in db.execute('SELECT article_id,content_hash FROM articles')}
assert {c['article_id'] for c in chunks}==set(articles)
assert all(articles[c['article_id']]==c['content_hash'] for c in chunks)
test_state=tempfile.TemporaryDirectory(prefix='alfa-feed-verification-')
feed=Feed(catalog=out/'catalog.sqlite',state=Path(test_state.name)/'feedback.sqlite',embeddings=False)
examples=companies(feed,limit=5)['items']
assert examples
recommendation=feed.recommend(examples[0]['company_id'],'verification-'+health(feed)['catalog_updated_at'],source_record_id=examples[0]['source_record_id'],scope='strict')
for a in recommendation['items']:
    assert a['matched_objects'] and not a['review_required']
    assert all(m['relation']=='declared_activity' and not m['specific_event_verified'] for m in a['matched_objects'])
assert recommendation['items'] or not examples[0]['accepted_count']
report={'sqlite_integrity':'ok','vector_rows':len(chunks),'catalog_articles':len(articles),'accepted_links_checked':accepted,
        'company_examples':examples,'example_company_id':examples[0]['company_id'],'example_feed_items':len(recommendation['items']),
        'checks':'Source quotes, IDs, original dictionary, model thresholds, Telegram exclusion from training, vectors, strict company feed',
        'measured_semantic_precision':None}
(out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
test_state.cleanup()
