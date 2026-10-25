"""Public Telegram previews through isolated Chrome; internal analytics only."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import gzip
import json
import logging
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urljoin, urlsplit, parse_qs

from lxml import html

from .browser import Browser, AccessBlocked
from .extract import article_element_text, parse_date
from .history import Window, atomic_json, timestamp
from .models import Source, digest, utcnow
from .runner import Collector
from .storage import Store

LOG = logging.getLogger(__name__)
HANDLE = re.compile(r'[a-zA-Z][a-zA-Z0-9_]{3,31}')


def public_url(handle, before=None):
    if not HANDLE.fullmatch(handle):
        raise ValueError('Invalid public channel username')
    if before is not None and (not isinstance(before, int) or before < 1):
        raise ValueError('Invalid history message offset')
    return f'https://t.me/s/{handle}' + (f'?before={before}' if before else '')


def parse_preview(page, handle, raw_path=''):
    """Do not confuse forwarded/quoted IDs with the wrapper post identity."""
    expected = handle.casefold()
    tree = html.fromstring(page.html)
    posts = []
    seen = set()
    for node in tree.xpath('//*[@data-post]'):
        match = re.fullmatch(r'([A-Za-z][A-Za-z0-9_]{3,31})/(\d+)', node.get('data-post', ''))
        if not match or match[1].casefold() != expected or int(match[2]) in seen:
            continue
        seen.add(int(match[2]))
        bodies = node.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," tgme_widget_message_text ")]')
        text = '\n\n'.join(article_element_text(body) for body in bodies)
        dates = node.xpath('.//a[contains(@class,"tgme_widget_message_date")]//time/@datetime')
        if not dates:
            dates = node.xpath('.//time/@datetime')
        published, status = parse_date(dates[0] if dates else None)
        images = []
        for anchor in node.xpath('.//a[contains(@class,"tgme_widget_message_photo_wrap")]'):
            image = re.search(r"background-image\s*:\s*url\(['\"]?(.*?)['\"]?\)", anchor.get('style', ''))
            if image and urlsplit(image[1]).scheme in ('http', 'https'):
                images.append({'url': image[1], 'role': 'telegram_preview', 'may_expire': True})
        forwarded = node.xpath('.//a[contains(@class,"tgme_widget_message_forwarded_from")]/@href')
        views = node.xpath('.//*[contains(@class,"tgme_widget_message_views")]/text()')
        posts.append({'schema_version': 1, 'kind': 'telegram_post',
            'dataset_purpose': 'internal_analytics', 'ml_export_allowed': False,
            'id': digest(f'telegram:{expected}:{match[2]}'), 'channel': expected,
            'message_id': int(match[2]), 'canonical_url': f'https://t.me/{handle}/{match[2]}',
            'title': text.split('\n', 1)[0][:180], 'text': text,
            'text_hash': digest(re.sub(r'\s+', ' ', text).strip().casefold()) if text else None,
            'published_at': published, 'publication_date_status': status,
            'fetched_at': utcnow(), 'views_raw': views[0] if views else None,
            'forwarded_from_url': forwarded[0] if forwarded else None,
            'images': images, 'raw_html_path': raw_path,
            'quality_flags': [] if text else ['media_only_or_preview_text_unavailable']})
    before = None
    for href in tree.xpath('//a[contains(@class,"tme_messages_more")]/@href'):
        url = urlsplit(urljoin(page.url, href))
        values = parse_qs(url.query).get('before', [])
        if url.hostname == 't.me' and url.path.casefold().rstrip('/') == f'/s/{expected}' and values and values[0].isdigit():
            before = int(values[0])
            break
    titles = tree.xpath('//meta[@property="og:title"]/@content')
    descriptions = tree.xpath('//meta[@property="og:description"]/@content')
    counters = [' '.join(node.text_content().split()) for node in tree.xpath('//*[contains(@class,"tgme_channel_info_counter")]')]
    return posts, before, {'title': titles[0] if titles else page.title,
        'description': descriptions[0] if descriptions else '', 'counters_raw': counters,
        'verified_badge': bool(tree.xpath('//*[contains(@class,"verified-icon")]'))}


class TelegramStore:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS posts(id TEXT PRIMARY KEY,channel TEXT NOT NULL,message_id INTEGER NOT NULL,
             published_at TEXT,record TEXT NOT NULL, UNIQUE(channel,message_id));
          CREATE TABLE IF NOT EXISTS channels(handle TEXT PRIMARY KEY,status TEXT NOT NULL,
             before_id INTEGER,checked_at TEXT,record TEXT NOT NULL,last_error TEXT);
          CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);''')

    def bind_window(self, window):
        value = json.dumps(window.record(), sort_keys=True)
        prior = self.db.execute("SELECT value FROM settings WHERE key='window'").fetchone()
        if prior and prior[0] != value:
            raise ValueError('Telegram runtime belongs to a different window')
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO settings VALUES ('window',?)", (value,))

    def save(self, posts):
        created = 0
        with self.db:
            for record in posts:
                created += not self.db.execute('SELECT 1 FROM posts WHERE id=?', (record['id'],)).fetchone()
                self.db.execute('INSERT INTO posts VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET record=excluded.record,published_at=excluded.published_at',
                    (record['id'], record['channel'], record['message_id'], record['published_at'], json.dumps(record, ensure_ascii=False)))
        return created

    def channel(self, handle, status, before, metadata, error=None):
        with self.db:
            self.db.execute('INSERT INTO channels VALUES (?,?,?,?,?,?) ON CONFLICT(handle) DO UPDATE SET '
                'status=excluded.status,before_id=excluded.before_id,checked_at=excluded.checked_at,record=excluded.record,last_error=excluded.last_error',
                (handle.casefold(), status, before, utcnow(), json.dumps(metadata, ensure_ascii=False), error))

    def close(self):
        self.db.close()


def export_telegram(store, runtime, config, catalog):
    """Telegram data never enters Store.articles or any training-news export."""
    rows = [json.loads(row[0]) for row in store.db.execute('SELECT record FROM posts ORDER BY published_at,channel,message_id')]
    stats = Counter(post['channel'] for post in rows)
    topic_counts, object_counts = Counter(), Counter()
    examples = {}
    for post in rows:
        if not post['text']:
            continue
        match = catalog.match_record({**post, 'content_hash': digest(post['text'])})
        post['interest_match'] = match
        for industry in match['industry_matches']:
            topic_counts[industry['industry'], post['channel']] += 1
            examples.setdefault((industry['industry'], post['channel']), []).append(post['canonical_url'])
        for obj in match['object_matches']:
            object_counts[obj['group_id'], post['channel']] += 1
    channels = {row['handle']: {**json.loads(row['record']), 'status': row['status'],
                'checked_at': row['checked_at'], 'last_error': row['last_error'],
                'saved_posts': stats[row['handle']], 'before_id': row['before_id']}
                for row in store.db.execute('SELECT * FROM channels')}
    by_handle = {entry['handle'].casefold(): entry for entry in config['channels']}
    industry_topics = []
    for industry in catalog.industries:
        candidates = config['industries'][industry]
        available = [entry for entry in candidates if channels.get(entry['handle'].casefold(), {}).get('status') == 'available'
                     and stats[entry['handle'].casefold()] >= 2]
        available.sort(key=lambda entry: (entry.get('scope') == 'industry',
                       topic_counts[industry, entry['handle'].casefold()]), reverse=True)
        selected = available[:2]
        industry_topics.append({'industry': industry, 'target_channels': 2,
            'channels': [{**entry, 'public_url': public_url(entry['handle']),
                'publisher_evidence': by_handle[entry['handle'].casefold()].get('publisher_evidence', []),
                'channel_title': channels[entry['handle'].casefold()].get('title'),
                'counters_raw': channels[entry['handle'].casefold()].get('counters_raw'),
                'saved_posts': stats[entry['handle'].casefold()],
                'matched_industry_posts': topic_counts[industry, entry['handle'].casefold()],
                'examples': examples.get((industry, entry['handle'].casefold()), [])[:3]}
                for entry in selected], 'missing_channels': max(0, 2 - len(selected))})
    by_industry = {row['industry']: row for row in industry_topics}
    objects = [{**row.record(), 'channels': [{**entry,
               'exact_object_posts': object_counts[row.group_id, entry['handle'].casefold()],
               'selection_level': 'industry', 'exact_object_relevance_verified': bool(object_counts[row.group_id, entry['handle'].casefold()])}
               for entry in by_industry[row.industry]['channels']],
               'missing_channels': by_industry[row.industry]['missing_channels']} for row in catalog.rows]
    def jsonl(name, values):
        path = runtime / name
        tmp = path.with_suffix(path.suffix + '.tmp')
        tmp.write_text(''.join(json.dumps(value, ensure_ascii=False) + '\n' for value in values), encoding='utf-8')
        tmp.replace(path)
    jsonl('telegram-posts.jsonl', rows)
    jsonl('telegram-industries.jsonl', industry_topics)
    jsonl('telegram-themes.jsonl', objects)
    report = {'updated_at': utcnow(), 'dataset_purpose': 'internal_analytics', 'ml_export_allowed': False,
              'posts': len(rows), 'channels_checked': len(channels),
              'channels_with_posts': len(stats), 'industries_with_two_channels': sum(not row['missing_channels'] for row in industry_topics),
              'objects_with_two_channels': sum(not row['missing_channels'] for row in objects),
              'industries_with_two_profile_channels': sum(sum(entry['scope'] == 'industry' for entry in row['channels']) == 2 for row in industry_topics),
              'industries_without_profile_channels': [row['industry'] for row in industry_topics if not any(entry['scope'] == 'industry' for entry in row['channels'])],
              'channels': channels, 'coverage_note': 'Public previews only. History is bounded; not all channels expose it. Two channels per industry are reused by its objects; narrow object relevance is separately reported.'}
    atomic_json(runtime / 'telegram-report.json', report)
    lines = ['# Telegram для внутренней аналитики', '',
        f"Обновлено: {report['updated_at']}. Постов: {len(rows)}. Каналов с постами: {len(stats)}.", '',
        'Telegram хранится отдельно от обучающего корпуса. Медиа — только ссылки. '
        'Публичный предпросмотр не гарантирует полный архив. Канал подбирается по отрасли, '
        'прямое совпадение узкого объекта отражено в exact_object_posts.', '',
        '| Отрасль | Каналы | Не хватает |', '|---|---|---:|']
    for row in industry_topics:
        links = ', '.join(f"[@{entry['handle']}]({entry['public_url']}) "
                          f"({'профильный' if entry['scope'] == 'industry' else 'широкий экономический резерв'})" for entry in row['channels'])
        lines.append(f"| {row['industry']} | {links} | {row['missing_channels']} |")
    (runtime / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return report


def collect_telegram(runtime, config_path, catalog, window, stop, headless=True,
                     max_pages=2, max_posts=40, poll_seconds=None, selected=(), follow=False):
    if max_pages < 1 or max_posts < 1 or poll_seconds is not None and poll_seconds < 300:
        raise ValueError('Positive page/post limits; polling >=300 seconds')
    runtime = Path(runtime).resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    if (runtime / 'news.sqlite3').exists() or (runtime / 'history-job.json').exists():
        raise ValueError('Telegram requires a dedicated runtime, separate from the news corpus')
    config = json.loads(Path(config_path).read_text())
    handles = [row['handle'] for row in config['channels'] if row.get('enabled', True)]
    if selected:
        if {name.casefold() for name in selected} - {name.casefold() for name in handles}:
            raise ValueError('Unknown Telegram channel')
        handles = [name for name in handles if name.casefold() in {item.casefold() for item in selected}]
    for handle in handles:
        public_url(handle)
    source = Source('telegram_public', 'Telegram public previews', ['https://t.me/s/rbc_news'], ['t.me'],
                    r'^/(?:s/)?[A-Za-z][A-Za-z0-9_]{3,31}/\d+/?$', 'ru', 'unknown', min_interval_seconds=8)
    collector = Collector(runtime, headless=headless, stop=stop)
    pacing = Store(runtime / 'pacing.sqlite3')
    store = TelegramStore(runtime / 'telegram.sqlite3')
    try:
        store.bind_window(window)
        atomic_json(runtime / 'telegram-process.json', {'pid': __import__('os').getpid(),
            'started_at': utcnow(), **window.record(), 'max_pages': max_pages, 'max_posts': max_posts,
            'poll_seconds': poll_seconds, 'follow': follow, 'purpose': 'internal_analytics'})
        while not stop.is_set():
            current_window = Window(window.start, max(window.end, datetime.now(timezone.utc))) if follow else window
            # A single browser/domain worker shares pacing across all channels.
            with Browser(runtime / 'profiles' / 'telegram', headless=headless) as browser:
                robots = {}
                for handle in handles:
                    if stop.is_set():
                        break
                    previous = store.db.execute('SELECT * FROM channels WHERE handle=?', (handle.casefold(),)).fetchone()
                    if previous and previous['status'] in ('blocked', 'error'):
                        # Explicitly changing the config/starting a new runtime
                        # is preferable to repeatedly requesting a blocked feed.
                        continue
                    if (previous and previous['checked_at'] and poll_seconds is not None
                            and time.time() - timestamp(previous['checked_at']).timestamp() < poll_seconds):
                        # Resume an interrupted catalog pass without rereading
                        # recently checked channels or increasing domain load.
                        continue
                    before, saved, metadata = None, 0, {}
                    try:
                        for page_number in range(max_pages):
                            if stop.is_set():
                                break
                            url = public_url(handle, before)
                            if not collector.robots(browser, pacing, source, url, robots):
                                store.channel(handle, 'robots_disallowed', before, metadata)
                                break
                            page = collector.paced_read(browser, pacing, source, url)
                            parsed = urlsplit(page.url)
                            if parsed.hostname != 't.me' or parsed.path.casefold().rstrip('/') != f'/s/{handle.casefold()}':
                                store.channel(handle, 'preview_unavailable', before, metadata)
                                break
                            raw = runtime / 'raw' / (digest(page.html) + '.html.gz')
                            raw.parent.mkdir(exist_ok=True)
                            raw.write_bytes(gzip.compress(page.html.encode(), mtime=0))
                            posts, next_before, metadata = parse_preview(page, handle, str(raw.relative_to(runtime)))
                            if len(posts) < 2:
                                already = store.db.execute('SELECT count(*) FROM posts WHERE channel=?', (handle.casefold(),)).fetchone()[0]
                                store.channel(handle, 'available' if already >= 2 else 'preview_unavailable', before, metadata)
                                break
                            eligible = [post for post in posts if current_window.contains(post['published_at'])]
                            # Newest first per page, then continue to older IDs.
                            eligible.sort(key=lambda post: post['message_id'], reverse=True)
                            eligible = eligible[:max(0, max_posts - saved)]
                            store.save(eligible)
                            saved += len(eligible)
                            store.channel(handle, 'available', next_before, metadata)
                            LOG.info('telegram channel=%s page=%s saved=%s', handle, page_number + 1, saved)
                            report = export_telegram(store, runtime, config, catalog)
                            oldest = min((timestamp(post['published_at']) for post in posts if post['published_at']), default=None)
                            if (saved >= max_posts or not next_before
                                    or before is not None and next_before >= before
                                    or oldest and oldest < window.start):
                                break
                            before = next_before
                    except InterruptedError:
                        store.channel(handle, 'interrupted', before, metadata)
                        break
                    except AccessBlocked as exc:
                        store.channel(handle, 'blocked', before, metadata, str(exc)[:500])
                        # Access restrictions on the shared domain stop the round.
                        LOG.warning('Telegram access restricted: %s', exc)
                        break
                    except Exception as exc:
                        store.channel(handle, 'error', before, metadata, str(exc)[:500])
                        LOG.warning('Telegram channel=%s error=%s', handle, exc)
                    report = export_telegram(store, runtime, config, catalog)
            if poll_seconds is None or stop.wait(poll_seconds):
                break
        return export_telegram(store, runtime, config, catalog)
    finally:
        store.close()
        pacing.close()
