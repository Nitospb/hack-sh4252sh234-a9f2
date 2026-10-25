from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import logging
from pathlib import Path
import random
import threading
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from selenium.common.exceptions import InvalidSessionIdException, WebDriverException

from .browser import AccessBlocked, Browser, PageError
from .extract import ExtractionError, discover, extract_article, listing_next, url_publication_day
from .models import Source, digest, utcnow
from .topics import classify
from .storage import Store
from .images import download_images,merge_images

LOG = logging.getLogger(__name__)


class Collector:
    def __init__(self, runtime: Path, headless=False, binary=None, driver_path=None, stop=None):
        self.runtime = runtime
        self.headless,self.binary,self.driver_path = headless,binary,driver_path
        self.stop = stop or threading.Event()

    def paced_read(self,browser,store,source,url,article=False,check_access=True):
        state = store.state(source.id)
        delay = source.min_interval_seconds + random.uniform(0,source.min_interval_seconds*.35)
        wait = max(0,state["last_navigation"]+delay-time.time())
        if self.stop.wait(wait):
            raise InterruptedError("Collector stopped")
        store.update_state(source.id,last_navigation=time.time())
        kwargs = {"article":article,"check_access":check_access}
        if check_access and not article and source.listing_scrolls:
            kwargs["scrolls"] = source.listing_scrolls
        page = browser.read(url,**kwargs)
        if check_access and not article and not discover(page,source,limit=1) and hasattr(browser,"wait_for_listing"):
            page = browser.wait_for_listing(page,source)
        return page

    def robots(self,browser,store,source,url,cache):
        p = urlsplit(url)
        origin = urlunsplit((p.scheme,p.netloc,"","",""))
        if origin not in cache:
            page = self.paced_read(browser,store,source,origin+"/robots.txt",check_access=False)
            if page.status in (401,403,429) or "just a moment" in page.title.casefold():
                raise AccessBlocked("robots.txt access restricted; source paused")
            if page.status and page.status >= 500:
                raise PageError(f"robots.txt unavailable: {page.status}")
            parser = RobotFileParser()
            if page.status in (404,410):
                parser.parse([])
            elif "<html" in page.html.lower() and not any(x in page.text.casefold() for x in ("user-agent:","disallow:","allow:","sitemap:")):
                # Chrome wraps plaintext in HTML; require a <pre> to distinguish it
                # from an unrelated soft-404 or a challenge HTML document.
                if "<pre" not in page.html.lower():
                    raise PageError("robots.txt did not return a recognizable text document")
                parser.parse(page.text.splitlines())
            else:
                parser.parse(page.text.splitlines())
            cache[origin] = parser
        parser = cache[origin]
        user_agent = browser.identity["userAgent"]
        crawl_delay = parser.crawl_delay(user_agent)
        if crawl_delay:
            wait = max(0,store.state(source.id)["last_navigation"]+crawl_delay-time.time())
            if self.stop.wait(wait):
                raise InterruptedError("Collector stopped")
        return parser.can_fetch(user_agent,url)

    def collect_source(self,browser,store,source,max_articles,max_links):
        result = {"source_id":source.id,"discovered":0,"attempted":0,"saved":0,"new":0,
                  "failed":0,"blocked":0,"robots_disallowed":0,"stale":0,"stale_links":0,"out_of_scope":0,"seed_errors":[],"seed_pages":0}
        state = store.state(source.id)
        if state["cooldown_until"] > time.time():
            return {**result,"skipped":"cooldown","until":state["cooldown_until"]}
        run_id = store.db.execute("INSERT INTO runs(started_at,source_id) VALUES (?,?)",(utcnow(),source.id)).lastrowid
        store.db.commit()
        cache = {}
        try:
            if state["next_discovery"] <= time.time():
                found = []
                seed_urls = set()
                priorities = {}
                for seed_index, seed in enumerate(source.seeds):
                    if self.stop.is_set():
                        raise InterruptedError("Collector stopped")
                    url = seed
                    for _ in range(source.listing_pages):
                        if url in seed_urls:
                            break
                        seed_urls.add(url)
                        try:
                            if not self.robots(browser,store,source,url,cache):
                                result["robots_disallowed"] += 1
                                break
                            page = self.paced_read(browser,store,source,url)
                            if not source.allows_host(page.url):
                                raise PageError("Seed redirected outside source allowlist")
                            result["seed_pages"] += 1
                            links = discover(page,source,limit=max_links)
                            if not links:
                                browser.diagnostic(self.runtime/"diagnostics",source.id+"-listing")
                            # Recent discovery wins over an old backlog. All sections
                            # enter the queue before the overall processing budget.
                            for rank, link in enumerate(links):
                                day = url_publication_day(link)
                                today = datetime.now(timezone.utc).date()
                                if day and day < today-timedelta(days=source.max_age_days+1):
                                    result["stale_links"] += 1
                                    continue
                                found.append(link)
                                _, score = classify(link, "", "")
                                priority = (day or today).toordinal()*100000 + (len(source.seeds)-seed_index)*2000 + max(0,1000-rank) + score
                                priorities[link] = max(priorities.get(link,0),priority)
                            url = listing_next(page,source,seed)
                            if not url:
                                break
                        except (PageError,ExtractionError,WebDriverException,ValueError) as exc:
                            if isinstance(exc,(AccessBlocked,InvalidSessionIdException)):
                                raise
                            result["seed_errors"].append({"url":url,"error":str(exc)[:500]})
                            LOG.warning("seed failed source=%s url=%s error=%s",source.id,url,exc)
                            break
                        finally:
                            # Preserve earlier sections even if a later one blocks.
                            if found:
                                result["discovered"] += store.enqueue(source.id,list(dict.fromkeys(found)),priorities)
                                found.clear()
                if not priorities and not result["stale_links"]:
                    result["seed_errors"].append({"error":"No article links discovered; check adapter or listing page"})
                store.update_state(source.id,next_discovery=time.time()+(60 if result["seed_errors"] else source.poll_seconds))
            for _ in range(min(max_articles,source.max_articles_per_cycle)):
                if self.stop.is_set():
                    break
                task = store.claim(source.id)
                if not task:
                    break
                result["attempted"] += 1
                try:
                    if not source.accepts(task["url"]):
                        store.skip(source.id,task,"Outside current source article allowlist")
                        result["out_of_scope"] += 1
                        continue
                    day = url_publication_day(task["url"])
                    if day and day < (datetime.now(timezone.utc)-timedelta(days=source.max_age_days+1)).date():
                        store.skip(source.id,task,f"Old URL date hint: {day.isoformat()}")
                        result["stale"] += 1
                        continue
                    if not self.robots(browser,store,source,task["url"],cache):
                        store.fail(source.id,task,"robots.txt disallows URL",terminal=True)
                        result["robots_disallowed"] += 1
                        continue
                    page = self.paced_read(browser,store,source,task["url"],article=True)
                    if not source.accepts(page.url):
                        raise ExtractionError("Article redirected outside allowlist")
                    html_hash = digest(page.html)
                    raw_path = self.runtime/"raw"/html_hash[:2]/(html_hash+".html.gz")
                    raw_path.parent.mkdir(parents=True,exist_ok=True)
                    if not raw_path.exists():
                        raw_path.write_bytes(gzip.compress(page.html.encode("utf-8"),mtime=0))
                    article = extract_article(page,source,str(raw_path.relative_to(self.runtime)))
                    if article.published_at:
                        published = datetime.fromisoformat(article.published_at)
                        now = datetime.now(timezone.utc)
                        if published < now-timedelta(days=source.max_age_days):
                            store.skip(source.id,task,f"Older than {source.max_age_days} days: {article.published_at}")
                            result["stale"] += 1
                            continue
                        if published > now+timedelta(days=2):
                            article.quality_flags.append("publication_date_in_future")
                    previous = store.db.execute("SELECT record FROM articles WHERE id=?",(digest(article.canonical_url),)).fetchone()
                    import json
                    old_images = json.loads(previous[0]).get("images",[]) if previous else []
                    article.images = merge_images(article.images,old_images,self.runtime)
                    article.main_image_path = next((x["local_path"] for x in article.images if x["status"]=="saved"),None)
                    # Commit text first: even a browser crash or slow image host
                    # cannot discard the successfully extracted news article.
                    created = store.complete(task,article)
                    result["saved"] += 1
                    result["new"] += int(created)
                    LOG.info("saved source=%s title=%s",source.id,article.title[:100])
                    try:
                        article.images,article.main_image_path = download_images(browser,self.runtime,article.canonical_url,article.title,article.images,old_images,self.stop)
                    except Exception as exc:
                        LOG.warning("image storage failed source=%s article=%s error=%s",source.id,article.canonical_url,exc)
                        for image in article.images:
                            if image["status"]!="saved":
                                image.update(status="failed",error=str(exc)[:500])
                    store.set_images(digest(article.canonical_url),article.images,article.main_image_path)
                except AccessBlocked as exc:
                    store.fail(source.id,task,exc,blocked=True)
                    result["blocked"] += 1
                    raise
                except InterruptedError:
                    store.fail(source.id,task,"Interrupted")
                    raise
                except (PageError,ExtractionError,WebDriverException,ValueError) as exc:
                    store.fail(source.id,task,exc)
                    store.update_state(source.id,last_error=str(exc))
                    result["failed"] += 1
                    browser.diagnostic(self.runtime/"diagnostics",source.id)
                    LOG.warning("article failed source=%s url=%s error=%s",source.id,task["url"],exc)
                    if isinstance(exc,InvalidSessionIdException):
                        raise
            if result["seed_errors"]:
                store.update_state(source.id,last_error=str(result["seed_errors"][-1]))
            elif not result["failed"] and result["saved"]:
                store.update_state(source.id,last_success=utcnow(),last_error=None)
        except AccessBlocked as exc:
            result["error"] = str(exc)
            result["blocked"] = max(1,result["blocked"])
            store.update_state(source.id,cooldown_until=time.time()+1800,last_error=str(exc))
            browser.diagnostic(self.runtime/"diagnostics",source.id)
            LOG.warning("source paused source=%s reason=%s",source.id,exc)
        except InterruptedError:
            result["interrupted"] = True
        except Exception as exc:
            result["error"] = str(exc)
            result["failed"] += 1
            store.update_state(source.id,cooldown_until=time.time()+300,last_error=str(exc))
            browser.diagnostic(self.runtime/"diagnostics",source.id)
            LOG.warning("source failed source=%s error=%s",source.id,exc)
        finally:
            with store.db:
                import json
                store.db.execute("UPDATE runs SET finished_at=?,result=? WHERE id=?",(utcnow(),json.dumps(result,ensure_ascii=False),run_id))
        return result

    def cycle(self,sources:list[Source],workers=2,max_articles=10,max_links=300):
        count = min(workers,len(sources))
        if not count:
            raise ValueError("No sources selected")
        def work(source):
            store = Store(self.runtime/"news.sqlite3")
            try:
                # A source retains its own browser profile regardless of worker count
                # or source ordering. Sessions/cookies are never copied across workers.
                result = []
                for source in [source]:
                    if self.stop.is_set():
                        break
                    state = store.state(source.id)
                    if state["cooldown_until"] > time.time():
                        result.append({"source_id":source.id,"skipped":"cooldown"})
                        continue
                    if state["next_discovery"] > time.time() and not store.has_due_tasks(source.id):
                        result.append({"source_id":source.id,"skipped":"idle"})
                        continue
                    try:
                        with Browser(self.runtime/"profiles"/source.id,self.headless,self.binary,self.driver_path) as browser:
                            result.append(self.collect_source(browser,store,source,max_articles,max_links))
                    except Exception as exc:
                        store.update_state(source.id,last_error=str(exc),cooldown_until=time.time()+300)
                        result.append({"source_id":source.id,"failed":1,"error":str(exc)})
                        LOG.warning("browser failed source=%s error=%s",source.id,exc)
                return result
            finally:
                store.close()
        results = []
        with ThreadPoolExecutor(max_workers=count) as pool:
            futures = [pool.submit(work,source) for source in sources]
            for future in as_completed(futures):
                results.extend(future.result())
        return results
