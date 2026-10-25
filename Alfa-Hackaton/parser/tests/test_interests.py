import csv
from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import unittest

from news_collector.extract import extract_article
from news_collector.history import Window, timestamp
from news_collector.interests import FIELDS, InterestCatalog, export_topics, read_records, select_diverse
from news_collector.storage import Store
from test_collector import SOURCE, page


def table(path, rows=None):
    rows = rows or [('group::lease', 'Финансы', 'Лизинг автопарка', 4, 2, 1, 1, 'U_1, U_2', 'bt_1, bt_2'),
                    ('group::risk', 'Финансы', 'Кредитный риск', 0, 0, 0, 0, '', 'bt_3')]
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream, delimiter=';')
        writer.writerow(FIELDS)
        writer.writerows(rows)
    return path


class InterestTests(unittest.TestCase):
    def test_csv_bom_semicolon_ids_counts_and_zero_groups(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog = InterestCatalog(table(Path(folder) / 'input.csv'))
            self.assertEqual(len(catalog.rows), 2)
            self.assertEqual(catalog.rows[0].example_company_ids, ('U_1', 'U_2'))
            self.assertEqual(catalog.rows[0].topic_ids, ('bt_1', 'bt_2'))
            self.assertEqual(catalog.summary()['zero_company_objects'], 1)
            self.assertTrue(catalog.match('Оценка кредитного риска')['matched'])

    def test_invalid_counts_and_duplicate_ids_fail_without_silent_loss(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'input.csv'
            bad = [('same', 'Финансы', 'Лизинг', 1, 0, 0, 0, '', '')]
            with self.assertRaisesRegex(ValueError, 'row 2'):
                InterestCatalog(table(path, bad))
            same = [('same', 'Финансы', 'Лизинг', 0, 0, 0, 0, '', '')] * 2
            with self.assertRaisesRegex(ValueError, 'unique'):
                InterestCatalog(table(path, same))

    def test_inflections_boundaries_and_untrusted_csv_is_only_text(self):
        with tempfile.TemporaryDirectory() as folder:
            path = table(Path(folder) / 'input.csv')
            aliases = Path(folder) / 'aliases.json'
            aliases.write_text(json.dumps({'Финансы': ['AI']}))
            catalog = InterestCatalog(path, aliases)
            match = catalog.match('Новые условия лизинга автопарка')
            self.assertEqual(match['object_matches'][0]['group_id'], 'group::lease')
            self.assertFalse(match['is_training_label'])
            self.assertFalse(catalog.match('chair and rain')['matched'])
            self.assertTrue(catalog.match('AI for business')['matched'])

    def test_equal_object_names_keep_separate_groups(self):
        with tempfile.TemporaryDirectory() as folder:
            rows = [(key, 'Финансы', 'Автобус', 0, 0, 0, 0, '', '') for key in ('a', 'b')]
            catalog = InterestCatalog(table(Path(folder) / 'input.csv', rows))
            self.assertEqual({m['group_id'] for m in catalog.match('Автобус')['object_matches']}, {'a', 'b'})

    def test_diversity_never_replaces_direct_matches_with_weaker_context(self):
        candidates = []
        for n in range(30):
            kind = 'object_phrase' if n < 20 else 'object_keywords'
            record = {'id': str(n), 'text_hash': str(n), 'source_id': 'one' if n < 20 else str(n)}
            candidates.append((1000 if n < 20 else 500, {'match_type': kind}, record))
        selected = select_diverse(candidates, 20)
        self.assertTrue(all(item[1]['match_type'] == 'object_phrase' for item in selected))

    def test_export_refs_exclusions_context_separation_and_readonly_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            catalog = InterestCatalog(table(root / 'input.csv'))
            config = root / 'sources.json'
            other = replace(SOURCE, id='other', seeds=['https://other.example/'], domains=['other.example'])
            config.write_text(json.dumps({'sources': [asdict(SOURCE), asdict(other)]}))
            mapping = root / 'mapping.json'
            mapping.write_text(json.dumps({'Финансы': [SOURCE.id, 'other']}))
            runtime = root / 'input'
            store = Store(runtime / 'news.sqlite3')
            article = extract_article(page(), SOURCE, 'raw/test.gz')
            article.title = 'Лизинг автопарка'
            article.text = 'Лизинг автопарка дешевеет. ' * 20
            article.published_at = '2026-10-01T00:00:00+00:00'
            store.enqueue(SOURCE.id, [article.url])
            store.complete(store.claim(SOURCE.id), article)
            undated = replace(article, url=article.url + '/undated', canonical_url=article.canonical_url + '/undated', published_at=None)
            store.enqueue(SOURCE.id, [undated.url])
            store.complete(store.claim(SOURCE.id), undated)
            before = [tuple(row) for row in store.db.execute('SELECT * FROM articles ORDER BY id')]
            report = export_topics(catalog, [runtime], root / 'output',
                Window(timestamp('2026-09-01'), timestamp('2026-11-01')), config, mapping)
            self.assertEqual(report['counts']['undated_excluded'], 1)
            self.assertEqual(report['selected_unique_articles'], 1)
            self.assertEqual(before, [tuple(row) for row in store.db.execute('SELECT * FROM articles ORDER BY id')])
            store.close()
            latest = root / 'output' / 'latest'
            rows = [json.loads(line) for line in (latest / 'themes.jsonl').read_text().splitlines()]
            self.assertEqual(rows[0]['direct_phrase_count'], 1)
            self.assertEqual(rows[1]['direct_phrase_count'], 0)
            self.assertEqual(rows[1]['articles'][0]['match_type'], 'industry_context')
            articles = {record['id'] for record in map(json.loads, (latest / 'articles.jsonl').read_text().splitlines())}
            self.assertTrue(all(ref['article_id'] in articles for row in rows for ref in row['articles']))
            self.assertEqual(len(list(read_records(runtime))), 2)
            for _ in range(3):
                export_topics(catalog, [runtime], root / 'output',
                    Window(timestamp('2026-09-01'), timestamp('2026-11-01')), config, mapping)
            generations = list((root / 'output' / 'generations').iterdir())
            self.assertEqual(len(generations), 2)


if __name__ == '__main__':
    unittest.main()
