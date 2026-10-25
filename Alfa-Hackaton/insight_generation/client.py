"""Server-side adapter for the hackathon gateway. No automatic paid retries."""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from jsonschema import Draft202012Validator

try:
    from .prompt import OUTPUT_SCHEMA, build_request
except ImportError:
    from prompt import OUTPUT_SCHEMA, build_request

BASE_URL = "https://changellenge.up.railway.app/v1"
ALLOWED_URLS = {BASE_URL, "https://api.alfahack-gateway26.ru/v1"}
MODELS = {
    "google/gemma-4-26b-a4b-it", "z-ai/glm-5.3-flash",
    "qwen/qwen3.6-35b-a3b", "deepseek/deepseek-v4.1-flash",
    "qwen/qwen3-vl-30b-a3b-instruct", "moonshotai/kimi-k2.6",
}


def _date(value):
    """Compare source dates consistently, including ISO timestamps with offsets."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Для используемого источника нужна дата публикации")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Некорректная дата источника") from None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def validate_result(result, payload):
    Draft202012Validator(OUTPUT_SCHEMA).validate(result)
    facts = {f["id"] for f in payload["company_facts"]}
    passages = {p["id"] for p in payload["bank_passages"]}
    news_id = payload["news"]["id"]
    sources = passages | {news_id}

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "source_ids" and not set(item) <= sources:
                    raise ValueError("Ответ ссылается на неизвестный источник")
                if key == "company_fact_ids" and not set(item) <= facts:
                    raise ValueError("Ответ ссылается на неизвестный признак компании")
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(result)
    as_of = _date(payload["as_of"])
    # An as_of calendar date includes that whole day, rather than midnight only.
    if len(payload["as_of"]) == 10:
        as_of = as_of.replace(hour=23, minute=59, second=59, microsecond=999999)
    news_date = payload["news"].get("published_at")
    if news_date and _date(news_date) > as_of:
        raise ValueError("Новость опубликована после даты анализа")
    if result["event"]["source_ids"] != [news_id]:
        raise ValueError("Факт события должен ссылаться на исходную новость")
    bank = result["bank_view"]
    if bank:
        if not set(bank["source_ids"]) <= passages:
            raise ValueError("Позиция банка должна ссылаться на материалы банка")
        label = ("Позиция Альфа-Банка по событию" if bank["relation"] == "direct"
                 else "Позиция Альфа-Банка по схожей ситуации")
        if bank["label"] != label:
            raise ValueError("Подпись не соответствует типу позиции банка")
        used = {p["id"]: p for p in payload["bank_passages"]}
        for source_id in bank["source_ids"]:
            if _date(used[source_id].get("published_at")) > as_of:
                raise ValueError("Материал банка опубликован после даты анализа")
        if bank["relation"] == "analogous" and not bank["limitations"].strip():
            raise ValueError("Для аналогичной ситуации нужны ограничения переноса")
    if result["status"] == "ready" and not result["why_for_company"]:
        raise ValueError("Готовый инсайт должен объяснять связь с компанией")
    confirmed = {f["id"] for f in payload["company_facts"]
                 if f.get("evidence_level") == "confirmed"}
    if result["status"] == "ready" and not any(
        set(claim["company_fact_ids"]) & confirmed
        for claim in result["why_for_company"]
    ):
        raise ValueError("Связь только по гипотезам требует needs_context")
    uncertain = {f["id"] for f in payload["company_facts"]
                 if f.get("evidence_level") != "confirmed"}
    for field in ("why_for_company", "ai_application", "risks", "opportunities", "actions"):
        for claim in result[field]:
            if set(claim["company_fact_ids"]) & uncertain and not claim["conditional"]:
                raise ValueError("Вывод по неподтверждённому признаку должен быть условным")
    if result["status"] == "needs_context" and not result["missing_context"]:
        raise ValueError("Укажите, каких данных не хватает для персонального вывода")
    if result["status"] == "not_relevant" and any(result[k] for k in (
        "why_for_company", "ai_application", "risks", "opportunities", "actions"
    )):
        raise ValueError("Нерелевантная новость не должна содержать персональных выводов")
    return result


def generate(payload, *, transport=None):
    key = os.environ.get("ALFA_API_KEY", "")
    if not key:
        raise ValueError("Задайте ALFA_API_KEY в окружении серверного процесса")
    base = os.environ.get("ALFA_BASE_URL", BASE_URL).rstrip("/")
    model = os.environ.get("ALFA_MODEL", "z-ai/glm-5.3-flash")
    if base not in ALLOWED_URLS or model not in MODELS:
        raise ValueError("Используйте адрес шлюза и модель из инструкции организаторов")
    prepared = build_request(payload)
    ids = ([payload["news"]["id"]]
           + [f["id"] for f in payload["company_facts"]]
           + [p["id"] for p in payload["bank_passages"]])
    if len(ids) != len(set(ids)):
        raise ValueError("ID входных материалов должны быть уникальны")
    messages = prepared["messages"]
    # Put the schema in the prompt to avoid assuming gateway support for
    # response_format/json_schema. Always validate the returned JSON locally.
    messages[0]["content"] += "\nJSON Schema:\n" + json.dumps(OUTPUT_SCHEMA, ensure_ascii=False)
    body = {"model": model, "messages": messages, "max_tokens": 4096}
    request = Request(base + "/chat/completions",
                      data=json.dumps(body).encode(),
                      headers={"Authorization": "Bearer " + key,
                               "Content-Type": "application/json"}, method="POST")
    try:
        with (transport or urlopen)(request, timeout=120) as response:
            raw = json.load(response)
    except HTTPError as exc:
        # Do not echo server errors: they may contain request data or credentials.
        message = exc.read().decode("utf-8", errors="replace").lower()
        if "budget has been exceeded" in message:
            raise RuntimeError("Бюджет исчерпан; сброс в 03:00 МСК. Повторов не было.") from None
        raise RuntimeError(f"Ошибка шлюза HTTP {exc.code}. Повторов не было.") from None
    except (URLError, TimeoutError):
        raise RuntimeError("Шлюз недоступен или истёк таймаут. Повторов не было.") from None
    try:
        choice = raw["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise ValueError("Модель не завершила ответ; результат не опубликован")
        content = choice["message"]["content"].strip()
        # Some compatible endpoints wrap JSON in a Markdown code block.
        # Accept a single complete block, never extract a fragment from prose.
        if content.startswith("```json\n") and content.endswith("\n```"):
            content = content[8:-4]
        elif content.startswith("```\n") and content.endswith("\n```"):
            content = content[4:-4]
        result = json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        raise ValueError("Шлюз не вернул ожидаемый JSON; результат не опубликован") from None
    return {"insight": validate_result(result, payload),
            "model": model, "usage": raw.get("usage", {})}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Path to input JSON")
    args = parser.parse_args()
    try:
        with open(args.input) as stream:
            payload = json.load(stream)
        print(json.dumps(generate(payload), ensure_ascii=False, indent=2))
    except Exception as exc:
        # Validation errors may include full documents; never dump them to logs.
        from jsonschema.exceptions import ValidationError
        if isinstance(exc, ValidationError):
            print("Ответ не соответствует JSON Schema; результат не опубликован", file=sys.stderr)
        elif isinstance(exc, (ValueError, RuntimeError)):
            print(str(exc), file=sys.stderr)
        else:
            print("Ошибка обработки запроса; результат не опубликован", file=sys.stderr)
        sys.exit(1)
