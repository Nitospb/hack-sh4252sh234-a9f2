"""Read-only catalog/vector checks; feed checks use disposable feedback state."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'recommendations'))
from engine import Feed


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(output, training=None):
    output = output.resolve()
    with closing(sqlite3.connect((output/'catalog.sqlite').as_uri()+'?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        require(db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'Catalog integrity')
        articles = {r['article_id']: dict(r) for r in db.execute('SELECT * FROM articles')}
        counts = dict(db.execute('SELECT kind,count(*) FROM articles GROUP BY kind'))
        require(not any(a['ml_export_allowed'] for a in articles.values() if a['kind']=='telegram_post'), 'Telegram ML isolation')
        for table, column, target in [('family_assignments','article_id','articles'),
                                       ('family_assignments','family_key','object_families')]:
            require(db.execute(f'SELECT count(*) FROM {table} f LEFT JOIN {target} t USING({column}) WHERE t.{column} IS NULL').fetchone()[0] == 0, 'Orphan assignments')
        profiles = db.execute('SELECT count(*) FROM companies').fetchone()[0]
        families = db.execute('SELECT count(*) FROM object_families').fetchone()[0]
        topics = db.execute('SELECT count(*) FROM topics').fetchone()[0]
        examples = [dict(db.execute('SELECT * FROM companies WHERE okved=? LIMIT 1', (code,)).fetchone())
                    for code in ['62.01','47.11','01.11','41.20','49.41']]
    chunks = [json.loads(line) for line in (output/'article_chunks.jsonl').open(encoding='utf-8')]
    vectors = np.load(output/'article_chunk_embeddings.npy', mmap_mode='r')
    require(vectors.shape==(len(chunks),384), 'Vector shape')
    require(np.isfinite(vectors).all(), 'Non-finite vectors')
    require(float(np.max(np.abs(np.linalg.norm(vectors,axis=1)-1)))<.005, 'Vector normalisation')
    require({c['article_id'] for c in chunks}==set(articles), 'Article/chunk ID mismatch')
    require(all(c['content_hash']==articles[c['article_id']]['content_hash'] for c in chunks), 'Stale chunk version')
    family_metadata = json.loads((output/'object_family_embedding_metadata.json').read_text())
    embedding_metadata = json.loads((output/'embedding_metadata.json').read_text())
    require(family_metadata['model_sha256']==embedding_metadata['fingerprint']['model_sha256'], 'Encoder mismatch')
    require(np.load(output/'object_family_embeddings.npy').shape==(families,384), 'Family vector shape')
    with closing(sqlite3.connect((output/'ranking.sqlite').as_uri()+'?mode=ro', uri=True)) as ranking:
        require(ranking.execute('PRAGMA integrity_check').fetchone()[0]=='ok', 'Ranking integrity')
        report = json.loads(ranking.execute("SELECT value FROM metadata WHERE key='report'").fetchone()[0])
        with (output/'catalog.sqlite').open('rb') as stream:
            require(report['catalog_sha256']==hashlib.file_digest(stream,'sha256').hexdigest(), 'Ranking/catalog mismatch')
    training_count = None
    if training:
        seen, hashes = set(), set()
        start = datetime.fromisoformat('2026-09-24T20:40:35.362238+00:00')
        end = datetime.fromisoformat('2026-10-24T20:40:35.362238+00:00')
        for line in training.open(encoding='utf-8'):
            record = json.loads(line)
            aid = record['id']
            require(aid in articles and articles[aid]['kind']=='news', 'Training record missing or Telegram')
            require(record.get('text_scope')!='accessible_excerpt', 'Excerpt in training')
            require(aid not in seen and record['text_hash'] not in hashes, 'Duplicate training news')
            date = datetime.fromisoformat(record['published_at'].replace('Z','+00:00'))
            require(start<=date<end, 'Training date outside fixed window')
            require(record['content_hash']==articles[aid]['content_hash'], 'Training/catalog version conflict')
            seen.add(aid)
            hashes.add(record['text_hash'])
        training_count = len(seen)
    checks = []
    with tempfile.TemporaryDirectory(prefix='alfa-validate-feedback-') as tmp:
        feed = Feed(catalog=output/'catalog.sqlite', state=Path(tmp)/'feedback.sqlite', embeddings=True)
        for i, company in enumerate(examples):
            kwargs = dict(company=company['company_id'], source_record_id=company['source_record_id'],
                          user='validation-'+str(i), limit=24, scope='interest', mode='ranked', role='director')
            first = feed.recommend(request_id='first-'+str(i), **kwargs)
            require(first==feed.recommend(request_id='first-'+str(i), **kwargs), 'Request replay differs')
            second = feed.recommend(request_id='second-'+str(i), **kwargs)
            require(len(first['items'])==24 and len(second['items'])==24, 'Short company feed')
            require(not {r['article_id'] for r in first['items']} & {r['article_id'] for r in second['items']}, 'Repeated feed stories')
            checks.append({'okved': company['okved'], 'first_page':24, 'second_page':24,
                           'distinct':True, 'idempotent':True})
    return {'checked_at':datetime.now(timezone.utc).isoformat(), 'counts':counts,
            'chunks':len(chunks), 'company_profiles':profiles, 'object_families':families,
            'topics':topics, 'fixed_window_training_news':training_count,
            'checks':'SQLite integrity, hash joins, vectors, encoder compatibility, training separation, feed passed',
            'feed_checks':checks, 'external_llm_calls':0}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'pipeline/output')
    parser.add_argument('--training', type=Path)
    args = parser.parse_args()
    result = validate(args.output, args.training)
    (args.output/'update_validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
