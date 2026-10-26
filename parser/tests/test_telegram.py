from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import json

from news_collector.browser import Page
from news_collector.history import Window, timestamp
from news_collector.telegram import TelegramStore, collect_telegram, parse_preview, public_url
from news_collector.interests import InterestCatalog
from test_interests import table


class TelegramTests(unittest.TestCase):
    def test_public_preview_posts_dates_media_forwarding_and_history_offset(self):
        html = '''<html><head><meta property="og:title" content="Test channel"></head><body>
          <div class="tgme_channel_info_counter"><span>12K</span> subscribers</div>
          <div data-post="sample_news/42"><div class="tgme_widget_message_text">Текст <b>поста</b><br>Вторая строка</div>
          <a class="tgme_widget_message_date"><time datetime="2026-10-01T12:00:00+03:00"></time></a>
          <a class="tgme_widget_message_photo_wrap" style="background-image:url('https://cdn.example/photo.jpg')"></a>
          <a class="tgme_widget_message_forwarded_from" href="https://t.me/original_news/1">Источник</a>
          <span class="tgme_widget_message_views">1.5K</span></div>
          <div data-post="sample_news/43"><a class="tgme_widget_message_date"><time datetime="2026-10-02T00:00:00Z"></time></a></div>
          <div data-post="other_news/55"><div class="tgme_widget_message_text">Не наш канал</div></div>
          <a class="tme_messages_more" href="/s/sample_news?before=42">Earlier</a></body></html>'''
        page = Page('https://t.me/s/sample_news', 'https://t.me/s/sample_news', 'Preview', html, '', 200)
        posts, before, info = parse_preview(page, 'sample_news', 'raw/test.gz')
        self.assertEqual(len(posts), 2)
        self.assertEqual(before, 42)
        self.assertEqual(info['title'], 'Test channel')
        self.assertEqual(posts[0]['published_at'], '2026-10-01T09:00:00+00:00')
        self.assertEqual(posts[0]['images'][0]['url'], 'https://cdn.example/photo.jpg')
        self.assertEqual(posts[0]['forwarded_from_url'], 'https://t.me/original_news/1')
        self.assertFalse(posts[0]['ml_export_allowed'])
        self.assertEqual(posts[0]['dataset_purpose'], 'internal_analytics')
        self.assertIn('media_only_or_preview_text_unavailable', posts[1]['quality_flags'])
        same, _, _ = parse_preview(page, 'SAMPLE_NEWS')
        self.assertEqual(posts[0]['id'], same[0]['id'])

    def test_invalid_username_and_external_history_link_are_rejected(self):
        for handle in ('../../secret', 'bad?name', '+privateinvite', 'bad/55'):
            with self.assertRaises(ValueError):
                public_url(handle)
        page = Page('', 'https://t.me/s/sample_news', '',
                    '<a class="tme_messages_more" href="https://evil.example/s/sample_news?before=5">More</a>', '', 200)
        self.assertIsNone(parse_preview(page, 'sample_news')[1])

    def test_store_upserts_edits_and_freezes_window(self):
        with tempfile.TemporaryDirectory() as folder:
            store = TelegramStore(Path(folder) / 'telegram.sqlite3')
            window = Window(timestamp('2026-09-01'), timestamp('2026-11-01'))
            store.bind_window(window)
            record = {'id': 'one', 'channel': 'sample_news', 'message_id': 1,
                      'published_at': '2026-10-01T00:00:00+00:00', 'text': 'first'}
            self.assertEqual(store.save([record]), 1)
            self.assertEqual(store.save([{**record, 'text': 'edited'}]), 0)
            self.assertEqual(store.db.execute('SELECT count(*) FROM posts').fetchone()[0], 1)
            self.assertIn('edited', store.db.execute('SELECT record FROM posts').fetchone()[0])
            with self.assertRaises(ValueError):
                store.bind_window(Window(timestamp('2026-08-01'), timestamp('2026-09-01')))
            self.assertNotIn('articles', {row[0] for row in store.db.execute('SELECT name FROM sqlite_master')})
            store.close()

    def test_telegram_rejects_news_runtime_before_creating_any_analytics_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'news.sqlite3').write_bytes(b'not to be touched')
            with self.assertRaisesRegex(ValueError, 'dedicated runtime'):
                collect_telegram(root, root / 'missing-config.json', None, None, threading.Event())
            self.assertEqual((root / 'news.sqlite3').read_bytes(), b'not to be touched')
            self.assertFalse((root / 'telegram.sqlite3').exists())

    def test_collection_keeps_real_period_and_separate_analytics_storage(self):
        class FakeBrowser:
            def __init__(self, *args, **kwargs):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        def read(collector, browser, pacing, source, url, **kwargs):
            handle = url.rsplit('/', 1)[-1]
            body = '<html><body>'
            for number, date in enumerate(('2026-08-01T00:00:00Z', '2026-10-01T00:00:00Z', '2026-12-01T00:00:00Z'), 1):
                body += f'<div data-post="{handle}/{number}"><div class="tgme_widget_message_text">Лизинг автопарка</div><time datetime="{date}"></time></div>'
            body += '</body></html>'
            return Page(url, url, 'Channel', body, '', 200)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            catalog = InterestCatalog(table(root / 'input.csv'))
            config = root / 'channels.json'
            config.write_text(json.dumps({'channels': [{'handle': 'sample_news'}, {'handle': 'other_news'}],
                'industries': {'Финансы': [{'handle': 'sample_news', 'scope': 'industry'},
                                         {'handle': 'other_news', 'scope': 'industry'}]}}))
            with patch('news_collector.telegram.Browser', FakeBrowser), \
                 patch('news_collector.telegram.Collector.paced_read', read), \
                 patch('news_collector.telegram.Collector.robots', return_value=True):
                runtime = root / 'analytics'
                report = collect_telegram(runtime, config, catalog,
                    Window(timestamp('2026-09-01'), timestamp('2026-11-01')), threading.Event(), max_pages=1)
            self.assertEqual(report['posts'], 2)
            self.assertEqual(report['industries_with_two_channels'], 0)  # one saved post is insufficient proof
            records = [json.loads(line) for line in (runtime / 'telegram-posts.jsonl').read_text().splitlines()]
            self.assertTrue(all(record['published_at'].startswith('2026-10-01') for record in records))
            self.assertTrue(all(record['ml_export_allowed'] is False for record in records))
            self.assertFalse((runtime / 'news.sqlite3').exists())


if __name__ == '__main__':
    unittest.main()
