from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import signal
import threading

from .doctor import diagnose
from .models import load_sources
from .runner import Collector
from .storage import Store
from .report import write_report


@contextmanager
def runtime_lock(runtime):
    """Kernel lock is released on crash; never delete another process's lock."""
    import fcntl
    runtime.mkdir(parents=True,exist_ok=True)
    with (runtime/"collector.lock").open("a+") as stream:
        try:
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another collector/doctor is using this runtime. Use another --runtime directory.") from exc
        try:
            yield
        finally:
            fcntl.flock(stream,fcntl.LOCK_UN)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Selenium + real Chrome news collector (macOS/Linux)")
    parser.add_argument("--runtime",type=Path,default=Path("runtime"))
    parser.add_argument("--config",type=Path,default=Path("config/sources.json"))
    parser.add_argument("--headless",action="store_true",help="Chrome without a visible window; Windows UA is always automatic")
    parser.add_argument("--chrome-binary",default=os.environ.get("CHROME_BINARY"))
    parser.add_argument("--chromedriver",default=os.environ.get("CHROMEDRIVER"))
    sub = parser.add_subparsers(dest="command",required=True)
    sub.add_parser("doctor",help="Launch Chrome; test HTTP and JS identity on a local server")
    sub.add_parser("sources",help="List configured sources")
    for name in ("collect","run"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--sources",nargs="*",default=[])
        cmd.add_argument("--workers",type=int,choices=range(1,5),default=2)
        cmd.add_argument("--max-articles",type=int,default=30,help="Maximum article attempts per source per cycle, additionally capped by source budget")
        cmd.add_argument("--max-links",type=int,default=300,help="Maximum article URLs per listing page (bounded pagination per source)")
    sub.add_parser("stats")
    cmd = sub.add_parser("reextract",help="Reprocess saved HTML locally after updating an extractor")
    cmd.add_argument("--source",required=True)
    sub.add_parser("audit",help="Validate/reextract all saved DOM; quarantine invalid records without deleting their raw data")
    cmd = sub.add_parser("images",help="Backfill article images from saved DOM using Chrome")
    cmd.add_argument("--sources",nargs="*",default=[])
    cmd.add_argument("--workers",type=int,choices=range(1,5),default=2)
    cmd.add_argument("--limit",type=int,default=0,help="Maximum articles needing downloads; 0 means all")
    cmd = sub.add_parser("check-sources",help="Check current article samples, without archive crawling or image downloads")
    cmd.add_argument("--sources",nargs="*",default=[])
    cmd.add_argument("--workers",type=int,choices=range(1,5),default=2)
    cmd.add_argument("--max-articles",type=int,default=2,help="Required distinct canonical sample articles per source (1–5)")
    cmd.add_argument("--max-links",type=int,default=80)
    cmd.add_argument("--resume",action="store_true")
    cmd = sub.add_parser("export")
    cmd.add_argument("--output",type=Path)
    cmd.add_argument("--max-age-days",type=int)
    cmd.add_argument("--topics",nargs="*",default=[])
    cmd.add_argument("--full-text-only",action="store_true",help="Exclude known paid excerpts; completeness of remaining text is not certified")
    cmd.add_argument("--require-date",action="store_true")
    cmd = sub.add_parser("report",help="Write per-source coverage, failures and example article links")
    cmd.add_argument("--output",type=Path)
    cmd = sub.add_parser("retry",help="Explicitly requeue failed or blocked articles after inspecting the cause")
    cmd.add_argument("--source",required=True)
    cmd.add_argument("--include-done",action="store_true",help="Also revisit saved articles to record updated versions")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
    try:
        if args.command == "sources":
            config = json.loads(args.config.read_text())
            print(json.dumps([{k:s[k] for k in ("id","name","enabled")} for s in config["sources"]],ensure_ascii=False,indent=2))
            return 0
        args.runtime = args.runtime.resolve()
        args.runtime.mkdir(parents=True,exist_ok=True)
        if args.command == "doctor":
            with runtime_lock(args.runtime):
                report = diagnose(args.runtime,args.headless,args.chrome_binary,args.chromedriver)
            print(json.dumps(report,ensure_ascii=False,indent=2))
            return 0 if report["ok"] else 1
        if args.command == "check-sources":
            from .source_check import check_sources
            if not 1<=args.max_articles<=5 or args.max_links<1:
                raise ValueError("Source check requires 1–5 sample articles and positive max-links")
            ids = args.sources or [source["id"] for source in json.loads(args.config.read_text())["sources"]]
            sources = load_sources(args.config,ids)
            stop = threading.Event()
            signal.signal(signal.SIGINT,lambda *_:stop.set())
            signal.signal(signal.SIGTERM,lambda *_:stop.set())
            collector = Collector(args.runtime,args.headless,args.chrome_binary,args.chromedriver,stop)
            with runtime_lock(args.runtime):
                report = check_sources(collector,sources,args.workers,args.max_articles,args.max_links,args.resume)
            print(json.dumps({key:value for key,value in report.items() if key!="sources"},ensure_ascii=False,indent=2))
            return 0 if all(row["status"]=="passed" and len(row["samples"])>=args.max_articles for row in report["sources"] if row["source_id"] in ids) else 1
        if args.command == "images":
            from .media_backfill import backfill
            if args.limit<0:
                raise ValueError("Image limit must be non-negative")
            sources = load_sources(args.config,args.sources)
            stop = threading.Event()
            signal.signal(signal.SIGINT,lambda *_:stop.set())
            signal.signal(signal.SIGTERM,lambda *_:stop.set())
            collector = Collector(args.runtime,args.headless,args.chrome_binary,args.chromedriver,stop)
            with runtime_lock(args.runtime):
                result = backfill(collector,sources,args.workers,args.limit)
                snapshot = Store(args.runtime/"news.sqlite3")
                try:
                    snapshot.export(args.runtime/"articles.jsonl")
                    snapshot.export(args.runtime/"financial-news.jsonl",max_age_days=14,topics=("finance","economy"))
                    snapshot.export(args.runtime/"finance-politics-news.jsonl",max_age_days=14,topics=("finance","economy","politics"))
                    write_report(snapshot,args.config,args.runtime/"coverage.md")
                finally:
                    snapshot.close()
                (args.runtime/"last-images.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return 1 if any(s.get("error") for s in result["sources"]) else 0
        if args.command in ("collect","run"):
            if args.max_articles < 1 or args.max_links < 1:
                raise ValueError("Limits must be positive")
            sources = load_sources(args.config,args.sources)
            stop = threading.Event()
            signal.signal(signal.SIGINT,lambda *_:stop.set())
            signal.signal(signal.SIGTERM,lambda *_:stop.set())
            collector = Collector(args.runtime,args.headless,args.chrome_binary,args.chromedriver,stop)
            with runtime_lock(args.runtime):
                # Bootstrap schema before worker connections run DDL concurrently.
                Store(args.runtime/"news.sqlite3").close()
                while not stop.is_set():
                    result = collector.cycle(sources,args.workers,args.max_articles,args.max_links)
                    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
                    report_path = args.runtime/"last-collection.json"
                    report_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
                    snapshot = Store(args.runtime/"news.sqlite3")
                    try:
                        snapshot.export(args.runtime/"articles.jsonl")
                        snapshot.export(args.runtime/"financial-news.jsonl",max_age_days=14,topics=("finance","economy"))
                        snapshot.export(args.runtime/"finance-politics-news.jsonl",max_age_days=14,topics=("finance","economy","politics"))
                        write_report(snapshot,args.config,args.runtime/"coverage.md")
                    finally:
                        snapshot.close()
                    if args.command == "collect":
                        return 1 if any(r.get("failed") or r.get("blocked") or r.get("error") or r.get("seed_errors") for r in result) else 0
                    stop.wait(30)
            return 0
        store = Store(args.runtime/"news.sqlite3")
        try:
            if args.command == "stats":
                print(json.dumps(store.stats(),ensure_ascii=False,indent=2))
            elif args.command == "export":
                if args.max_age_days is not None and args.max_age_days < 1:
                    raise ValueError("max-age-days must be positive")
                output = args.output or args.runtime/"articles.jsonl"
                count = store.export(output,args.max_age_days,args.topics,args.full_text_only,args.require_date)
                print(json.dumps({"articles":count,"output":str(output)},ensure_ascii=False))
            elif args.command == "report":
                output = args.output or args.runtime/"coverage.md"
                report = write_report(store,args.config,output)
                print(json.dumps({"articles":report["articles"],"sources_with_articles":report["sources_with_articles"],"output":str(output)},ensure_ascii=False))
            elif args.command == "retry":
                load_sources(args.config,[args.source])
                with runtime_lock(args.runtime),store.db:
                    states = "('failed','blocked','retry','done')" if args.include_done else "('failed','blocked','retry')"
                    changed = store.db.execute(f"UPDATE frontier SET state='pending',attempts=0,next_attempt=0,last_error=NULL WHERE source_id=? AND state IN {states}",(args.source,)).rowcount
                    store.db.execute("UPDATE source_state SET cooldown_until=0,last_error=NULL WHERE source_id=?",(args.source,))
                print(json.dumps({"requeued":changed,"source":args.source}))
            elif args.command in ("reextract","audit"):
                import gzip
                from dataclasses import replace
                from .browser import Page
                from .extract import extract_article
                from .extract import ExtractionError
                ids = [s["id"] for s in json.loads(args.config.read_text())["sources"]]
                sources = {s.id:s for s in load_sources(args.config,ids if args.command == "audit" else [args.source])}
                updated = 0
                rejected = []
                with runtime_lock(args.runtime):
                    rows = store.db.execute("SELECT record FROM articles").fetchall()
                    if args.command == "audit":
                        rows += store.db.execute("SELECT record FROM quarantined_articles").fetchall()
                    for row in rows:
                        record = json.loads(row[0])
                        if record["source_id"] not in sources:
                            continue
                        source = sources[record["source_id"]]
                        markup = gzip.decompress((args.runtime/record["raw_html_path"]).read_bytes()).decode("utf-8")
                        page = Page(record["url"],record["canonical_url"],record["title"],markup,"",200)
                        try:
                            article = replace(extract_article(page,source,record["raw_html_path"]),fetched_at=record["fetched_at"])
                            from .images import merge_images,write_manifest
                            article.images = merge_images(article.images,record.get("images",[]),args.runtime)
                            article.main_image_path = next((x["local_path"] for x in article.images if x["status"]=="saved"),None)
                            store.complete({"url":record["url"]},article)
                            write_manifest(args.runtime,article.canonical_url,article.title,article.images,article.main_image_path)
                            updated += 1
                        except (ExtractionError,ValueError) as exc:
                            rejected.append({"url":record["url"],"error":str(exc)})
                            if args.command == "audit":
                                store.quarantine(record,exc)
                    store.export(args.runtime/"articles.jsonl")
                    write_report(store,args.config,args.runtime/"coverage.md")
                print(json.dumps({"reextracted":updated,"rejected":rejected},ensure_ascii=False))
        finally:
            store.close()
        return 0
    except Exception as exc:
        logging.error("%s: %s",type(exc).__name__,exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
