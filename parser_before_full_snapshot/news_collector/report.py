"""Coverage grounded in stored article records and actual run results."""
from collections import Counter, defaultdict
import json
from pathlib import Path

from .models import utcnow


def coverage(store, config):
    records = defaultdict(list)
    for row in store.db.execute("SELECT source_id,record FROM articles"):
        records[row[0]].append(json.loads(row[1]))
    runs = {}
    for row in store.db.execute("SELECT source_id,result,finished_at FROM runs WHERE finished_at IS NOT NULL ORDER BY id"):
        runs[row[0]] = {**json.loads(row[1]),"finished_at":row[2]}
    states = {row["source_id"]:dict(row) for row in store.db.execute("SELECT * FROM source_state")}
    sources = []
    configs = sorted(json.loads(Path(config).read_text())["sources"],key=lambda s:s.get("collection_priority",50),reverse=True)
    for source in configs:
        sid = source["id"]
        articles = records[sid]
        run = runs.get(sid,{})
        state = states.get(sid,{})
        scopes = Counter(a["text_scope"] for a in articles)
        quarantined = store.db.execute("SELECT reason FROM quarantined_articles WHERE source_id=? ORDER BY quarantined_at DESC",(sid,)).fetchall()
        if run.get("blocked"):
            status = "blocked"
        elif run.get("robots_disallowed") and not articles:
            status = "robots_disallowed"
        elif run.get("error") or (not articles and (run.get("failed") or state.get("last_error"))):
            status = "error"
        elif articles:
            status = "partial" if run.get("failed") or run.get("seed_errors") else "collected"
        elif quarantined:
            status = "validation_failed"
        elif run:
            status = "no_articles"
        else:
            status = "untested"
        sources.append({"id":sid,"name":source["name"],"enabled":source["enabled"],"status":status,
            "publisher_country":source.get("publisher_country"),
            "collection_priority":source.get("collection_priority",50),"article_budget":source.get("max_articles_per_cycle",20),
            "articles":len(articles),"extracted":scopes["extracted_article"],"excerpts":scopes["accessible_excerpt"],
            "missing_date":sum(not a.get("published_at") for a in articles),
            "saved_images":sum(x.get("status")=="saved" for a in articles for x in a.get("images",[])),
            "topics":dict(Counter(t for a in articles for t in a.get("topics",[]))),
            "queue":dict((r[0],r[1]) for r in store.db.execute("SELECT state,count(*) FROM frontier WHERE source_id=? GROUP BY state",(sid,))),
            "last_run":run,"last_error":state.get("last_error") or (quarantined[0][0] if quarantined and not articles else None),"notes":source.get("notes",""),"quarantined":len(quarantined),
            "examples":[{"title":a["title"],"url":a["canonical_url"],"scope":a["text_scope"]} for a in articles[-3:]]})
    all_articles = [a for items in records.values() for a in items]
    text_hashes = Counter(a.get("text_hash") for a in all_articles if a.get("text_hash"))
    return {"generated_at":utcnow(),"configured_sources":len(sources),"sources_with_articles":sum(s["articles"]>0 for s in sources),
            "articles":len(all_articles),"excerpts":sum(a["text_scope"]=="accessible_excerpt" for a in all_articles),
            "financial_priority_sources":sum(s["collection_priority"]>=90 for s in sources),
            "russian_sources_with_articles":sum(s["articles"]>0 and s["publisher_country"]=="RU" for s in sources),
            "financial_topic_articles":sum(bool(set(a.get("topics",[])) & {"finance","economy"}) for a in all_articles),
            "articles_with_images":sum(any(x.get("status")=="saved" for x in a.get("images",[])) for a in all_articles),
            "saved_images":sum(x.get("status")=="saved" for a in all_articles for x in a.get("images",[])),
            "saved_image_files":len({x["local_path"] for a in all_articles for x in a.get("images",[]) if x.get("status")=="saved"}),
            "filtered_images":sum(x.get("status")=="filtered" for a in all_articles for x in a.get("images",[])),
            "failed_images":sum(x.get("status")=="failed" for a in all_articles for x in a.get("images",[])),
            "exact_duplicate_text_groups":sum(n>1 for n in text_hashes.values()),"sources":sources}


def write_report(store, config, output):
    result = coverage(store,config)
    output = Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    lines = ["# Покрытие новостных источников", "", f"Обновлено: {result['generated_at']}", "",
             f"Настроено: {result['configured_sources']}. Со статьями: {result['sources_with_articles']}. "
             f"Публикаций: {result['articles']}, доступных фрагментов: {result['excerpts']}.", "",
             f"Файлов изображений: {result['saved_image_files']}. Статей с изображениями: {result['articles_with_images']}. Отсеяно мелких изображений: {result['filtered_images']}. Ошибок отдельных изображений: {result['failed_images']}.", "",
             "collected означает успешные примеры, а не проверку всех материалов сайта. partial — статьи есть, но последний проход содержал ошибки.","",
             "| Источник | Включён | Статус | Статей | Фрагментов | Без даты | Картинок | Последняя ошибка |", "|---|---|---|---:|---:|---:|---:|---|"]
    for source in result["sources"]:
        error = str(source["last_error"] or "").replace("|","/").replace("\n"," ")[:180]
        lines.append(f"| {source['name']} | {'да' if source['enabled'] else 'нет'} | {source['status']} | {source['articles']} | {source['excerpts']} | {source['missing_date']} | {source['saved_images']} | {error} |")
    for source in result["sources"]:
        if source["examples"] or source["last_run"]:
            lines.extend(["", f"## {source['name']}", "", f"Последний проход: `{json.dumps(source['last_run'],ensure_ascii=False)}`", ""])
            for example in source["examples"]:
                lines.append(f"- [{example['title'].replace('[','(').replace(']',')')}]({example['url']}) — {example['scope']}")
    output.write_text("\n".join(lines)+"\n",encoding="utf-8")
    output.with_suffix(".json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result
