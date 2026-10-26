"""Merge snapshots and live records without reverting newer article revisions."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3


def jsonl(path):
    # Physical file lines: U+2028 inside JSON strings is not a record boundary.
    with Path(path).open(encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def timestamp(record):
    values = []
    for field in ('fetched_at', 'last_seen_at', 'collected_at'):
        try:
            value = datetime.fromisoformat(record.get(field, '').replace('Z', '+00:00'))
            if value.tzinfo is not None:
                values.append(value.astimezone(timezone.utc))
        except (ValueError, TypeError, AttributeError):
            pass
    return max(values, default=datetime.min.replace(tzinfo=timezone.utc))


def merge_streams(streams):
    """Newest observation wins; on ties retain the first (snapshot) version."""
    selected, origins, conflicts = {}, {}, []
    for origin, records in streams:
        for record in records:
            record = dict(record)
            aid = record['id']
            previous = selected.get(aid)
            replace = previous is None or timestamp(record) > timestamp(previous)
            if previous and previous.get('content_hash') != record.get('content_hash'):
                conflicts.append({'article_id': aid,
                    'previous_origin': origins[aid], 'incoming_origin': origin,
                    'previous_hash': previous.get('content_hash'),
                    'incoming_hash': record.get('content_hash'),
                    'selected_origin': origin if replace else origins[aid],
                    'selection': 'latest_observation; first_on_tie'})
            if replace:
                selected[aid], origins[aid] = record, origin
    return selected, origins, conflicts


def sqlite_records(path, table):
    if not Path(path).exists():
        return
    if table not in {'articles', 'posts'}:
        raise ValueError('Unsupported record table')
    with sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True) as db:
        for (raw,) in db.execute(f'SELECT record FROM {table}'):
            yield json.loads(raw)


def merged_corpus(snapshot, news_live, telegram_live, extra_news=()):
    snapshot = Path(snapshot).resolve()
    news, news_origins, conflicts = merge_streams([
        ('snapshot_news', jsonl(snapshot / 'data/articles-all.jsonl')),
        ('live_news', sqlite_records(news_live, 'articles'))]+[
        ('additional_news_'+str(i),sqlite_records(path,'articles')) for i,path in enumerate(extra_news)])
    posts, post_origins, post_conflicts = merge_streams([
        ('snapshot_telegram', jsonl(snapshot / 'telegram/telegram-posts.jsonl')),
        ('live_telegram', sqlite_records(telegram_live, 'posts'))])
    if news.keys() & posts.keys():
        raise ValueError('News and Telegram IDs collide')
    for record in news.values():
        record.update(kind='news', ml_export_allowed=True)
    for record in posts.values():
        record.update(kind='telegram_post', language='ru',
            source_name='@' + record['channel'], text_scope='public_preview',
            content_hash=hashlib.sha256((record['title'] + '\n' + record['text']).encode()).hexdigest(),
            ml_export_allowed=False)
    records = sorted([*news.values(), *posts.values()], key=lambda a: a['id'])
    return records, {'snapshot': str(snapshot), 'counts': dict(Counter(a['kind'] for a in records)),
        'selected_origins': dict(Counter([*news_origins.values(), *post_origins.values()])),
        'revision_conflicts': conflicts + post_conflicts,
        'training_policy': 'Only the snapshot training-news.jsonl is the fixed-window ML corpus; catalog includes review records. Telegram is internal analytics only.'}
