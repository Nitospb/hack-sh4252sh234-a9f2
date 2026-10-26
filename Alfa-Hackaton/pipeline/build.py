"""Incremental local semantic catalog for news and a distinct Telegram analytics stream."""
import argparse
import fcntl
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'news_matching'))
import numpy as np
from model_backend import TorchE5Model, OnnxTextModel, sha256
from prepare_embeddings import load
from evidence import sentences, object_positions, object_aliases, norm

OUT = ROOT / 'pipeline/output'
SNAPSHOT = ROOT.parent / 'imports/alfa-final-dataset-2026-10-25-0900'
if not SNAPSHOT.exists():
    SNAPSHOT = ROOT.parent / 'imports/alfa-full-snapshot-2026-10-25-0407'
MODEL_POLICY = {'cosine_min': .83, 'reranker_min': 0., 'body_cosine_min': .86,
                'body_reranker_min': 1.5, 'body_sentence_max': 8}

def atomic_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)

def corpus(snapshot=None, extra_news=()):
    from corpus import merged_corpus
    records, report = merged_corpus(snapshot or SNAPSHOT,
        ROOT / 'parser/runtime/full-snapshot/news.sqlite3',
        ROOT / 'parser/runtime/telegram-live/telegram.sqlite3', extra_news=extra_news)
    atomic_json(OUT / 'corpus_manifest.json', report)
    return records

def anchor(family, records):
    aliases = object_aliases(family)
    for i, r in enumerate(records[:9]):
        text = norm(r['text'])
        if family['sector_id'] == 'crosscut_28' and not __import__('re').search(r'(?<!\w)(ии|ai|llm)(?!\w)|нейросет|искусственн.{0,20}интеллект|машинн.{0,20}обуч|chatgpt|компьютерн.{0,10}зрен', text):
            continue
        if norm(family['object']) == 'сталь' and not any(s.startswith(('металл', 'сталевар', 'прокат', 'тонн', 'стальн')) for s in r['stems']):
            continue
        if norm(family['object']) == 'конвейер' and not __import__('re').search(r'ленточн|роликов|транспортер|конвейерн.{0,15}(лент|оборудован|систем)', text):
            continue
        if object_positions(r, aliases):
            return {'evidence': r['text'], 'location': r['where'], 'sentence_index': i}
    return None

def embeddings(articles, backend, encoder_dir=None, reuse_from=None):
    """Reuse only chunks with unchanged article ID, content hash and encoder weights."""
    old = ROOT / 'news_matching/output'
    reuse = {}
    sources = [old] + ([Path(reuse_from)] if reuse_from else []) + [OUT]
    model = TorchE5Model(encoder_dir, device=backend) if backend in ('mps','cuda') or encoder_dir else OnnxTextModel('embedding')
    encoder_hash = sha256(model.path)
    for directory in sources:
        metadata_path = directory / 'embedding_metadata.json'
        if not metadata_path.exists():
            continue
        metadata = json.loads(metadata_path.read_text())
        if metadata.get('fingerprint', {}).get('model_sha256') != encoder_hash:
            continue
        chunks = load(directory / 'article_chunks.jsonl')
        matrix = np.load(directory / 'article_chunk_embeddings.npy', mmap_mode='r')
        grouped = defaultdict(list)
        for i, c in enumerate(chunks):
            grouped[(c['article_id'], c['content_hash'])].append((c, np.array(matrix[i])))
        reuse.update(grouped)
    chunks, rows, pending, pending_indices = [], [], [], []
    reused = 0
    for a in articles:
        key = (a['id'], a['content_hash'])
        if key in reuse:
            for c, v in reuse[key]:
                chunks.append(c); rows.append(v); reused += 1
        else:
            for i, c in enumerate(model.article_chunks(a['title'][:500], a['text'])):
                pending_indices.append(len(chunks))
                chunks.append({'article_id': a['id'], 'content_hash': a['content_hash'], 'chunk_index': i, **c})
                rows.append(None)
                pending.append('passage: ' + c['text'])
    print('Embedding chunks reused', reused, 'new', len(pending), flush=True)
    if pending:
        encoded = model.embed(pending, max_length=384, batch_size=24, progress='New news and Telegram')
        for index, vector in zip(pending_indices, encoded):
            rows[index] = vector
    matrix = np.asarray(rows, dtype=np.float32)
    assert matrix.shape == (len(chunks), 384) and np.isfinite(matrix).all()
    temp = OUT / 'article_chunk_embeddings.tmp.npy'
    np.save(temp, matrix); temp.replace(OUT / 'article_chunk_embeddings.npy')
    with (OUT / 'article_chunks.jsonl').open('w') as f:
        for c in chunks: f.write(json.dumps(c, ensure_ascii=False) + '\n')
    atomic_json(OUT / 'embedding_metadata.json', {'fingerprint': {'model_sha256': encoder_hash}, 'articles': len(articles), 'chunks': len(chunks), 'reused': reused, 'new': len(pending), 'body_chunk_tokens': 256, 'body_overlap_tokens': 32, 'title_max_chars': 500})
    families = json.loads((old / 'object_families.json').read_text())
    metadata = json.loads((old / 'object_family_embedding_metadata.json').read_text())
    # These family vectors were generated by the same original E5 checkpoint.
    if metadata['model_sha256'] == encoder_hash:
        vectors = np.load(old / 'object_family_embeddings.npy')
    else:
        vectors = model.embed(['query: ' + f['object'] + '. ' + f['sector_name'] + '. ' + ', '.join(f.get('object_keywords', [])) for f in families], max_length=160, progress='Object groups')
    np.save(OUT / 'object_family_embeddings.npy', vectors)
    atomic_json(OUT / 'object_family_embedding_metadata.json', {
        'model_sha256': encoder_hash, 'families': len(families),
        'vectors_sha256': sha256(OUT / 'object_family_embeddings.npy')})
    del model
    return chunks, matrix, families, vectors

def build(args):
    global OUT
    OUT = args.output.resolve()
    OUT.mkdir(exist_ok=True, parents=True)
    start = time.time()
    articles = corpus(args.snapshot, getattr(args,"news_live",()))
    atomic_json(OUT / 'source_counts.json', dict(Counter(a['kind'] for a in articles)))
    chunks, vectors, families, family_vectors = embeddings(articles, args.backend, args.encoder_dir, getattr(args,"reuse_from",None))
    grouped = defaultdict(list)
    for i, c in enumerate(chunks): grouped[c['article_id']].append(i)
    signature = hashlib.sha256(json.dumps({'algorithm':'anchored-v2',
        'encoder':json.loads((OUT/'embedding_metadata.json').read_text())['fingerprint'],
        'families':families},sort_keys=True).encode()).hexdigest()
    candidate_cache = {}
    for directory in ([Path(args.reuse_from)] if getattr(args,'reuse_from',None) else [])+[OUT]:
        path=directory/'candidate_cache.json'
        if path.exists():
            saved=json.loads(path.read_text())
            if saved.get('signature')==signature:candidate_cache.update(saved['articles'])
    candidates = []
    reused_candidates=0
    next_cache={}
    for offset, a in enumerate(articles):
        previous=candidate_cache.get(a['id'])
        if previous and previous['content_hash']==a['content_hash']:
            candidates.extend(previous['candidates']);next_cache[a['id']]=previous
            reused_candidates+=1
            continue
        sims = (vectors[grouped[a['id']]] @ family_vectors.T).max(0)
        indices = np.argpartition(sims, -25)[-25:]
        records = None
        found = []
        for i in sorted(indices, key=lambda i: -sims[i]):
            if sims[i] < .78: continue
            if records is None: records = sentences(a)
            e = anchor(families[int(i)], records)
            if e:
                found.append({'article_id': a['id'], 'family_key': families[int(i)]['family_key'], 'object': families[int(i)]['object'], 'sector_name': families[int(i)]['sector_name'], 'embedding_cosine': round(float(sims[i]), 6), **e})
        candidates.extend(found[:6])
        next_cache[a["id"]]={"content_hash":a["content_hash"],"candidates":found[:6]}
        if (offset+1) % 1000 == 0: print('Retrieved', offset+1, 'articles;', len(candidates), 'anchored pairs', flush=True)
    atomic_json(OUT/'candidate_cache.json',{'signature':signature,'articles':next_cache})
    print('Thematic articles reused',reused_candidates,'new',len(articles)-reused_candidates,flush=True)
    by_id = {a['id']: a for a in articles}
    reranker = OnnxTextModel('reranker', threads=4)
    cache_path = OUT / 'reranker_cache.json'
    cache={}
    for directory in ([Path(args.reuse_from)] if getattr(args,'reuse_from',None) else [])+[OUT]:
        saved=directory/'reranker_cache.json'
        if saved.exists():cache.update(json.loads(saved.read_text()))
    def key(c): return hashlib.sha256((sha256_reranker + '|' + c['family_key'] + '|' + by_id[c['article_id']]['title'] + '|' + c['evidence']).encode()).hexdigest()
    sha256_reranker = sha256(reranker.path)
    pending = {key(c): c for c in candidates if key(c) not in cache}
    keys = list(pending)
    pairs = [(pending[k]['object'], by_id[pending[k]['article_id']]['title'] + '\n' + pending[k]['evidence']) for k in keys]
    if pairs:
        scores = reranker.rerank(pairs, batch_size=24, max_length=384, progress='Unified reranker')
        cache.update({k: round(float(v), 6) for k, v in zip(keys, scores)})
        atomic_json(cache_path, cache)
    del reranker
    temp_db = OUT / 'catalog.building.sqlite'
    if temp_db.exists(): temp_db.unlink()
    db = sqlite3.connect(temp_db)
    db.executescript('''CREATE TABLE articles(article_id TEXT PRIMARY KEY,content_hash TEXT,text_hash TEXT,title TEXT,text TEXT,url TEXT,source TEXT,published_at TEXT,language TEXT,kind TEXT,ml_export_allowed INTEGER,eligible_delivery INTEGER,object_eligible_delivery INTEGER,status TEXT,images TEXT);
    CREATE TABLE article_provenance(article_id TEXT PRIMARY KEY,record TEXT);
    CREATE TABLE assignments(article_id TEXT,topic_id TEXT,embedding_cosine REAL,reranker_logit REAL,evidence TEXT);
    CREATE TABLE object_families(family_key TEXT PRIMARY KEY,object TEXT,sector_id TEXT,sector_name TEXT,reference_member_topic_ids TEXT);
    CREATE TABLE family_assignments(article_id TEXT,family_key TEXT,embedding_cosine REAL,reranker_logit REAL,evidence TEXT,status TEXT,review_reasons TEXT,PRIMARY KEY(article_id,family_key));''')
    source = ROOT / 'taxonomy/output/okved_topic_mapping/okved_topics.sqlite'
    db.execute('ATTACH DATABASE ? AS original', (str(source),))
    for original, target in [('companies','companies'),('topics','topics'),('mapping','company_mapping'),('bindings','company_bindings'),('activities','company_activities')]:
        db.execute(f'CREATE TABLE {target} AS SELECT * FROM original.{original}')
    db.executescript('''CREATE INDEX company_id_lookup ON companies(company_id);CREATE INDEX company_okved_lookup ON companies(okved);
    CREATE INDEX company_mapping_code ON company_mapping(okved);CREATE INDEX article_date ON articles(published_at);
    CREATE INDEX company_topic_lookup ON company_mapping(topic_id);
    CREATE TABLE company_family_mapping AS SELECT DISTINCT m.okved,t.sector_id||'::'||t.object AS family_key,m.relation,b.reason FROM company_mapping m JOIN topics t USING(topic_id) JOIN company_bindings b USING(binding_id);
    CREATE INDEX company_family_lookup ON company_family_mapping(okved,family_key);''')
    db.executemany('INSERT INTO object_families VALUES(?,?,?,?,?)', [(f['family_key'],f['object'],f['sector_id'],f['sector_name'],json.dumps(f['member_topic_ids'])) for f in families])
    selected = defaultdict(list)
    for c in candidates:
        c['reranker_logit'] = cache[key(c)]
        selected[c['article_id']].append(c)
    seen_hashes = set()
    counters = Counter()
    reason_counts = Counter()
    # Prefer latest dated version when identical text occurs at multiple URLs.
    articles.sort(key=lambda a: (a.get('published_at') or '', a['id']), reverse=True)
    with (OUT / 'annotations.jsonl').open('w') as stream:
        for a in articles:
            db.execute('INSERT INTO article_provenance VALUES(?,?)',(a['id'],json.dumps({
                k:a.get(k) for k in ('schema_version','source_id','source_name','canonical_url',
                'fetched_at','first_seen_at','last_seen_at','published_at','publication_date_status',
                'text_scope','quality_flags','raw_html_path','content_hash','text_hash','kind',
                'ml_export_allowed')},ensure_ascii=False)))
            quality = []
            try:
                date = datetime.fromisoformat((a.get('published_at') or '').replace('Z','+00:00'))
                if date.tzinfo is None: quality.append('unknown_timezone')
                elif date > datetime.now(timezone.utc): quality.append('future_date')
                elif date < datetime.now(timezone.utc)-timedelta(days=30): quality.append('outside_recent_30_days')
            except ValueError: quality.append('unknown_date')
            if a.get('text_scope') == 'accessible_excerpt': quality.append('excerpt')
            if not a.get('text') or len(a['text'].strip()) < 50: quality.append('short_or_missing_text')
            if a.get('text_hash') and a['text_hash'] in seen_hashes: quality.append('exact_duplicate')
            if not quality and a.get('text_hash'): seen_hashes.add(a['text_hash'])
            accepted, review = [], []
            for c in sorted(selected[a['id']], key=lambda c: -c['reranker_logit']):
                reasons = []
                if c['embedding_cosine'] < MODEL_POLICY['cosine_min']: reasons.append('embedding_below_threshold')
                if c['reranker_logit'] < MODEL_POLICY['reranker_min']: reasons.append('reranker_below_threshold')
                if c['location'] != 'title' and (c['embedding_cosine'] < MODEL_POLICY['body_cosine_min'] or c['reranker_logit'] < MODEL_POLICY['body_reranker_min']): reasons.append('secondary_body_mention')
                if len(a['text']) > 30000: reasons.append('long_document')
                if str(a.get('language', '')).lower().replace('_','-').split('-')[0] != 'ru': reasons.append('language_review')
                reasons += quality
                if len(accepted) >= 4: reasons.append('label_limit')
                c['status'] = 'review' if reasons else 'accepted'
                c['review_reasons'] = reasons
                (review if reasons else accepted).append(c)
                reason_counts.update(reasons)
                db.execute('INSERT INTO family_assignments VALUES(?,?,?,?,?,?,?)', (a['id'],c['family_key'],c['embedding_cosine'],c['reranker_logit'],c['evidence'],c['status'],json.dumps(reasons)))
            ready = not quality
            status = 'accepted' if accepted else ('review' if review else 'unmatched')
            db.execute('INSERT INTO articles VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (a['id'],a['content_hash'],a.get('text_hash'),a['title'],a['text'],a.get('canonical_url') or a.get('url'),a.get('source_name'),a.get('published_at'),a.get('language'),a['kind'],int(a['ml_export_allowed']),0,int(ready and bool(accepted)),status,json.dumps(a.get('images', []))))
            # Date/text safety is separate from semantic acceptance for the review tab.
            if ready: db.execute('UPDATE articles SET eligible_delivery=1 WHERE article_id=?', (a['id'],))
            stream.write(json.dumps({'article_id':a['id'],'kind':a['kind'],'status':status,'quality_reasons':quality,'accepted_objects':accepted,'review_candidates':review,'event_labels_verified':False},ensure_ascii=False)+'\n')
            counters[a['kind']] += 1
            counters['quality_eligible'] += ready
            counters['accepted_articles'] += bool(accepted)
            counters['accepted_links'] += len(accepted)
            counters['review_links'] += len(review)
    db.executescript('CREATE INDEX family_assignment_lookup ON family_assignments(family_key,status);CREATE INDEX family_article_lookup ON family_assignments(article_id);')
    db.commit(); db.close()
    temp_db.replace(OUT / 'catalog.sqlite')
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'counts': dict(counters), 'review_reasons':dict(reason_counts), 'policy':MODEL_POLICY,'seconds':round(time.time()-start,1),'thematic_articles_reused':reused_candidates,'thematic_articles_new':len(articles)-reused_candidates,'measured_precision':None,'semantics':'Existing object groups only; member bt_ event IDs are references, not assertions that events occurred. Telegram remains internal analytics and is never exported as training news.'}
    atomic_json(OUT / 'report.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--backend', choices=['mps','cpu','cuda'], default='mps')
    parser.add_argument('--encoder-dir', type=Path, help='Local Torch checkpoint; use a separate output for candidates')
    parser.add_argument('--news-live', type=Path, action='append', default=[], help='Additional isolated collector SQLite (repeatable)')
    parser.add_argument('--reuse-from', type=Path, help='Read-only previous embedding/candidate/reranker cache')
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    if args.encoder_dir and args.output.resolve() == OUT.resolve():
        parser.error('Candidate encoder requires a separate --output, e.g. pipeline/output-candidate')
    # A shared lock also covers builds into staging directories.
    lock_path = ROOT / 'pipeline/output/.build.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error('Another catalog build is running')
        build(args)
