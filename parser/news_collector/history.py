"""Resumable bounded archive crawl; publication time, not lastmod, defines membership."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import gzip
import io
import json
import logging
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

from lxml import etree, html

from .browser import AccessBlocked, Browser, PageError
from .extract import discover, extract_article, listing_next, url_publication_day
from .images import download_images, merge_images
from .models import digest, normalize_url, utcnow
from .storage import Store
from .source_check import source_fingerprint

LOG = logging.getLogger(__name__)
MAX_XML_BYTES = 52_428_800


def timestamp(value):
    """CLI dates mean UTC midnight; timestamps must carry an explicit offset."""
    value = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        value += "T00:00:00+00:00"
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp requires a timezone; a date alone means UTC midnight")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime

    def __post_init__(self):
        if self.start.tzinfo is None or self.end.tzinfo is None or self.start >= self.end:
            raise ValueError("History requires an aware, nonempty date interval [since, until)")

    def contains(self, value):
        if not value:
            return False
        try:
            return self.start <= timestamp(value) < self.end
        except (TypeError, ValueError):
            return False

    def record(self):
        return {"since": self.start.isoformat(), "until": self.end.isoformat()}


def job_window(runtime, days=None, since=None, until=None):
    """A resumed --days run retains its original bounds, even the next day."""
    path = runtime / "history-job.json"
    previous = json.loads(path.read_text()) if path.exists() else None
    if days is not None and (since is not None or until is not None):
        raise ValueError("Use --days OR --since/--until")
    if days is not None and days < 1:
        raise ValueError("--days must be positive")
    if previous:
        window = Window(timestamp(previous["since"]), timestamp(previous["until"]))
        if since and timestamp(since) != window.start or until and timestamp(until) != window.end:
            raise ValueError("This runtime belongs to a different interval; use a new --runtime")
        if days is not None and previous.get("days") != days:
            raise ValueError("This runtime uses a different --days value; use a new --runtime")
        return window
    if not since and days is None:
        days = 30
    end = timestamp(until) if until else datetime.now(timezone.utc)
    start = timestamp(since) if since else end - timedelta(days=days)
    window = Window(start, end)
    # Keep monitoring and period collection in separate runtimes: done/skipped
    # frontier rows from a different job must not suppress this interval.
    db = runtime / "news.sqlite3"
    if db.exists():
        import sqlite3
        with closing(sqlite3.connect(db)) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if any(connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
                   for table in ("articles", "frontier") if table in tables):
                raise ValueError("History needs a fresh runtime, or an existing history-job.json")
    runtime.mkdir(parents=True, exist_ok=True)
    atomic_json(path, {**window.record(), "days": days, "created_at": utcnow(), "schema_version": 1})
    return window


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def sitemap_entries(data):
    """No entities/network/DTD; cap both compressed and decompressed content.

    Return kind, (loc, publication_date, lastmod) entries. lastmod is only a
    scheduling hint: it never becomes the article's published_at.
    """
    if len(data) > MAX_XML_BYTES:
        raise ValueError("Sitemap exceeds size limit")
    if data.startswith(b"\x1f\x8b"):
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            data = stream.read(MAX_XML_BYTES + 1)
    if len(data) > MAX_XML_BYTES:
        raise ValueError("Decompressed sitemap exceeds size limit")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    root = etree.fromstring(data, parser)
    kind = etree.QName(root).localname
    if kind not in ("sitemapindex", "urlset"):
        raise ValueError("Not a sitemap XML document")
    result = []
    for child in root[:50_000]:
        loc = child.findtext("{*}loc")
        if loc:
            publication = child.findtext("{*}news/{*}publication_date")
            result.append((loc.strip(), publication, child.findtext("{*}lastmod")))
    return kind, result


def page_priority(url, window, lastmod=None):
    """Prefer matching month partitions, without assuming index order is stable."""
    score = 0
    current = window.start.date().replace(day=1)
    while current <= window.end.date():
        y, m = current.year, current.month
        if re.search(rf"{y}[-_/]?{m:02d}(?:\D|$)", url):
            score += 200
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
    if lastmod:
        try:
            if timestamp(lastmod) >= window.start:
                score += 50
        except ValueError:
            pass
    if re.search(r"news|article|post|econom|financ|polit|business", url, re.I):
        score += 20
    if re.search(r"daily|latest|recent|today|news-sitemap|sitemap-news", url, re.I):
        score += 150
    return score


def archive_seeds(source, window):
    urls = list(source.seeds)
    # Include adjacent UTC days because an archive calendar can use local time.
    for template in source.archive_seeds:
        if "{" not in template:
            urls.append(template)
            continue
        day = window.start.date() - timedelta(days=1)
        while day <= window.end.date() + timedelta(days=1):
            urls.append(template.format(date=day.isoformat(), year=day.year,
                                        month=f"{day.month:02d}", day=f"{day.day:02d}"))
            day += timedelta(days=1)
    return list(dict.fromkeys(urls))


def prepare(store):
    store.db.executescript("""
    CREATE TABLE IF NOT EXISTS history_pages (
      source_id TEXT NOT NULL, url TEXT NOT NULL, kind TEXT NOT NULL,
      seed TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 0,
      position INTEGER NOT NULL DEFAULT 0,
      state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
      next_attempt REAL NOT NULL DEFAULT 0, last_error TEXT,
      PRIMARY KEY(source_id,url));
    CREATE INDEX IF NOT EXISTS history_pages_due ON history_pages(source_id,state,next_attempt);
    CREATE TABLE IF NOT EXISTS history_sources (
      source_id TEXT PRIMARY KEY, initialized INTEGER NOT NULL DEFAULT 0,
      fingerprint TEXT,
      status TEXT NOT NULL DEFAULT 'pending', last_error TEXT, updated_at TEXT);
    """)
    for table, column, declaration in (("history_pages", "position", "INTEGER NOT NULL DEFAULT 0"),
                                       ("history_sources", "fingerprint", "TEXT")):
        if column not in {row[1] for row in store.db.execute(f"PRAGMA table_info({table})")}:
            store.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
    store.db.commit()


def enqueue_page(store, source, url, kind, seed=None, priority=0, position=0, reopen=False):
    try:
        url = normalize_url(url)
    except ValueError:
        return
    if not source.allows_host(url) or source.accepts(url):
        return
    with store.db:
        store.db.execute("""INSERT INTO history_pages(source_id,url,kind,seed,priority,position) VALUES (?,?,?,?,?,?)
          ON CONFLICT(source_id,url) DO UPDATE SET priority=MAX(history_pages.priority,excluded.priority),
          position=excluded.position, state=CASE WHEN ? THEN 'pending' ELSE history_pages.state END,
          attempts=CASE WHEN ? THEN 0 ELSE history_pages.attempts END,
          next_attempt=CASE WHEN ? THEN 0 ELSE history_pages.next_attempt END""",
                         (source.id, url, kind, seed or url, priority, position, reopen, reopen, reopen))


def article_priority(url, window, date_hint=None):
    day = url_publication_day(url)
    if not day and date_hint:
        try:
            day = timestamp(date_hint).date()
        except ValueError:
            pass
    if day and window.start.date() - timedelta(days=1) <= day <= window.end.date() + timedelta(days=1):
        # Stable sampling across the discovered interval, rather than consuming
        # only today's high-volume feed before the first monthly checkpoint.
        return 1_000_000 + int(digest(url)[:8], 16) % 100_000
    return 0 if not day else -abs((day - window.start.date()).days) - 1


def enqueue_articles(store, source, urls, window, hints=None, listing=False):
    # URL dates only affect ordering, never replace the page publication date.
    urls = [url for url in dict.fromkeys(urls) if source.accepts(url)]
    priorities = {url: article_priority(url, window, (hints or {}).get(url)) for url in urls}
    if listing:
        priorities = {url: max(priority, 100_000) if priority >= 0 else priority for url, priority in priorities.items()}
    return store.enqueue(source.id, urls, priorities)


def pagination_urls(page, source, seed):
    explicit = listing_next(page, source, seed)
    urls = [explicit] if explicit else []
    tree = html.fromstring(page.html)
    bases = tree.xpath('//base[@href]/@href')
    base = urljoin(page.url, bases[0]) if bases else page.url
    root_path = urlsplit(seed).path.rstrip("/")
    for node in tree.xpath('//a[@href]'):
        label = " ".join(node.text_content().split()).casefold()
        rel = node.get("rel", "").split()
        container = " ".join(node.xpath('ancestor-or-self::*[position()<=3]/@class')).casefold()
        if not ("next" in rel or label in ("далее", "следующая", "следующая →", "next", "older", "older posts", "назад")
                or label.isdecimal() and any(token in container for token in ("pagin", "pager", "pages"))):
            continue
        try:
            url = normalize_url(urljoin(base, node.get("href")))
        except ValueError:
            continue
        path = urlsplit(url).path.rstrip("/")
        inside = path == root_path or path.startswith(root_path + "/")
        if source.allows_host(url) and inside and not source.accepts(url):
            urls.append(url)
    return list(dict.fromkeys(urls))


class History:
    def __init__(self, collector, window, max_pages=80, max_articles=500, defer_images=False):
        if max_pages < 1 or max_articles < 1:
            raise ValueError("History page/article budgets must be positive")
        self.collector, self.window = collector, window
        self.max_pages, self.max_articles = max_pages, max_articles
        self.defer_images = defer_images

    def initialize(self, browser, store, source, cache):
        row = store.db.execute("SELECT initialized,fingerprint FROM history_sources WHERE source_id=?", (source.id,)).fetchone()
        fingerprint = source_fingerprint(source)
        if row and row["initialized"] and row["fingerprint"] == fingerprint:
            return
        reopen = bool(row and row["initialized"])
        for index, seed in enumerate(archive_seeds(source, self.window)):
            enqueue_page(store, source, seed, "listing", priority=1000 if index == 0 else 100, reopen=reopen)
        maps = list(source.sitemap_urls)
        origins = list(dict.fromkeys(urlunsplit((*urlsplit(seed)[:2], "", "", "")) for seed in source.seeds))
        for origin in origins:
            self.collector.robots(browser, store, source, origin + "/", cache)
            maps.extend(cache[origin].site_maps() or [])
        if not maps:
            maps.extend(origin + suffix for origin in origins for suffix in ("/sitemap.xml", "/sitemap_index.xml"))
        for url in maps:
            enqueue_page(store, source, url, "sitemap", priority=300 + page_priority(url, self.window), reopen=reopen)
        with store.db:
            store.db.execute("INSERT INTO history_sources(source_id,initialized,fingerprint) VALUES (?,1,?) ON CONFLICT(source_id) DO UPDATE SET initialized=1,fingerprint=excluded.fingerprint", (source.id, fingerprint))

    def read_map(self, browser, store, source, url):
        state = store.state(source.id)
        import random
        delay = source.min_interval_seconds * random.uniform(1, 1.35)
        if self.collector.stop.wait(max(0, state["last_navigation"] + delay - time.time())):
            raise InterruptedError("History stopped")
        store.update_state(source.id, last_navigation=time.time())
        data = browser.resource_bytes(url, MAX_XML_BYTES)
        path = self.collector.runtime / "sitemaps" / source.id / (digest(url) + ".xml.gz")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if data.startswith(b"\x1f\x8b") else gzip.compress(data, mtime=0))
        return sitemap_entries(data)

    def discover_page(self, browser, store, source, task, cache):
        url = task["url"]
        if not source.allows_host(url):
            return "out_of_scope"
        if not self.collector.robots(browser, store, source, url, cache):
            return "robots_disallowed"
        if task["kind"] == "sitemap":
            kind, entries = self.read_map(browser, store, source, url)
            if kind == "sitemapindex":
                def recency(entry):
                    try:
                        return timestamp(entry[2]).timestamp() if entry[2] else 0
                    except ValueError:
                        return 0
                ordered = list(reversed(entries)) if source.sitemap_reverse else entries
                for position, (loc, _, lastmod) in enumerate(sorted(ordered, key=recency, reverse=True)):
                    enqueue_page(store, source, loc, "sitemap", priority=200 + page_priority(loc, self.window, lastmod), position=position)
            else:
                urls, hints = [], {}
                for loc, publication, lastmod in entries:
                    try:
                        loc = normalize_url(loc)
                    except ValueError:
                        continue
                    # A news publication date with a timezone is usable for
                    # discovery pruning; page metadata still defines membership.
                    if publication:
                        try:
                            stamp = timestamp(publication)
                            if stamp < self.window.start - timedelta(days=1) or stamp >= self.window.end + timedelta(days=1):
                                continue
                        except ValueError:
                            pass
                    urls.append(loc)
                    hints[loc] = publication or lastmod
                enqueue_articles(store, source, urls, self.window, hints)
        else:
            page = self.collector.paced_read(browser, store, source, url)
            if not source.allows_host(page.url):
                raise PageError("Archive redirected outside source host allowlist")
            enqueue_articles(store, source, discover(page, source, limit=5000), self.window, listing=True)
            for next_url in pagination_urls(page, source, task["seed"]):
                enqueue_page(store, source, next_url, "listing", task["seed"], priority=90)
        return "done"

    def article(self, browser, store, source, task, cache):
        if not source.accepts(task["url"]):
            store.skip(source.id, task, "Outside current article allowlist")
            return "out_of_scope"
        if not self.collector.robots(browser, store, source, task["url"], cache):
            store.fail(source.id, task, "robots.txt disallows URL", terminal=True)
            return "robots_disallowed"
        page = self.collector.paced_read(browser, store, source, task["url"], article=True)
        if not source.accepts(page.url):
            raise ValueError("Article redirected outside source allowlist")
        raw_hash = digest(page.html)
        path = self.collector.runtime / "raw" / raw_hash[:2] / (raw_hash + ".html.gz")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(page.html.encode(), mtime=0))
        article = extract_article(page, source, str(path.relative_to(self.collector.runtime)))
        if article.published_at and not self.window.contains(article.published_at):
            store.skip(source.id, task, "Publication outside history interval: " + article.published_at)
            return "outside_period"
        if not article.published_at:
            article.quality_flags.append("history_period_unverified")
        previous = store.db.execute("SELECT record FROM articles WHERE id=?", (digest(article.canonical_url),)).fetchone()
        old_images = json.loads(previous[0]).get("images", []) if previous else []
        article.images = merge_images(article.images, old_images, self.collector.runtime)
        article.main_image_path = next((image["local_path"] for image in article.images if image["status"] == "saved"), None)
        created = store.complete(task, article)
        LOG.info("history saved source=%s dated=%s title=%s", source.id, bool(article.published_at), article.title[:100])
        if not self.defer_images:
            try:
                article.images, article.main_image_path = download_images(
                    browser, self.collector.runtime, article.canonical_url, article.title,
                    article.images, old_images, self.collector.stop)
                store.set_images(digest(article.canonical_url), article.images, article.main_image_path)
            except Exception as exc:
                LOG.warning("History image failure source=%s url=%s: %s", source.id, task["url"], exc)
        return "new" if created else "updated"

    def source_turn(self, source, page_batch=4, article_batch=30):
        if self.collector.stop.is_set():
            return {"source_id": source.id, "pages": 0, "attempted": 0, "status": "interrupted"}
        store = Store(self.collector.runtime / "news.sqlite3")
        result = {"source_id": source.id, "pages": 0, "attempted": 0}
        try:
            if self.collector.stop.is_set():
                result["status"] = "interrupted"
                return result
            if store.state(source.id)["cooldown_until"] > time.time():
                return {**result, "status": "cooldown"}
            with Browser(self.collector.runtime / "profiles" / source.id, self.collector.headless,
                         self.collector.binary, self.collector.driver_path) as browser:
                cache = {}
                self.initialize(browser, store, source, cache)
                for _ in range(page_batch):
                    if self.collector.stop.is_set():
                        break
                    used = store.db.execute("SELECT count(*) FROM history_pages WHERE source_id=? AND state!='pending'", (source.id,)).fetchone()[0]
                    if used >= self.max_pages:
                        break
                    row = store.db.execute("SELECT * FROM history_pages WHERE source_id=? AND state='pending' AND next_attempt<=? ORDER BY priority DESC,position,rowid LIMIT 1", (source.id, time.time())).fetchone()
                    if not row:
                        break
                    task = dict(row)
                    with store.db:
                        store.db.execute("UPDATE history_pages SET attempts=attempts+1 WHERE source_id=? AND url=?", (source.id, task["url"]))
                    try:
                        status = self.discover_page(browser, store, source, task, cache)
                        with store.db:
                            store.db.execute("UPDATE history_pages SET state=?,last_error=NULL WHERE source_id=? AND url=?", (status, source.id, task["url"]))
                        result["pages"] += 1
                    except AccessBlocked:
                        raise
                    except InterruptedError:
                        raise
                    except Exception as exc:
                        attempts = task["attempts"] + 1
                        with store.db:
                            store.db.execute("UPDATE history_pages SET state=?,last_error=?,next_attempt=? WHERE source_id=? AND url=?",
                                             ("failed" if attempts >= 2 else "pending", str(exc)[:500], time.time() + 60 * attempts, source.id, task["url"]))
                        LOG.warning("History discovery source=%s url=%s: %s", source.id, task["url"], exc)
                attempted = store.db.execute("SELECT COALESCE(sum(attempts),0) FROM frontier WHERE source_id=?", (source.id,)).fetchone()[0]
                for _ in range(min(article_batch, max(0, self.max_articles - attempted))):
                    if self.collector.stop.is_set():
                        break
                    task = store.claim(source.id)
                    if not task:
                        break
                    result["attempted"] += 1
                    try:
                        status = self.article(browser, store, source, task, cache)
                        result[status] = result.get(status, 0) + 1
                    except AccessBlocked as exc:
                        store.fail(source.id, task, exc, blocked=True)
                        raise
                    except InterruptedError:
                        store.fail(source.id, task, "History interrupted")
                        raise
                    except Exception as exc:
                        store.fail(source.id, task, exc)
                        result["failed"] = result.get("failed", 0) + 1
                        LOG.warning("History article source=%s url=%s: %s", source.id, task["url"], exc)
            result["status"] = "processed"
        except AccessBlocked as exc:
            store.update_state(source.id, cooldown_until=time.time() + 1800, last_error=str(exc))
            result.update(status="blocked", error=str(exc)[:500])
        except InterruptedError:
            result["status"] = "interrupted"
        except Exception as exc:
            store.update_state(source.id, cooldown_until=time.time() + 300, last_error=str(exc))
            result.update(status="error", error=str(exc)[:500])
        finally:
            with store.db:
                store.db.execute("INSERT INTO history_sources(source_id,status,last_error,updated_at) VALUES (?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET status=excluded.status,last_error=excluded.last_error,updated_at=excluded.updated_at",
                                 (source.id, result.get("status", "error"), result.get("error"), utcnow()))
            store.close()
        return result

    def eligible(self, store, source):
        row = store.db.execute("SELECT initialized,status,fingerprint FROM history_sources WHERE source_id=?", (source.id,)).fetchone()
        if row and row["status"] in ("blocked", "error"):
            return False
        if not row or not row["initialized"] or row["fingerprint"] != source_fingerprint(source):
            return True
        used = store.db.execute("SELECT count(*) FROM history_pages WHERE source_id=? AND state!='pending'", (source.id,)).fetchone()[0]
        pages = used < self.max_pages and store.db.execute("SELECT 1 FROM history_pages WHERE source_id=? AND state='pending' LIMIT 1", (source.id,)).fetchone()
        attempts = store.db.execute("SELECT COALESCE(sum(attempts),0) FROM frontier WHERE source_id=?", (source.id,)).fetchone()[0]
        articles = attempts < self.max_articles and store.db.execute("SELECT 1 FROM frontier WHERE source_id=? AND state IN ('pending','retry','fetching') LIMIT 1", (source.id,)).fetchone()
        return bool(pages or articles)

    def ready(self, store, source):
        if store.state(source.id)["cooldown_until"] > time.time():
            return False
        row = store.db.execute("SELECT initialized,fingerprint FROM history_sources WHERE source_id=?", (source.id,)).fetchone()
        if not row or not row["initialized"] or row["fingerprint"] != source_fingerprint(source):
            return True
        used = store.db.execute("SELECT count(*) FROM history_pages WHERE source_id=? AND state!='pending'", (source.id,)).fetchone()[0]
        pages = used < self.max_pages and store.db.execute("SELECT 1 FROM history_pages WHERE source_id=? AND state='pending' AND next_attempt<=? LIMIT 1", (source.id, time.time())).fetchone()
        attempts = store.db.execute("SELECT COALESCE(sum(attempts),0) FROM frontier WHERE source_id=?", (source.id,)).fetchone()[0]
        return bool(pages or attempts < self.max_articles and store.has_due_tasks(source.id))

    def report(self, store, sources, target):
        return write_history_report(store, self.collector.runtime, self.window, sources, target,
                                    self.max_pages, self.max_articles)

    def run(self, sources, workers=2, target=10_000, rounds=0):
        store = Store(self.collector.runtime / "news.sqlite3")
        prepare(store)
        store.close()
        round_number = 0
        while not self.collector.stop.is_set():
            store = Store(self.collector.runtime / "news.sqlite3")
            try:
                eligible = [source for source in sources if self.eligible(store, source)]
                scheduling = {row["source_id"]: dict(row) for row in store.db.execute("SELECT source_id,initialized,updated_at FROM history_sources")}
                eligible.sort(key=lambda source: (
                    bool(scheduling.get(source.id, {}).get("initialized")),
                    (scheduling.get(source.id, {}).get("updated_at") or "") if scheduling.get(source.id, {}).get("initialized") else ""))
                due = [source for source in eligible if self.ready(store, source)]
                report = self.report(store, sources, target)
            finally:
                store.close()
            all_visited = all(row["status"] != "pending" for row in report["sources"])
            if not eligible or rounds and round_number >= rounds or report["target_reached"] and all_visited:
                return report
            if not due:
                if self.collector.stop.wait(30):
                    break
                continue
            round_number += 1
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(self.source_turn, source) for source in due]
                for future in as_completed(futures):
                    result = future.result()
                    if self.collector.stop.is_set() and result["status"] == "interrupted" and not result["pages"] and not result["attempted"]:
                        continue
                    LOG.info("History turn %s", json.dumps(result, ensure_ascii=False))
                    store = Store(self.collector.runtime / "news.sqlite3")
                    try:
                        report = self.report(store, sources, target)
                    finally:
                        store.close()
            # Retries keep their backoff. Polling cannot create a hot loop.
            self.collector.stop.wait(10)
        store = Store(self.collector.runtime / "news.sqlite3")
        try:
            return self.report(store, sources, target)
        finally:
            store.close()


def write_history_report(store, runtime, window, sources, target=10_000, max_pages=None, max_articles=None):
    counts = {}
    unique_texts = set()
    days = {}
    totals = {"period_articles": 0, "undated_articles": 0, "accessible_excerpts": 0, "training_articles": 0, "duplicate_texts": 0}
    paths = {name: runtime / name for name in ("period-news.jsonl", "training-news.jsonl", "undated-news.jsonl")}
    streams = {name: path.with_suffix(".jsonl.tmp").open("w", encoding="utf-8") for name, path in paths.items()}
    try:
        for row in store.db.execute("SELECT record,first_seen_at,last_seen_at FROM articles ORDER BY first_seen_at,id"):
            record = json.loads(row[0])
            record.update(first_seen_at=row[1], last_seen_at=row[2])
            source_counts = counts.setdefault(record["source_id"], {"period_articles": 0, "undated_articles": 0, "training_articles": 0})
            encoded = json.dumps(record, ensure_ascii=False) + "\n"
            if not record.get("published_at"):
                totals["undated_articles"] += 1
                source_counts["undated_articles"] += 1
                streams["undated-news.jsonl"].write(encoded)
            elif window.contains(record["published_at"]):
                totals["period_articles"] += 1
                source_counts["period_articles"] += 1
                day = timestamp(record["published_at"]).date().isoformat()
                days[day] = days.get(day, 0) + 1
                streams["period-news.jsonl"].write(encoded)
                if record.get("text_scope") == "accessible_excerpt":
                    totals["accessible_excerpts"] += 1
                elif record["text_hash"] in unique_texts:
                    totals["duplicate_texts"] += 1
                else:
                    unique_texts.add(record["text_hash"])
                    totals["training_articles"] += 1
                    source_counts["training_articles"] += 1
                    streams["training-news.jsonl"].write(encoded)
    finally:
        for stream in streams.values():
            stream.close()
    for name, path in paths.items():
        path.with_suffix(".jsonl.tmp").replace(path)
    states = {row["source_id"]: dict(row) for row in store.db.execute("SELECT * FROM history_sources")}
    rows = []
    for source in sources:
        row = {"source_id": source.id, "name": source.name, "publisher_country": source.publisher_country,
               **counts.get(source.id, {"period_articles": 0, "undated_articles": 0, "training_articles": 0}),
               **{key: value for key, value in states.get(source.id, {}).items() if key not in ("source_id", "initialized")}}
        row["status"] = row.get("status", "pending")
        row["pages"] = {r[0]: r[1] for r in store.db.execute("SELECT state,count(*) FROM history_pages WHERE source_id=? GROUP BY state", (source.id,))}
        row["queue"] = {r[0]: r[1] for r in store.db.execute("SELECT state,count(*) FROM frontier WHERE source_id=? GROUP BY state", (source.id,))}
        row["article_attempts"] = store.db.execute("SELECT COALESCE(sum(attempts),0) FROM frontier WHERE source_id=?", (source.id,)).fetchone()[0]
        page_count = sum(count for state, count in row["pages"].items() if state != "pending")
        row["coverage_status"] = (row["status"] if row["status"] in ("pending", "error", "blocked", "interrupted")
                                  else "discovery_budget_reached" if max_pages and page_count >= max_pages and row["pages"].get("pending")
                                  else "article_budget_reached" if max_articles and row["article_attempts"] >= max_articles and any(row["queue"].get(state) for state in ("pending", "retry", "fetching"))
                                  else "more_candidates" if row["pages"].get("pending") or any(row["queue"].get(state) for state in ("pending", "retry", "fetching"))
                                  else "discovered_queue_exhausted")
        rows.append(row)
    report = {"updated_at": utcnow(), **window.record(), **totals, "target": target,
              "target_reached": totals["training_articles"] >= target,
              "limits": {"pages_per_source": max_pages, "article_attempts_per_source": max_articles},
              "visited_sources": sum(row["status"] != "pending" for row in rows),
              "sources_with_period_articles": sum(row["period_articles"] > 0 for row in rows),
              "articles_by_day_utc": dict(sorted(days.items())), "sources": rows,
              "coverage_note": "Bounded discovery, not a guarantee of every article on a site. Unknown dates and paid excerpts do not count toward the training target. Exact text deduplication is not semantic deduplication."}
    atomic_json(runtime / "history-report.json", report)
    lines = ["# Сбор публикаций за период", "", f"Интервал UTC: [{report['since']}, {report['until']}).",
             f"Статей с датой: {totals['period_articles']}; без даты: {totals['undated_articles']}; обучающая выборка: {totals['training_articles']} / {target}.",
             "", "Обучающая выборка исключает неизвестные даты, известные платные фрагменты и точные дубли текста. Семантическая дедупликация не выполнялась. Полнота архива сайта не гарантируется.",
             "", "| Источник | Статус | За период | Без даты | В обучении | Страницы | Очередь | Ошибка |",
             "|---|---|---:|---:|---:|---|---|---|"]
    for row in rows:
        error = str(row.get("last_error") or "").replace("|", "/").replace("\n", " ")[:160]
        lines.append(f"| {row['name']} | {row['coverage_status']} | {row['period_articles']} | {row['undated_articles']} | {row['training_articles']} | {row['pages']} | {row['queue']} | {error} |")
    path = runtime / "history-report.md"
    temporary = path.with_suffix(".md.tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(path)
    return report
