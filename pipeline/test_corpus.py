import unittest
from corpus import merge_streams, timestamp, jsonl
from tempfile import TemporaryDirectory
from pathlib import Path
import json


class CorpusTests(unittest.TestCase):
    def test_old_live_does_not_revert_final_snapshot(self):
        latest = dict(id='a', content_hash='new', fetched_at='2026-10-25T01:41:25Z')
        stale = dict(id='a', content_hash='old', fetched_at='2026-10-24T19:56:33Z')
        rows, origins, conflicts = merge_streams([('final', [latest]), ('live', [stale, dict(id='b')])])
        self.assertEqual(rows['a']['content_hash'], 'new')
        self.assertIn('b', rows)
        self.assertEqual(conflicts[0]['selected_origin'], 'final')

    def test_new_live_and_timezone_order(self):
        first = dict(id='a', content_hash='old', fetched_at='2026-10-25T06:00:00+03:00')
        newer = dict(id='a', content_hash='new', fetched_at='2026-10-25T04:00:00Z')
        self.assertGreater(timestamp(newer), timestamp(first))
        self.assertEqual(merge_streams([('final', [first]), ('live', [newer])])[0]['a'], newer)

    def test_no_date_uses_stable_priority_not_publication_date(self):
        a = dict(id='a', content_hash='one', published_at='2099-01-01T00:00:00Z')
        b = dict(id='a', content_hash='two', fetched_at='invalid')
        self.assertEqual(merge_streams([('final', [a]), ('live', [b])])[0]['a'], a)

    def test_unicode_separator_not_an_extra_row(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'records.jsonl'
            path.write_text(json.dumps({'id': 'a', 'text': 'a\u2028b'}, ensure_ascii=False) + '\n')
            self.assertEqual(len(list(jsonl(path))), 1)


if __name__ == '__main__':
    unittest.main()
