"""User-supplied interest catalog, explainable matching and a separate archive job.

CSV is data, never configuration or executable instructions. The source article
schema and hashes stay unchanged; matches are exported as an additional envelope.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import closing
import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from urllib.parse import unquote

from .history import atomic_json
from .models import utcnow

FIELDS = ('ID группы', 'Отрасль', 'Объект', 'Компаний всего',
          'Прямая деятельность по ОКВЭД', 'Возможная специализация',
          'Косвенный операционный интерес', 'Примеры ID компаний', 'Входящие ID тем')
STOP = set('в во на по и с со для от из к о об при за до the of for and in to a an'.split())
ENDINGS = tuple(sorted(('иями', 'ями', 'ами', 'ого', 'его', 'ому', 'ему', 'ыми', 'ими',
                        'ая', 'яя', 'ое', 'ее', 'ые', 'ие', 'ый', 'ий', 'ой', 'ых', 'их',
                        'ую', 'юю', 'ов', 'ев', 'ом', 'ем', 'ам', 'ям', 'ах', 'ях', 'ей',
                        'а', 'я', 'ы', 'и', 'у', 'ю', 'е', 'о', 'ь'), key=len, reverse=True))
METHOD = 'lexical_ru_inflections_aliases_v1'


def tokens(text):
    return re.findall(r'[a-zа-я0-9]+', text.casefold().replace('ё', 'е'))


def stem(word):
    # Conservative inflection normalization, not semantic understanding or a
    # complete morphological analyzer. Keep short tokens/acronyms intact.
    if re.fullmatch('[а-я]+', word):
        for suffix in ENDINGS:
            if word.endswith(suffix) and len(word) - len(suffix) >= 4:
                return word[:-len(suffix)]
    return word


def terms(text):
    return tuple(stem(word) for word in tokens(text) if word not in STOP)


@dataclass(frozen=True)
class Interest:
    group_id: str
    industry: str
    object: str
    companies: int
    direct: int
    possible: int
    indirect: int
    example_company_ids: tuple[str, ...]
    topic_ids: tuple[str, ...]

    def record(self):
        return dict(group_id=self.group_id, industry=self.industry, object=self.object,
                    companies=self.companies, direct=self.direct, possible=self.possible,
                    indirect=self.indirect, example_company_ids=list(self.example_company_ids),
                    topic_ids=list(self.topic_ids))


class InterestCatalog:
    def __init__(self, path, aliases=None):
        path = Path(path)
        self.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream, delimiter=';')
            if not set(FIELDS) <= set(reader.fieldnames or []):
                raise ValueError('Interest CSV is missing required columns')
            rows = []
            for number, row in enumerate(reader, 2):
                try:
                    numbers = [int(row[key]) for key in FIELDS[3:7]]
                    if any(n < 0 for n in numbers) or numbers[0] != sum(numbers[1:]):
                        raise ValueError('Company counts must be nonnegative and reconcile')
                    if not all(row[key].strip() for key in FIELDS[:3]):
                        raise ValueError('Empty group, industry or object')
                    rows.append(Interest(*(row[key].strip() for key in FIELDS[:3]), *numbers,
                        *(tuple(x.strip() for x in row[key].split(',') if x.strip()) for key in FIELDS[7:])))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f'Invalid interest CSV row {number}: {exc}') from exc
        if not rows or len({row.group_id for row in rows}) != len(rows):
            raise ValueError('Interest CSV must contain unique, nonempty group IDs')
        self.rows = rows
        self.by_id = {row.group_id: row for row in rows}
        self.industries = sorted({row.industry for row in rows})
        aliases = json.loads(Path(aliases).read_text(encoding='utf-8')) if aliases else {}
        unknown = set(aliases) - set(self.industries)
        # Shared alias catalogs may include industries absent from a smaller
        # custom table. They never manufacture interest rows.
        self.unused_alias_industries = sorted(unknown)
        self.alias_sha256 = hashlib.sha256(json.dumps(aliases, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        self.fingerprint = hashlib.sha256((self.sha256 + self.alias_sha256 + METHOD).encode()).hexdigest()
        self.phrases = []
        for row in rows:
            self.phrases.append(('object', row.group_id, row.object, terms(row.object)))
        for industry in self.industries:
            values = aliases.get(industry, [])
            if not isinstance(values, list) or any(not isinstance(x, str) or not terms(x) for x in values):
                raise ValueError('Industry aliases must be lists of nonempty text phrases')
            for phrase in dict.fromkeys([industry, *values]):
                self.phrases.append(('industry', industry, phrase, terms(phrase)))
        frequency = Counter(word for *_, phrase in self.phrases for word in set(phrase))
        self.index = defaultdict(list)
        for number, (*_, phrase) in enumerate(self.phrases):
            if phrase:
                self.index[min(phrase, key=lambda word: frequency[word])].append(number)
        self._cache = {}
        self.object_index = defaultdict(set)
        for row in rows:
            for word in set(terms(row.object)):
                if len(word) >= 4 or word.isascii() and len(word) >= 2:
                    self.object_index[word].add(row.group_id)

    def summary(self):
        return {'catalog_sha256': self.sha256, 'aliases_sha256': self.alias_sha256,
                'matcher_fingerprint': self.fingerprint, 'method': METHOD,
                'objects': len(self.rows), 'industries': len(self.industries),
                'zero_company_objects': sum(row.companies == 0 for row in self.rows),
                'note': 'Counts overlap across objects. Example company IDs are not a complete company list. Matches are heuristic, not training labels.'}

    def match(self, title, text=''):
        found = {}
        for field, value in (('title', title), ('text', text)):
            words = terms(value or '')
            positions = defaultdict(list)
            for offset, word in enumerate(words):
                positions[word].append(offset)
            candidates = {number for word in positions for number in self.index.get(word, [])}
            for number in sorted(candidates):
                kind, key, phrase, expected = self.phrases[number]
                # A contiguous phrase after stop-word/inflection normalization.
                # Never match substrings (e.g. AI inside another word).
                if not all(word in positions for word in expected):
                    continue
                at = next((offset for offset in positions[expected[0]]
                           if words[offset:offset + len(expected)] == expected), None)
                if at is None:
                    continue
                evidence = {'phrase': phrase, 'field': field,
                            'excerpt': ' '.join(words[max(0, at - 4):at + len(expected) + 4])}
                previous = found.get((kind, key))
                if previous is None or previous['field'] != 'title' and field == 'title':
                    found[kind, key] = evidence
        objects = []
        industries = {}
        for (kind, key), evidence in found.items():
            if kind == 'object':
                row = self.by_id[key]
                objects.append({'group_id': key, 'object': row.object, 'industry': row.industry,
                                'companies': row.companies, **evidence})
                industries.setdefault(row.industry, {'industry': row.industry, 'basis': 'object'})
            else:
                industries[key] = {'industry': key, 'basis': 'phrase', **evidence}
        weight = max((math.log1p(row['companies']) for row in objects), default=0)
        score = (100 if objects else 0) + (30 if any(e['field'] == 'title' for e in found.values()) else 0) + min(20, len(industries) * 2) + round(weight)
        return {'method': METHOD, 'catalog_sha256': self.sha256,
                'matcher_fingerprint': self.fingerprint, 'matched': bool(found), 'score': score,
                'object_matches': objects, 'industry_matches': list(industries.values()),
                'is_training_label': False}

    def match_record(self, record):
        key = (record['id'], record['content_hash'])
        if key not in self._cache:
            self._cache[key] = self.match(record['title'], record['text'])
        return self._cache[key]

    def priority(self, title, url=''):
        return self.match(title, unquote(url).replace('-', ' ').replace('_', ' '))['score'] * 1000

    def keyword_candidates(self, record, match):
        """Broader lexical retrieval is separate from direct phrase matches."""
        title_words = set(terms(record['title']))
        body_words = set(terms(record['text']))
        industries = {entry['industry'] for entry in match['industry_matches']}
        direct = {entry['group_id'] for entry in match['object_matches']}
        candidates = set().union(*(self.object_index.get(word, set()) for word in title_words | body_words))
        generic = set(terms('корпоративный финансовый управление деятельность услуга система товар продукт компания производство новый'))
        result = []
        for key in sorted(candidates - direct):
            row = self.by_id[key]
            expected = set(terms(row.object)) - generic
            shared = expected & (title_words | body_words)
            if not expected or not shared or row.industry not in industries:
                continue
            # A common adjective by itself is not a specific object match.
            if not shared & title_words and len(shared) < 2 and len(expected) > 1:
                continue
            result.append({'group_id': key, 'industry': row.industry,
                           'matched_terms': sorted(shared),
                           'score': round(30 * len(shared) / len(expected)) + (20 if shared & title_words else 0)})
        return result


def read_records(runtime):
    """A single read-only WAL snapshot; never instantiate Store on a live input."""
    db = Path(runtime).resolve() / 'news.sqlite3'
    with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=30)) as connection:
        connection.execute('BEGIN')
        for encoded, first_seen, last_seen in connection.execute(
                'SELECT record,first_seen_at,last_seen_at FROM articles ORDER BY first_seen_at,id'):
            record = json.loads(encoded)
            record.update(first_seen_at=first_seen, last_seen_at=last_seen)
            yield record


def select_diverse(candidates, limit):
    """Input (rank, reference, record); same text once, prefer source diversity."""
    candidates = sorted(candidates, key=lambda x: (x[0], x[2].get('published_at') or '', x[2]['id']), reverse=True)
    selected, seen = [], set()
    tiers = defaultdict(list)
    for item in candidates:
        tier = {'object_phrase': 3, 'object_keywords': 2}.get(item[1]['match_type'], 1)
        tiers[tier].append(item)
    for tier in sorted(tiers, reverse=True):
        accepted, deferred, counts = [], [], Counter()
        for item in tiers[tier]:
            text_hash = item[2]['text_hash']
            if text_hash in seen:
                continue
            seen.add(text_hash)
            if counts[item[2]['source_id']] >= 3:
                deferred.append(item)
            else:
                accepted.append(item)
                counts[item[2]['source_id']] += 1
        selected.extend((accepted + deferred)[:limit - len(selected)])
        if len(selected) == limit:
            break
    return selected


def export_topics(catalog, inputs, output, window, sources_config, source_map,
                  source_checks=(), limit=20):
    """Build up to twenty references per object/industry from existing news.

    No input writes, Chrome, fetches, guessed dates or duplicated article bodies.
    Broader industry context never silently becomes a direct object match.
    A generation directory plus atomic CURRENT.json keeps readers consistent.
    """
    from .models import load_sources
    import shutil
    import uuid

    if not 10 <= limit <= 20:
        raise ValueError('Per-theme limit must be between 10 and 20')
    inputs = list(dict.fromkeys(Path(path).resolve() for path in inputs))
    output = Path(output).resolve()
    if output in inputs:
        raise ValueError('Topic exports require a separate output directory')
    sources = {source.id: source for source in load_sources(Path(sources_config))}
    specialties = json.loads(Path(source_map).read_text(encoding='utf-8'))
    for industry in catalog.industries:
        ids = specialties.get(industry, [])
        if not isinstance(ids, list) or len(set(ids)) < 2 or set(ids) - set(sources):
            raise ValueError(f'Need at least two configured specialty sources for {industry}')
    checks = {}
    for path in source_checks:
        for row in json.loads(Path(path).read_text())['sources']:
            if row.get('checked_at', '') >= checks.get(row['source_id'], {}).get('checked_at', ''):
                checks[row['source_id']] = row

    industry_pool, object_pool = defaultdict(list), defaultdict(list)
    object_source_counts, industry_source_counts = Counter(), Counter()
    source_examples, source_totals = defaultdict(list), Counter()
    source_dated, source_full = Counter(), Counter()
    source_ready = Counter()
    counts, seen_ids, seen_hashes = Counter(), set(), set()
    matched_records = []
    for runtime in inputs:
        for record in read_records(runtime):
            counts['input_records'] += 1
            if record['id'] in seen_ids:
                counts['duplicate_ids'] += 1
                continue
            seen_ids.add(record['id'])
            source_id = record['source_id']
            source_totals[source_id] += 1
            source_dated[source_id] += bool(record.get('published_at'))
            source_full[source_id] += record.get('text_scope') != 'accessible_excerpt'
            if len(source_examples[source_id]) < 2:
                source_examples[source_id].append({'url': record['canonical_url'], 'title': record['title'],
                    'published_at': record.get('published_at'), 'text_scope': record.get('text_scope')})
            if not record.get('published_at'):
                counts['undated_excluded'] += 1
                continue
            if not window.contains(record['published_at']):
                counts['outside_period_excluded'] += 1
                continue
            if record.get('text_scope') == 'accessible_excerpt':
                counts['paid_excerpts_excluded'] += 1
                continue
            if record['text_hash'] in seen_hashes:
                counts['duplicate_texts_excluded'] += 1
                continue
            seen_hashes.add(record['text_hash'])
            counts['eligible_articles'] += 1
            source_ready[source_id] += 1
            match = catalog.match_record(record)
            if not match['matched']:
                continue
            matched_records.append((record, runtime, match))
            counts['matched_articles'] += 1
            for entry in match['industry_matches']:
                score = match['score'] + (50 if entry.get('field') == 'title' else 0)
                reference = {'article_id': record['id'], 'match_type': 'industry_phrase',
                             'evidence': entry, 'needs_review': True}
                industry_pool[entry['industry']].append((score, reference, record))
                industry_source_counts[entry['industry'], source_id] += 1
            for entry in match['object_matches']:
                reference = {'article_id': record['id'], 'match_type': 'object_phrase',
                             'evidence': entry, 'needs_review': True}
                object_pool[entry['group_id']].append((1000 + match['score'], reference, record))
                object_source_counts[entry['group_id'], source_id] += 1
            for entry in catalog.keyword_candidates(record, match):
                reference = {'article_id': record['id'], 'match_type': 'object_keywords',
                             'evidence': entry, 'needs_review': True}
                object_pool[entry['group_id']].append((500 + entry['score'], reference, record))

    registry = {}
    for slug, source in sources.items():
        check = checks.get(slug, {})
        registry[slug] = {'source_id': slug, 'name': source.name, 'section_urls': source.seeds,
            'language': source.language, 'publisher_country': source.publisher_country,
            'enabled': source.enabled, 'source_kind': source.source_kind,
            'saved_articles': source_totals[slug], 'dated_articles': source_dated[slug],
            'non_excerpt_articles': source_full[slug], 'eligible_articles': source_ready[slug],
            'validation': {'status': check.get('status', 'not_provided'),
                           'checked_at': check.get('checked_at'),
                           'sample_count': len(check.get('samples', []))},
            'examples': source_examples[slug] or check.get('samples', [])[:2],
            'collection_method': 'selenium_chrome',
            'availability_note': 'Last observed result only; continued access/full text is not guaranteed.'}

    def recommendations(industry, group_id=None):
        profile = specialties[industry]
        observed = [slug for (name, slug), count in industry_source_counts.items()
                    if name == industry and count and slug in registry]
        candidates = list(dict.fromkeys([*profile, *observed]))
        def rank(slug):
            return (bool(group_id and object_source_counts[group_id, slug]),
                    slug in profile and industry_source_counts[industry, slug] > 0,
                    slug in profile, bool(source_ready[slug]),
                    industry_source_counts[industry, slug])
        result = []
        for slug in sorted(candidates, key=rank, reverse=True)[:5]:
            result.append({'source_id': slug, 'name': registry[slug]['name'],
                'section_urls': registry[slug]['section_urls'],
                'selection_basis': 'editorial_specialty' if slug in profile else 'observed_topic_articles',
                'topic_articles_in_corpus': industry_source_counts[industry, slug],
                'direct_object_articles_in_corpus': object_source_counts[group_id, slug] if group_id else None,
                'object_topic_verified': bool(group_id and object_source_counts[group_id, slug]),
                'parser_verified': source_totals[slug] >= 2 or checks.get(slug, {}).get('status') == 'passed',
                'dated_full_text_available': bool(source_ready[slug]),
                'validation': registry[slug]['validation']})
        return result

    industry_rows, object_rows = [], []
    selected_ids = set()
    for industry in catalog.industries:
        selected = select_diverse(industry_pool[industry], limit)
        selected_ids.update(item[2]['id'] for item in selected)
        industry_rows.append({'industry': industry, 'target': limit, 'article_count': len(selected),
            'missing_to_target': max(0, limit - len(selected)),
            'articles': [item[1] for item in selected], 'sources': recommendations(industry)})
    for row in catalog.rows:
        direct = select_diverse(object_pool[row.group_id], limit)
        used = {item[2]['text_hash'] for item in direct}
        context = []
        if len(direct) < limit:
            for item in select_diverse(industry_pool[row.industry], limit):
                if item[2]['text_hash'] not in used:
                    context.append((item[0], {**item[1], 'match_type': 'industry_context',
                        'note': 'Related industry context; no confirmed mention of this exact object.'}, item[2]))
                    used.add(item[2]['text_hash'])
                if len(direct) + len(context) == limit:
                    break
        selected = direct + context
        selected_ids.update(item[2]['id'] for item in selected)
        exact_count = sum(item[1]['match_type'] == 'object_phrase' for item in selected)
        object_rows.append({**row.record(), 'target': limit, 'article_count': len(selected),
            'direct_phrase_count': exact_count, 'keyword_candidate_count': len(direct) - exact_count,
            'industry_context_count': len(context), 'missing_to_target': max(0, limit - len(selected)),
            'articles': [item[1] for item in selected], 'sources': recommendations(row.industry, row.group_id)})

    output.mkdir(parents=True, exist_ok=True)
    generations = output / 'generations'
    generations.mkdir(exist_ok=True)
    generation = generations / uuid.uuid4().hex
    generation.mkdir()
    atomic_json(generation / 'generation.json', {'producer': 'alfa-interest-export-v1'})
    def jsonl(name, rows):
        with (generation / name).open('w', encoding='utf-8') as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    try:
        jsonl('themes.jsonl', object_rows)
        jsonl('industries.jsonl', industry_rows)
        jsonl('articles.jsonl', ({**record, 'origin_runtime': str(runtime)} for record, runtime, _ in matched_records
                                if record['id'] in selected_ids))
        jsonl('article-matches.jsonl', ({'article_id': record['id'], 'content_hash': record['content_hash'], **match}
                                      for record, _, match in matched_records if record['id'] in selected_ids))
        jsonl('theme-sources.jsonl', ({'group_id': row['group_id'], 'object': row['object'],
                    'industry': row['industry'], 'sources': row['sources']} for row in object_rows))
        atomic_json(generation / 'source-catalog.json', registry)
        selected_records = {record['id']: record for record, _, _ in matched_records if record['id'] in selected_ids}
        def detail_page(kind, key, title, references, recommended):
            directory = generation / kind
            directory.mkdir(exist_ok=True)
            path = directory / (hashlib.sha256(key.encode()).hexdigest()[:20] + '.md')
            detail = [f'# {title}', '', '[Все подборки](../README.md)', '',
                      '## Источники', '']
            for source in recommended:
                detail.append(f"- [{source['name']}]({source['section_urls'][0]}): "
                              f"статей отрасли в корпусе — {source['topic_articles_in_corpus']}; "
                              f"проверка парсера — {'есть' if source['parser_verified'] else 'не подтверждена'}.")
            detail += ['', '## Статьи', '']
            for number, reference in enumerate(references, 1):
                article = selected_records[reference['article_id']]
                label = {'object_phrase': 'Фраза объекта', 'object_keywords': 'Ключевые слова',
                         'industry_phrase': 'Отраслевая тема', 'industry_context': 'Только отраслевой контекст'}[reference['match_type']]
                detail += [f"{number}. [{article['title']}]({article['canonical_url']})", '',
                    f"   {article['source_name']} · {article['published_at']} · **{label}**", '',
                    '   ' + article['text'][:360].replace('\n', ' ') + '…', '']
            path.write_text('\n'.join(detail), encoding='utf-8')
            return str(path.relative_to(generation))
        for row in industry_rows:
            row['detail_path'] = detail_page('industries', row['industry'], row['industry'], row['articles'], row['sources'])
        for row in object_rows:
            row['detail_path'] = detail_page('themes', row['group_id'], row['object'], row['articles'], row['sources'])
        # Include stable relative detail paths in machine-readable manifests.
        jsonl('themes.jsonl', object_rows)
        jsonl('industries.jsonl', industry_rows)
        report = {'updated_at': utcnow(), **catalog.summary(), **window.record(), 'counts': dict(counts),
            'inputs': [str(path) for path in inputs], 'per_theme_target': limit,
            'selected_unique_articles': len(selected_ids),
            'industries_with_20': sum(row['article_count'] >= 20 for row in industry_rows),
            'industries_with_at_least_10': sum(row['article_count'] >= 10 for row in industry_rows),
            'objects_with_20_candidates': sum(row['article_count'] >= 20 for row in object_rows),
            'objects_with_at_least_10_candidates': sum(row['article_count'] >= 10 for row in object_rows),
            'objects_with_20_phrase_matches': sum(row['direct_phrase_count'] >= 20 for row in object_rows),
            'objects_with_any_phrase_matches': sum(row['direct_phrase_count'] > 0 for row in object_rows),
            'objects_without_articles': sum(row['article_count'] == 0 for row in object_rows),
            'source_profiles': len(registry), 'sources_per_theme_minimum': min(len(row['sources']) for row in object_rows),
            'selection_note': 'Phrase/keyword retrieval is heuristic. Industry-context candidates are explicitly marked, not exact-object matches or ML ground truth. Articles may belong to several themes; bodies are stored once.'}
        atomic_json(generation / 'interest-report.json', report)
        lines = ['# Подборки новостей по интересам', '',
            f"Обновлено: {report['updated_at']}. Проверенный период UTC: [{window.start.isoformat()}, {window.end.isoformat()}).",
            f"Объектов: {len(object_rows)}. Отраслей: {len(industry_rows)}. Уникальных текстов в подборках: {len(selected_ids)}.",
            '', '## Как читать данные', '',
            '`themes.jsonl`: строка на объект CSV, `group_id` сохраняется. `industries.jsonl`: строка на отрасль. '
            '`articles.jsonl`: полные статьи, соединение по `articles[].article_id = id`. '
            '`theme-sources.jsonl`: отдельный каталог источников по каждому объекту. `source-catalog.json`: рубрики и свидетельства работы парсера.',
            '', 'В подборке до 20 текстов. `object_phrase` — фраза объекта с нормализацией окончаний; '
            '`object_keywords` — более широкие ключевые слова внутри отрасли; `industry_context` — только отраслевой контекст, '
            '**не подтверждённое соответствие конкретному объекту**. Это кандидаты для просмотра, а не метки обучения. '
            'Одна статья может быть полезна нескольким темам; внутри темы одинаковый text_hash не повторяется.',
            '', 'Неизвестная дата, выход за период и известные платные фрагменты исключены. '
            'Нулевой счётчик компаний не исключает тему. Примеры ID компаний не считаются полным списком компаний. '
            'Входящие ID тем сохранены как исходные связи; их описания в CSV отсутствуют.',
            '', 'Источники отсортированы по прямым совпадениям объекта, профильности редакции и фактическим статьям. '
            '`object_topic_verified=false` означает, что именно для этого узкого объекта примера пока нет. '
            'Успешная проверка двух текстов подтверждает работу адаптера на момент проверки, но не постоянную доступность сайта.',
            '', '## Покрытие отраслей', '', '| Отрасль | Статей | Рекомендуемые источники |', '|---|---:|---|']
        for row in industry_rows:
            names = ', '.join(f"[{source['name']}]({source['section_urls'][0]})" for source in row['sources'])
            lines.append(f"| [{row['industry']}]({row['detail_path']}) | {row['article_count']} | {names} |")
        lines += ['', '## Объекты с нехваткой прямых совпадений', '',
                  '| Объект | Отрасль | Фразы | Ключевые слова | Отраслевой контекст | Всего |',
                  '|---|---|---:|---:|---:|---:|']
        for row in object_rows:
            if row['direct_phrase_count'] < limit:
                lines.append(f"| [{row['object']}]({row['detail_path']}) | {row['industry']} | {row['direct_phrase_count']} | {row['keyword_candidate_count']} | {row['industry_context_count']} | {row['article_count']} |")
        lines += ['', '## Все объекты', '', '| Объект | Отрасль | Кандидатов |', '|---|---|---:|']
        lines.extend(f"| [{row['object']}]({row['detail_path']}) | {row['industry']} | {row['article_count']} |" for row in object_rows)
        (generation / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        # Never prune the currently published generation. Retain one previous
        # generation so a reader can finish loading it during refresh.
        prior = json.loads((output / 'CURRENT.json').read_text()) if (output / 'CURRENT.json').exists() else None
        atomic_json(output / 'CURRENT.json', {'generation': str(generation.relative_to(output)),
                    'updated_at': report['updated_at'], 'report': 'interest-report.json'})
        pointer = output / 'latest'
        temporary_link = output / ('latest-' + uuid.uuid4().hex)
        temporary_link.symlink_to(generation.relative_to(output), target_is_directory=True)
        temporary_link.replace(pointer)
        keep = {generation.name}
        if prior:
            prior_path = (output / prior['generation']).resolve()
            if prior_path.parent == generations.resolve():
                keep.add(prior_path.name)
        for path in generations.iterdir():
            marker = path / 'generation.json'
            if (path.is_dir() and not path.is_symlink() and re.fullmatch('[0-9a-f]{32}', path.name)
                    and path.name not in keep and marker.is_file()
                    and json.loads(marker.read_text()).get('producer') == 'alfa-interest-export-v1'):
                shutil.rmtree(path)
    except BaseException:
        # Unpublished partial generation is harmless; never touch inputs.
        raise
    return report


