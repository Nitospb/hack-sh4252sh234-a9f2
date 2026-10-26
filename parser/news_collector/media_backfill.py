from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import json
import logging
from collections import defaultdict
import time

from lxml import html

from .browser import AccessBlocked, Browser
from .extract import jsonld_articles
from .images import candidates, download_images, merge_images
from .storage import Store

LOG = logging.getLogger(__name__)


def backfill(collector, sources, workers=2, limit=0):
    """Discover from saved DOM, fetch via one source browser context per batch."""
    store = Store(collector.runtime/"news.sqlite3")
    jobs = defaultdict(list)
    offline = 0
    selected = {s.id:s for s in sources}
    prepared = 0
    try:
        rows = store.db.execute("SELECT record FROM articles ORDER BY first_seen_at,id").fetchall()
        indexed = defaultdict(list)
        for row in rows:
            record = json.loads(row[0])
            indexed[record["source_id"]].append(record)
        for source in sources:
            for record in indexed[source.id]:
                if limit and prepared>=limit:
                    break
                tree = html.fromstring(gzip.decompress((collector.runtime/record["raw_html_path"]).read_bytes()))
                ld = next((x for x in jsonld_articles(tree) if x.get("headline")),{})
                images = merge_images(candidates(tree,source,record["canonical_url"],ld),record.get("images",[]),collector.runtime)
                lead_saved = any(x["role"]=="lead" and x["status"]=="saved" for x in images)
                needs_fetch = any(x["status"] not in ("saved","filtered") and (x["role"]!="lead" or not lead_saved) for x in images)
                if not needs_fetch:
                    images, main = download_images(None,collector.runtime,record["canonical_url"],record["title"],images)
                    store.set_images(record["id"],images,main)
                    offline += 1
                    continue
                store.set_images(record["id"],images,record.get("main_image_path"))
                jobs[source.id].append((record,images))
                prepared += 1
    finally:
        store.close()

    def work(source):
        store = Store(collector.runtime/"news.sqlite3")
        result = {"source_id":source.id,"articles":0,"saved_images":0,"failed_images":0}
        try:
            if store.state(source.id)["cooldown_until"]>time.time():
                return {**result,"skipped":"cooldown"}
            if collector.stop.is_set():
                return {**result,"skipped":"stopped"}
            with Browser(collector.runtime/"profiles"/source.id,collector.headless,collector.binary,collector.driver_path) as browser:
                context = jobs[source.id][0][0]["canonical_url"]
                if not collector.robots(browser,store,source,context,{}):
                    return {**result,"skipped":"robots_disallowed"}
                page = collector.paced_read(browser,store,source,context,article=True)
                if not source.accepts(page.url):
                    return {**result,"error":"Article context redirected outside source allowlist"}
                for record,images in jobs[source.id]:
                    if collector.stop.is_set():
                        break
                    images,main = download_images(browser,collector.runtime,record["canonical_url"],record["title"],images,stop=collector.stop)
                    store.set_images(record["id"],images,main)
                    result["articles"] += 1
                    result["saved_images"] += sum(x["status"]=="saved" for x in images)
                    result["failed_images"] += sum(x["status"]=="failed" for x in images)
                    LOG.info("images source=%s saved=%s title=%s",source.id,sum(x["status"]=="saved" for x in images),record["title"][:75])
        except AccessBlocked as exc:
            store.update_state(source.id,cooldown_until=time.time()+1800,last_error=str(exc))
            result["error"] = str(exc)
        except Exception as exc:
            result["error"] = str(exc)
        finally:
            store.close()
        return result
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(work,selected[sid]) for sid in jobs]
        for future in as_completed(futures):
            results.append(future.result())
    return {"prepared":prepared,"already_available_or_no_candidates":offline,"sources":results}
