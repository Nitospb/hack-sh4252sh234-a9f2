from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time

from .models import Article, utcnow, image_status


class Store:
    """One connection per worker; claims and writes are transactional."""
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS frontier (
          source_id TEXT NOT NULL, url TEXT NOT NULL, discovered_at TEXT NOT NULL,
          state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
          next_attempt REAL NOT NULL DEFAULT 0, lease_until REAL NOT NULL DEFAULT 0,
          last_error TEXT, PRIMARY KEY(source_id,url));
        CREATE INDEX IF NOT EXISTS frontier_due ON frontier(source_id,state,next_attempt);
        CREATE TABLE IF NOT EXISTS articles (
          id TEXT PRIMARY KEY, canonical_url TEXT UNIQUE NOT NULL,
          source_id TEXT NOT NULL, first_seen_at TEXT NOT NULL,
          last_seen_at TEXT NOT NULL, content_hash TEXT NOT NULL, record TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS articles_hash ON articles(content_hash);
        CREATE TABLE IF NOT EXISTS revisions (
          article_id TEXT NOT NULL, content_hash TEXT NOT NULL, fetched_at TEXT NOT NULL,
          record TEXT NOT NULL, PRIMARY KEY(article_id,content_hash));
        CREATE TABLE IF NOT EXISTS source_state (
          source_id TEXT PRIMARY KEY, next_discovery REAL NOT NULL DEFAULT 0,
          cooldown_until REAL NOT NULL DEFAULT 0, last_navigation REAL NOT NULL DEFAULT 0,
          last_success TEXT, last_error TEXT);
        CREATE TABLE IF NOT EXISTS runs (
          id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
          source_id TEXT NOT NULL, result TEXT);
        CREATE TABLE IF NOT EXISTS quarantined_articles (
          id TEXT PRIMARY KEY, source_id TEXT NOT NULL, reason TEXT NOT NULL,
          record TEXT NOT NULL, quarantined_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS article_images (
          article_id TEXT NOT NULL, image_id TEXT NOT NULL, position INTEGER NOT NULL,
          record TEXT NOT NULL, PRIMARY KEY(article_id,image_id));
        """)
        columns = {r[1] for r in self.db.execute("PRAGMA table_info(frontier)")}
        if "priority" not in columns:
            self.db.execute("ALTER TABLE frontier ADD COLUMN priority INTEGER NOT NULL DEFAULT 0")
            self.db.commit()

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.rollback()
            raise
        else:
            self.db.commit()

    def state(self, source_id):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO source_state(source_id) VALUES (?)", (source_id,))
        return dict(self.db.execute("SELECT * FROM source_state WHERE source_id=?",(source_id,)).fetchone())

    def update_state(self, source_id, **fields):
        allowed = {"next_discovery", "cooldown_until", "last_navigation", "last_success", "last_error"}
        if not fields or set(fields) - allowed:
            raise ValueError("Invalid source state fields")
        self.state(source_id)
        with self.db:
            self.db.execute("UPDATE source_state SET " + ",".join(f"{k}=?" for k in fields) + " WHERE source_id=?", (*fields.values(),source_id))

    def enqueue(self, source_id, urls, priorities=None):
        count = 0
        with self.db:
            for url in urls:
                priority = (priorities or {}).get(url, 0)
                count += self.db.execute("INSERT OR IGNORE INTO frontier(source_id,url,discovered_at,priority) VALUES (?,?,?,?)",
                                         (source_id,url,utcnow(),priority)).rowcount
                if priorities:
                    self.db.execute("UPDATE frontier SET priority=MAX(priority,?) WHERE source_id=? AND url=?", (priority,source_id,url))
        return count

    def claim(self, source_id):
        stamp = time.time()
        with self.transaction():
            # Recover interrupted work only after the lease expires.
            self.db.execute("UPDATE frontier SET state='pending' WHERE source_id=? AND state='fetching' AND lease_until<?", (source_id,stamp))
            row = self.db.execute("SELECT * FROM frontier WHERE source_id=? AND state IN ('pending','retry') AND next_attempt<=? ORDER BY priority DESC,discovered_at,url LIMIT 1", (source_id,stamp)).fetchone()
            if row:
                self.db.execute("UPDATE frontier SET state='fetching',attempts=attempts+1,lease_until=? WHERE source_id=? AND url=?", (stamp+180,source_id,row["url"]))
                return {**dict(row),"attempts": row["attempts"]+1}
        return None

    def has_due_tasks(self,source_id):
        stamp = time.time()
        return self.db.execute("SELECT 1 FROM frontier WHERE source_id=? AND ((state IN ('pending','retry') AND next_attempt<=?) OR (state='fetching' AND lease_until<?)) LIMIT 1",(source_id,stamp,stamp)).fetchone() is not None

    def fail(self, source_id, task, error, terminal=False, blocked=False):
        state = "blocked" if blocked else "failed" if terminal or task["attempts"] >= 3 else "retry"
        with self.db:
            self.db.execute("UPDATE frontier SET state=?,last_error=?,next_attempt=?,lease_until=0 WHERE source_id=? AND url=?",
                            (state,str(error)[:2000],time.time()+min(3600,60*2**task["attempts"]),source_id,task["url"]))

    def skip(self, source_id, task, reason):
        with self.db:
            self.db.execute("UPDATE frontier SET state='skipped',last_error=?,lease_until=0 WHERE source_id=? AND url=?", (reason,source_id,task["url"]))

    def quarantine(self, record, reason):
        with self.transaction():
            self.db.execute("INSERT OR REPLACE INTO quarantined_articles VALUES (?,?,?,?,?)", (record["id"],record["source_id"],str(reason),json.dumps(record,ensure_ascii=False),utcnow()))
            self.db.execute("DELETE FROM articles WHERE id=?",(record["id"],))
            self.db.execute("DELETE FROM article_images WHERE article_id=?",(record["id"],))
            self.db.execute("UPDATE frontier SET state='failed',last_error=? WHERE source_id=? AND url=?", ("Validation: "+str(reason),record["source_id"],record["url"]))

    def complete(self, task, article: Article):
        record = article.record()
        encoded = json.dumps(record,ensure_ascii=False)
        with self.transaction():
            exists = self.db.execute("SELECT 1 FROM articles WHERE id=?",(record["id"],)).fetchone()
            self.db.execute("""INSERT INTO articles VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
              last_seen_at=excluded.last_seen_at,content_hash=excluded.content_hash,record=excluded.record""",
              (record["id"],article.canonical_url,article.source_id,article.fetched_at,article.fetched_at,record["content_hash"],encoded))
            self.db.execute("INSERT OR IGNORE INTO revisions VALUES (?,?,?,?)",(record["id"],record["content_hash"],article.fetched_at,encoded))
            self.db.execute("DELETE FROM quarantined_articles WHERE id=?",(record["id"],))
            self._write_images(record["id"],record.get("images",[]))
            self.db.execute("UPDATE frontier SET state='done',last_error=NULL,lease_until=0 WHERE source_id=? AND url=?", (article.source_id,task["url"]))
        return not exists

    def _write_images(self, article_id, images):
        self.db.execute("DELETE FROM article_images WHERE article_id=?",(article_id,))
        self.db.executemany("INSERT INTO article_images VALUES (?,?,?,?)",[(article_id,x["id"],index,json.dumps(x,ensure_ascii=False)) for index,x in enumerate(images)])

    def set_images(self, article_id, images, main):
        with self.transaction():
            row = self.db.execute("SELECT record FROM articles WHERE id=?",(article_id,)).fetchone()
            if not row:
                raise ValueError("Article no longer exists")
            record = json.loads(row[0])
            record.update(images=images,main_image_path=main)
            record["images_status"] = image_status(images)
            encoded = json.dumps(record,ensure_ascii=False)
            self.db.execute("UPDATE articles SET record=? WHERE id=?",(encoded,article_id))
            self.db.execute("UPDATE revisions SET record=? WHERE article_id=? AND content_hash=?",(encoded,article_id,record["content_hash"]))
            self._write_images(article_id,images)

    def stats(self):
        return {"articles": self.db.execute("SELECT count(*) FROM articles").fetchone()[0],
                "revisions": self.db.execute("SELECT count(*) FROM revisions").fetchone()[0],
                "frontier": [dict(r) for r in self.db.execute("SELECT source_id,state,count(*) AS count FROM frontier GROUP BY source_id,state")],
                "sources": [dict(r) for r in self.db.execute("SELECT * FROM source_state")]}

    def export(self, output: Path, max_age_days=None, topics=(), full_text_only=False, require_date=False):
        from datetime import datetime, timezone, timedelta
        output.parent.mkdir(parents=True,exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        count = 0
        with temporary.open("w",encoding="utf-8") as stream:
            for row in self.db.execute("SELECT record,first_seen_at,last_seen_at FROM articles ORDER BY first_seen_at,id"):
                record = json.loads(row[0])
                date = record.get("published_at")
                if require_date and not date:
                    continue
                if max_age_days and date:
                    stamp = datetime.fromisoformat(date)
                    now = datetime.now(timezone.utc)
                    if stamp < now-timedelta(days=max_age_days) or stamp > now+timedelta(days=2):
                        continue
                if topics and not set(topics).intersection(record.get("topics",[])):
                    continue
                if full_text_only and record.get("text_scope") == "accessible_excerpt":
                    continue
                record.update(first_seen_at=row[1],last_seen_at=row[2])
                stream.write(json.dumps(record,ensure_ascii=False)+"\n")
                count += 1
        temporary.replace(output)
        return count
