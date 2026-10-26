"""Prepare immutable news-only E5 data and pending human annotation tasks."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

import numpy as np
from training.common import APP, START, END, digest, read_jsonl, require, write_json, write_jsonl


def normal(text):
    return ' '.join(re.findall(r'\w+', text.casefold().replace('ё', 'е')))


def shingles(text):
    words = normal(text).split()[:1500]
    return {int.from_bytes(hashlib.blake2b(' '.join(words[i:i+5]).encode(), digest_size=8).digest(), 'little')
            for i in range(max(0, len(words)-4))}


def duplicate_groups(records):
    """Approximate syndication detection, not certified semantic deduplication."""
    parent = list(range(len(records)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(a, b):
        parent[max(find(a), find(b))] = min(find(a), find(b))
    buckets, titles, sets = defaultdict(list), {}, []
    rng = np.random.default_rng(42)
    multipliers = rng.integers(1, 2**32, size=32, dtype=np.uint64) | np.uint64(1)
    offsets = rng.integers(0, 2**32, size=32, dtype=np.uint64)
    for i, row in enumerate(records):
        title = normal(row['title'])
        if len(title) >= 40:
            if title in titles:
                union(i, titles[title])
            titles[title] = i
        values = shingles(row['text'])
        sets.append(values)
        if len(values) < 30:
            continue
        hashes = np.array(list(values), dtype=np.uint64) & np.uint64(0xffffffff)
        signature = (((hashes[:, None]*multipliers+offsets) & np.uint64(0xffffffff)).min(axis=0))
        keys = [(band, tuple(int(v) for v in signature[band*4:(band+1)*4])) for band in range(8)]
        candidates = {j for key in keys for j in buckets[key]}
        for j in candidates:
            if len(values & sets[j])/max(1, len(values | sets[j])) >= .8:
                union(i, j)
        for key in keys:
            buckets[key].append(i)
    groups = defaultdict(list)
    for i, row in enumerate(records):
        groups[find(i)].append(row)
    result = []
    for members in groups.values():
        group_id = hashlib.sha256('\n'.join(sorted(r['id'] for r in members)).encode()).hexdigest()
        # Keep only one representative, chosen before temporal splitting.
        representative = max(members, key=lambda r: (r['published_at'], len(r['text']), r['id']))
        result.append({**representative, 'group_id': group_id,
                       'group_member_ids': sorted(r['id'] for r in members)})
    return sorted(result, key=lambda r: (r['published_at'], r['id']))


def split_records(records):
    require(len(records) >= 10, 'Need at least 10 distinct stories for temporal holdouts')
    ordered = sorted(records, key=lambda r: (r['published_at'], r['id']))
    first = ordered[int(len(ordered)*.8)]['published_at']
    second = ordered[int(len(ordered)*.9)]['published_at']
    splits = {'train': [], 'validation': [], 'test': []}
    for row in ordered:
        split = 'train' if row['published_at'] < first else ('validation' if row['published_at'] < second else 'test')
        splits[split].append({**row, 'split': split})
    require(all(splits.values()), 'Publication timestamps cannot form three nonempty holdouts')
    return splits


def body_without_title(row):
    body = row['text'].strip()
    title = row['title'].strip()
    if body[:len(title)].casefold() == title.casefold():
        body = body[len(title):].lstrip(' \n\r:—–-')
    return body


def validate_news(rows):
    seen, hashes = set(), set()
    start, end = datetime.fromisoformat(START), datetime.fromisoformat(END)
    clean = []
    for row in rows:
        require(row.get('kind') not in ('telegram', 'telegram_post') and row.get('ml_export_allowed') is not False,
                'Telegram/non-ML record in news input')
        require(row.get('text_scope') != 'accessible_excerpt', 'Accessible excerpt in training input')
        when = datetime.fromisoformat(row['published_at'].replace('Z', '+00:00'))
        require(when.tzinfo is not None and start <= when < end, 'Unknown/out-of-window date')
        require(row['id'] not in seen and row['text_hash'] and row['text_hash'] not in hashes, 'Duplicate input ID/text_hash')
        require(row.get('content_hash') and row.get('title', '').strip() and row.get('text', '').strip(), 'Missing news fields')
        seen.add(row['id']); hashes.add(row['text_hash'])
        clean.append({k: row.get(k) for k in ('id', 'text_hash', 'content_hash', 'title', 'text',
                                              'language', 'source_id', 'source_name', 'canonical_url', 'text_scope')} |
                     {'published_at': when.astimezone(timezone.utc).isoformat(), 'kind': 'news', 'ml_export_allowed': True})
    return clean


def validate_labels(labels, news, families):
    checked, seen = [], set()
    for row in labels:
        key = (row['family_key'], row['article_id'])
        require(key not in seen, 'Duplicate human judgment')
        require(key[0] in families and key[1] in news, 'Judgment outside prepared representative corpus')
        require(row.get('review_status') == 'approved' and str(row.get('annotator') or '').strip(), 'Only attributed approved human labels accepted')
        require(type(row.get('judgment')) is int and row['judgment'] in (0, 1, 2), 'Judgment must be 0/1/2; null is not negative')
        reviewed = datetime.fromisoformat(str(row.get('reviewed_at', '')).replace('Z', '+00:00'))
        require(reviewed.tzinfo is not None, 'Review timestamp needs timezone')
        require(str(row.get('reason') or '').strip(), 'Human judgment needs a reason')
        if row['judgment'] == 2:
            evidence = row.get('evidence') or ''
            require(len(evidence.strip()) >= 8 and (evidence in news[key[1]]['title'] or evidence in news[key[1]]['text']),
                    'Direct-object positive needs a verbatim evidence span')
        seen.add(key); checked.append(row)
    return checked


def positive_passage(article, evidence):
    """Train on the judged span, even if it lies beyond the article lead."""
    if evidence in article['title']:
        body = article['text'][:2200]
    else:
        position = article['text'].index(evidence)
        body = article['text'][max(0, position-120):position+len(evidence)+1200]
    # Evidence is first so title/lead truncation cannot hide the judged object.
    return evidence+'\n'+article['title'][:500]+'\n'+body


def prepare(snapshot, output, families_path, catalog=None, labels_path=None):
    require(not output.exists(), 'Output already exists: choose a new version; never rewrite heldouts')
    snapshot, output = snapshot.resolve(), output.resolve()
    source = snapshot/'data/training-news.jsonl'
    families = {f['family_key']: f for f in json.loads(families_path.read_text())}
    require(len(families) == 1000, 'Expected the original 1,000 object families')
    records = validate_news(read_jsonl(source))
    grouped = duplicate_groups(records)
    splits = split_records(grouped)
    news = {r['id']: r for rows in splits.values() for r in rows}
    checked = validate_labels(read_jsonl(labels_path), news, families) if labels_path else []
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name+'.preparing-', dir=output.parent))
    try:
        write_jsonl(temporary/'corpus/news.jsonl', records)
        write_jsonl(temporary/'corpus/stories.jsonl', [r for rows in splits.values() for r in rows])
        write_json(temporary/'taxonomy/object_families.json', list(families.values()))
        weak_counts = {}
        for split, rows in splits.items():
            pairs = []
            for row in rows:
                passage = body_without_title(row)
                if len(passage) < 100 or len(row['title'].strip()) < 10:
                    continue
                pairs.append({'article_id': row['id'], 'group_id': row['group_id'],
                    'query_id': row['id'], 'query': row['title'], 'positive': passage,
                    'published_at': row['published_at'], 'supervision': 'weak_title_body', 'split': split})
            write_jsonl(temporary/f'weak/{split}.jsonl', pairs)
            weak_counts[split] = len(pairs)
        tasks = []
        if catalog and catalog.exists():
            with sqlite3.connect(catalog.resolve().as_uri()+'?mode=ro', uri=True) as db:
                db.row_factory = sqlite3.Row
                by_family = defaultdict(list)
                for match in db.execute('SELECT * FROM family_assignments ORDER BY embedding_cosine DESC'):
                    if match['article_id'] not in news:
                        continue
                    by_family[match['family_key']].append(dict(match))
            for family_key, candidates in sorted(by_family.items()):
                # Coverage queue, not fabricated positives or negatives.
                selected = []
                for split in splits:
                    selected.extend([c for c in candidates if news[c['article_id']]['split']==split][:3])
                for candidate in selected:
                    article = news[candidate['article_id']]
                    tasks.append({'family_key': family_key, 'object': families[family_key]['object'],
                        'sector_name': families[family_key]['sector_name'], 'article_id': article['id'],
                        'split': article['split'], 'title': article['title'], 'url': article['canonical_url'],
                        'suggested_evidence': candidate['evidence'], 'retrieval_score': candidate['embedding_cosine'],
                        'candidate_origin': 'automatic_retrieval_not_gold', 'judgment': None,
                        'review_status': 'pending', 'annotator': None, 'reviewed_at': None,
                        'reason': None, 'evidence': None})
        write_jsonl(temporary/'annotation/tasks.jsonl', tasks)
        write_jsonl(temporary/'annotation/approved-labels.jsonl', checked)
        supervised_counts = {}
        for split in splits:
            current = [r for r in checked if news[r['article_id']]['split']==split]
            grouped_labels = defaultdict(list)
            for row in current:
                grouped_labels[row['family_key']].append(row)
            triples = []
            for family_key, judgments in sorted(grouped_labels.items()):
                family = families[family_key]
                query = family['object']+'. '+family['sector_name']+'. '+', '.join(family.get('object_keywords', []))
                positives = sorted((r for r in judgments if r['judgment']==2), key=lambda r: r['article_id'])
                negatives = sorted((r for r in judgments if r['judgment']==0), key=lambda r: r['article_id'])
                for i, positive in enumerate(positives):
                    if not negatives:
                        continue
                    negative = negatives[i % len(negatives)]
                    a, b = news[positive['article_id']], news[negative['article_id']]
                    triples.append({'query_id': family_key, 'query': query, 'positive': positive_passage(a, positive['evidence']),
                        'positive_evidence': positive['evidence'],
                        'negative': b['title']+'\n'+b['text'], 'article_id': a['id'], 'negative_article_id': b['id'],
                        'group_id': a['group_id'], 'split': split, 'supervision': 'human_approved_direct_object'})
            write_jsonl(temporary/f'supervised/{split}.jsonl', triples)
            write_jsonl(temporary/f'supervised/{split}-qrels.jsonl', current)
            supervised_counts[split] = len(triples)
        files = {p.relative_to(temporary).as_posix(): digest(p) for p in sorted(temporary.rglob('*')) if p.is_file()}
        manifest = {'schema_version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
            'source': str(source), 'source_sha256': digest(source), 'families_sha256': digest(families_path),
            'fixed_window': {'start_inclusive': START, 'end_exclusive': END},
            'input_news': len(records), 'representative_stories': len(grouped),
            'collapsed_copy_records': len(records)-len(grouped),
            'deduplication': 'normalized long title equality OR MinHash-32/LSH-8x4 candidate shingle Jaccard>=0.8; approximate, not semantic certification',
            'split_policy': 'chronological 80/10/10 over one representative per copy group; timestamp ties kept together',
            'split_counts': {s: len(rows) for s, rows in splits.items()},
            'weak_pair_counts': weak_counts, 'supervised_triplet_counts': supervised_counts,
            'approved_human_labels': len(checked), 'annotation_tasks_pending': len(tasks),
            'split_ranges': {s: {'min': rows[0]['published_at'], 'max': rows[-1]['published_at']} for s, rows in splits.items()},
            'telegram_records': 0, 'images_used': False, 'training_started': False,
            'label_policy': '2=direct object relevant; 1=industry context only (never automatic positive/negative); 0=human verified irrelevant. Pending/null not training labels.',
            'files_sha256': files}
        write_json(temporary/'manifest.json', manifest)
        temporary.rename(output)
        return manifest
    except BaseException:
        shutil.rmtree(temporary)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=APP/'imports/alfa-final-dataset-2026-10-25-0900')
    parser.add_argument('--output', type=Path, default=APP/'training/data/news-v1')
    parser.add_argument('--families', type=Path, default=APP/'news_matching/output/object_families.json')
    parser.add_argument('--catalog', type=Path, default=APP/'pipeline/output/catalog.sqlite')
    parser.add_argument('--labels', type=Path)
    args = parser.parse_args()
    result = prepare(args.snapshot, args.output, args.families, args.catalog, args.labels)
    print(json.dumps({k: v for k, v in result.items() if k != 'files_sha256'}, ensure_ascii=False, indent=2))
