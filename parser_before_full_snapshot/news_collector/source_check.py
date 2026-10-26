"""Bounded live adapter checks; no historical crawl and no image downloads."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import gzip
import json
import logging
import time

from .browser import AccessBlocked, Browser
from .extract import discover, extract_article, url_publication_day
from .models import digest, utcnow
from .storage import Store

LOG = logging.getLogger(__name__)


def source_fingerprint(source):
    config = asdict(source)
    for key in ("enabled","notes"):
        config.pop(key,None)
    if not config.get("title_selectors"):
        config.pop("title_selectors",None)
    return digest(json.dumps(config,sort_keys=True,ensure_ascii=False))


def check_one(collector, source, samples=2, max_links=80):
    store = Store(collector.runtime/"news.sqlite3")
    result = {"source_id":source.id,"name":source.name,"publisher_country":source.publisher_country,
              "fingerprint":source_fingerprint(source),"checked_at":utcnow(),"status":"no_articles","requested_samples":samples,
              "samples":[],"seed_errors":[],"article_errors":[],"discovered":0,"attempted":0}
    raw = collector.runtime/"source-checks"/source.id
    raw.mkdir(parents=True,exist_ok=True)
    try:
        if collector.stop.is_set():
            return {**result,"status":"interrupted"}
        if store.state(source.id)["cooldown_until"]>time.time():
            return {**result,"status":"cooldown"}
        with Browser(collector.runtime/"profiles"/source.id,collector.headless,collector.binary,collector.driver_path) as browser:
            cache = {}
            links = []
            disallowed = 0
            for index,seed in enumerate(source.seeds):
                if collector.stop.is_set():
                    return {**result,"status":"interrupted"}
                try:
                    if not collector.robots(browser,store,source,seed,cache):
                        disallowed += 1
                        continue
                    page = collector.paced_read(browser,store,source,seed)
                    if not source.allows_host(page.url):
                        raise ValueError(f"Listing redirected outside source host allowlist: {page.url}")
                    (raw/f"listing-{index}.html.gz").write_bytes(gzip.compress(page.html.encode(),mtime=0))
                    from lxml import html
                    anchors = html.fromstring(page.html).xpath('//a[@href]/@href')
                    (raw/f"listing-{index}.json").write_text(json.dumps({"url":page.url,"links":anchors[:500]},ensure_ascii=False,indent=2),encoding="utf-8")
                    links.extend(discover(page,source,limit=max_links))
                except AccessBlocked:
                    raise
                except Exception as exc:
                    result["seed_errors"].append({"url":seed,"error":str(exc)[:600]})
            links = list(dict.fromkeys(links))
            result["discovered"] = len(links)
            if not links:
                result["status"] = "robots_disallowed" if disallowed else "no_links"
                return result
            attempts = 0
            records = []
            canonical_urls = set()
            text_hashes = set()
            for url in links:
                if collector.stop.is_set():
                    result["status"] = "interrupted"
                    return result
                day = url_publication_day(url)
                if day and day<(datetime.now(timezone.utc)-timedelta(days=source.max_age_days+1)).date():
                    continue
                if len(result["samples"])>=samples or attempts>=samples*3:
                    break
                attempts += 1
                result["attempted"] = attempts
                try:
                    if not collector.robots(browser,store,source,url,cache):
                        result["article_errors"].append({"url":url,"error":"robots.txt disallows article"})
                        continue
                    page = collector.paced_read(browser,store,source,url,article=True)
                    if not source.accepts(page.url):
                        raise ValueError(f"Article redirected outside source article allowlist: {page.url}")
                    path = raw/("article-"+digest(url)[:16]+".html.gz")
                    path.write_bytes(gzip.compress(page.html.encode(),mtime=0))
                    article = extract_article(page,source,str(path.relative_to(collector.runtime)))
                    if article.published_at and datetime.fromisoformat(article.published_at)<datetime.now(timezone.utc)-timedelta(days=source.max_age_days):
                        raise ValueError("Article older than the current-news window")
                    if article.canonical_url in canonical_urls:
                        raise ValueError("Duplicate canonical article in validation sample")
                    record = article.record()
                    if record["text_hash"] in text_hashes:
                        raise ValueError("Duplicate extracted text in validation sample; check for boilerplate")
                    canonical_urls.add(article.canonical_url)
                    text_hashes.add(record["text_hash"])
                    records.append(record)
                    temporary = raw/"samples.jsonl.tmp"
                    temporary.write_text("".join(json.dumps(record,ensure_ascii=False)+"\n" for record in records),encoding="utf-8")
                    temporary.replace(raw/"samples.jsonl")
                    result["samples"].append({"url":url,"canonical_url":article.canonical_url,"title":article.title,
                        "text_chars":len(article.text),"published_at":article.published_at,"text_scope":article.text_scope,
                        "topics":article.topics,"quality_flags":article.quality_flags,"image_candidates":len(article.images)})
                except AccessBlocked:
                    raise
                except Exception as exc:
                    result["article_errors"].append({"url":url,"error":str(exc)[:600]})
            result["status"] = "passed" if len(result["samples"])>=samples else "partial" if result["samples"] else "no_articles"
    except AccessBlocked as exc:
        result.update(status="blocked",error=str(exc)[:600])
        store.update_state(source.id,cooldown_until=time.time()+1800,last_error=str(exc))
    except Exception as exc:
        result.update(status="error",error=str(exc)[:600])
    finally:
        store.close()
    return result


def write_checks(runtime, results):
    ordered = sorted(results.values(),key=lambda row:(row.get("publisher_country")!="RU",row["name"]))
    report = {"updated_at":utcnow(),"checked_sources":len(ordered),"sources_with_samples":sum(bool(x["samples"]) for x in ordered),
              "extracted_articles":sum(len(x["samples"]) for x in ordered),
              "passed_sources":sum(x["status"]=="passed" for x in ordered),"sources":ordered}
    report["passed_by_region"] = {
        "RU":sum(x["status"]=="passed" and x.get("publisher_country")=="RU" for x in ordered),
        "world":sum(x["status"]=="passed" and x.get("publisher_country")!="RU" for x in ordered)}
    target = runtime/"source-checks.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    temporary.replace(target)
    lines = ["# Проверка адаптеров", "", "Это ограниченная проверка текущих статей, без обхода архива и без загрузки изображений.","",
             f"Обновлено: {report['updated_at']}. Проверено источников: {len(ordered)}. Passed: {report['passed_sources']}. Извлечено примеров: {report['extracted_articles']}.","",
             "Passed требует заданного числа разных canonical и разных текстов. Стандартная выборка — две статьи; полнота каждого текста не сертифицируется.","",
             "| ID | Источник | Страна | Статус | Статей проверено | Найдено ссылок | Причина/пример ошибки |", "|---|---|---|---|---:|---:|---|"]
    for row in ordered:
        errors = row.get("seed_errors",[])+row.get("article_errors",[])
        reason = str(row.get("error") or (errors[0]["error"] if errors else ""))[:180].replace("|","/").replace("\n"," ")
        lines.append(f"| {row['source_id']} | {row['name']} | {row['publisher_country']} | {row['status']} | {len(row['samples'])} | {row['discovered']} | {reason} |")
    (runtime/"source-checks.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return report


def check_sources(collector, sources, workers=2, samples=2, max_links=80, resume=False):
    Store(collector.runtime/"news.sqlite3").close()
    report_path = collector.runtime/"source-checks.json"
    previous = json.loads(report_path.read_text()) if report_path.exists() else {"sources":[]}
    results = {row["source_id"]:row for row in previous["sources"]}
    due = [source for source in sources if not (resume and source.id in results
           and results[source.id].get("status") not in ("interrupted","cooldown")
           and results[source.id].get("requested_samples",2)>=samples
           and results[source.id].get("fingerprint")==source_fingerprint(source))]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(check_one,collector,source,samples,max_links) for source in due]
        for future in as_completed(futures):
            result = future.result()
            results[result["source_id"]] = result
            write_checks(collector.runtime,results)
            LOG.info("source-check id=%s status=%s samples=%s discovered=%s",result["source_id"],result["status"],len(result["samples"]),result["discovered"])
    return write_checks(collector.runtime,results)
