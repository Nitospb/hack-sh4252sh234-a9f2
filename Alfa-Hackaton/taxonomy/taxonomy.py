"""Versioned business-topic vocabulary and transparent candidate retrieval; stdlib only."""
import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = 'business-topics.v1'


def normalize(text):
    return re.sub(r'\s+', ' ', str(text).lower().replace('ё', 'е')).strip()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def load_sectors():
    return [s for p in sorted((ROOT / 'seeds').glob('*.json'))
            for s in json.loads(p.read_text(encoding='utf-8'))]


def build():
    sectors = load_sectors()
    assert len(sectors) == 100, len(sectors)
    assert len({s['id'] for s in sectors}) == 100
    topics = []
    for s in sectors:
        assert len(s['objects']) == len(s['signals']) == 10, s['id']
        for obj in s['objects']:
            for sig in s['signals']:
                name = f"{obj['name']}: {sig['name']}"
                # Semantic-key IDs survive reordering of the seed arrays.
                key = s['id'] + '|' + normalize(name)
                topics.append(dict(topic_id='bt_' + hashlib.sha256(key.encode()).hexdigest()[:16],
                    name=name, sector_id=s['id'], sector_name=s['name'],
                    object=obj['name'], signal=sig['name'],
                    object_keywords=obj['keywords'], signal_keywords=sig['keywords'],
                    okved_prefixes=s['okved_prefixes'],
                    company_conditions=s.get('company_conditions', []),
                    taxonomy_version=VERSION, status='candidate_vocabulary'))
    assert len(topics) == len({t['topic_id'] for t in topics}) == 10000
    duplicates = [k for k, n in Counter(normalize(t['name']) for t in topics).items() if n > 1]
    assert not duplicates, duplicates[:20]
    for t in topics:
        assert t['object_keywords'] and t['signal_keywords']
        assert all(normalize(k) for k in t['object_keywords'] + t['signal_keywords'])
    out = ROOT / 'output'
    with (out / 'business_topics.jsonl').open('w', encoding='utf-8') as f:
        for t in topics:
            f.write(json.dumps(t, ensure_ascii=False) + '\n')
    with (out / 'business_topics.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(topics[0]))
        writer.writeheader()
        for t in topics:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v for k, v in t.items()})
    write_json(out / 'validation.json', dict(version=VERSION, sectors=len(sectors), topics=len(topics),
        unique_names=10000, unique_ids=10000, duplicate_names=duplicates,
        by_seed={p.stem: len(json.loads(p.read_text())) * 100 for p in sorted((ROOT/'seeds').glob('*.json'))},
        quality_status='structural_checks_passed_semantic_expert_review_pending'))
    return topics


class Matcher:
    def __init__(self, topics):
        self.topics = topics
        self.sectors = {t['sector_id']: t for t in topics}
        self.profile_cache = {}
        self.flag_fields = sorted({f for t in topics for f in t.get('company_conditions', [])})
        phrases = {normalize(k) for t in topics for k in t['object_keywords'] + t['signal_keywords']}
        # Full phrase boundaries avoid 'газ' matching 'магазин'. No stemming/translation.
        self.patterns = {p: re.compile(r'(?<!\w)' + re.escape(p) + r'(?!\w)') for p in phrases}

    def classify(self, article, limit=20):
        text = normalize(' '.join(str(article.get(k) or '') for k in ('title', 'description', 'text')))
        hits = {p for p, pattern in self.patterns.items() if pattern.search(text)}
        results = []
        for t in self.topics:
            objects = sorted({k for k in t['object_keywords'] if normalize(k) in hits})
            signals = sorted({k for k in t['signal_keywords'] if normalize(k) in hits})
            if objects and signals:
                # Require local co-occurrence to reduce accidental long-article matches.
                local = False
                for obj in objects:
                    for m in self.patterns[normalize(obj)].finditer(text):
                        window = text[max(0, m.start()-240):m.end()+240]
                        if any(self.patterns[normalize(sig)].search(window) for sig in signals):
                            local = True
                            break
                    if local:
                        break
                if local:
                    results.append(dict(topic_id=t['topic_id'], name=t['name'], sector_id=t['sector_id'],
                        retrieval_score=len(objects)+len(signals),
                        evidence={'object_phrases': objects, 'signal_phrases': signals},
                        status='lexical_candidate_requires_context_check'))
        results.sort(key=lambda r: (-r['retrieval_score'], r['topic_id']))
        return {'article_id': article.get('id'), 'taxonomy_version': VERSION,
                'total_candidates': len(results), 'truncated': len(results) > limit,
                'topics': results[:limit], 'abstained': not results}

    def profile(self, company):
        code = str(company.get('MAINOKVED_CODE') or '').strip()
        cache_key = (code, *(str(company.get(f, '')).strip() for f in self.flag_fields))
        if cache_key in self.profile_cache:
            evidence = self.profile_cache[cache_key]
            return dict(company_id=company.get('SYNTHETIC_U'), taxonomy_version=VERSION,
                        candidate_sectors=evidence, abstained=not evidence)
        evidence = []
        for sid, s in self.sectors.items():
            prefixes = [p for p in s['okved_prefixes'] if code.replace('.', '').startswith(p.replace('.', ''))]
            flags = [f for f in s.get('company_conditions', [])
                     if str(company.get(f, '')).strip() in ('1', '1.0', 'True', 'true')]
            if prefixes or flags:
                evidence.append({'sector_id': sid, 'sector_name': s['sector_name'],
                    'matched_okved_prefixes': prefixes, 'matched_product_flags': flags,
                    'status': 'candidate_exposure_not_confirmed_product_activity'})
        self.profile_cache[cache_key] = evidence
        return dict(company_id=company.get('SYNTHETIC_U'), taxonomy_version=VERSION,
                    candidate_sectors=evidence, abstained=not evidence)


def evaluate(topics, companies, articles):
    matcher = Matcher(topics)
    counts, sector_counts, examples = Counter(), Counter(), []
    with companies.open(encoding='utf-8-sig', newline='') as f, (ROOT/'output/company_sector_candidates.jsonl').open('w', encoding='utf-8') as profiles:
        for company in csv.DictReader(f, delimiter=';'):
            profile = matcher.profile(company)
            profiles.write(json.dumps(profile, ensure_ascii=False)+'\n')
            counts['companies'] += 1
            counts['companies_with_candidates'] += bool(profile['candidate_sectors'])
            sector_counts.update(s['sector_id'] for s in profile['candidate_sectors'])
            if len(examples) < 5 and profile['candidate_sectors']:
                examples.append(profile)
    out = ROOT / 'output'
    with articles.open(encoding='utf-8') as src, (out/'article_topic_candidates.jsonl').open('w', encoding='utf-8') as dst:
        for line in src:
            if not line.strip():
                continue
            article = json.loads(line)
            result = matcher.classify(article)
            counts['articles'] += 1
            counts['articles_with_candidates'] += not result['abstained']
            counts['articles_truncated'] += result['truncated']
            dst.write(json.dumps(result, ensure_ascii=False)+'\n')
    write_json(out/'coverage.json', dict(counts=counts, company_sector_counts=sector_counts,
        company_examples=examples, note='Coverage is retrieval coverage, not precision or confirmed relevance.'))
    print(json.dumps(counts, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['build', 'evaluate', 'classify', 'profile'])
    p.add_argument('--companies', type=Path)
    p.add_argument('--articles', type=Path)
    p.add_argument('--input', type=Path)
    args = p.parse_args()
    if args.command == 'build':
        print(f'Built {len(build())} topics')
        return
    topics = [json.loads(line) for line in (ROOT/'output/business_topics.jsonl').read_text().splitlines()]
    if args.command == 'evaluate':
        if not args.companies or not args.articles:
            p.error('--companies and --articles required')
        evaluate(topics, args.companies, args.articles)
    else:
        if not args.input:
            p.error('--input JSON file required')
        data = json.loads(args.input.read_text())
        matcher = Matcher(topics)
        result = matcher.classify(data) if args.command == 'classify' else matcher.profile(data)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
