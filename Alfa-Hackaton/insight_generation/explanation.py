"""Deterministic source excerpts and explicit relevance hypotheses; no LLM calls."""
import re
from html import unescape


def _plain(value, limit=600):
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", str(value or ""), flags=re.I | re.S)
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"\s+", " ", unescape(text)).strip()
    return text[:limit].rstrip() + ("…" if len(text) > limit else "")


def build_explanation(company, article, viewer_role="general", matches=None, industries=None):
    """Build a transparent reading aid, without inventing impact or bank opinions.

    Interests are inferred from OKVED. A match establishes a thematic connection,
    not the company's actual exposure, an occurred event, or a financial effect.
    Source text is quoted, never executed or treated as instructions.
    """
    if matches is None:
        interests = {m.get("family_key"): m for m in company.get("interests", [])}
        matches = []
        for match in article.get("object_matches", []):
            interest = interests.get(match.get("family_key"))
            if interest:
                matches.append({**match, "company_reason": interest.get("reason"),
                                "relation": interest.get("relation")})
    industries = industries if industries is not None else article.get("matched_industries", [])
    title = _plain(article.get("title"), 240)
    body = _plain(article.get("text") or article.get("fulltext"), 12000)
    sentences = re.split(r"(?<=[.!?])\s+(?=[А-ЯЁA-Z0-9«\"])", body)
    event = _plain(" ".join(sentences[:2]), 650) if body else title
    reasons = []
    review = False
    for match in matches:
        topic = _plain(match.get("object") or match.get("name"), 100)
        reason = _plain(match.get("company_reason") or match.get("reason"), 250)
        relation = match.get("relation")
        label = {"declared_activity": "связь с заявленной деятельностью",
                 "activity_scope_candidate": "возможная специализация",
                 "operating_exposure": "возможный косвенный интерес"}.get(relation, "тематическая связь")
        if not topic and not reason:
            continue
        line = f"Предположение по ОКВЭД: {label}"
        if topic:
            line += f" — «{topic}»"
        if reason:
            line += f". {reason}"
        if match.get("status") == "review":
            line += " Совпадение темы требует проверки."
            review = True
        if line not in reasons:
            reasons.append(line)
    for industry in industries:
        reason = _plain(industry.get("reason"), 250)
        if reason:
            line = "Предположение по отраслевому контексту: " + reason
            if line not in reasons:
                reasons.append(line)
    questions_by_role = {
        "treasurer": ["Есть ли у компании платежи, договоры или финансирование, связанные с описанным событием?",
                      "Какие сроки платежей и условия договоров стоит проверить до изменения планов?"],
        "accountant": ["Затрагивает ли событие учёт, документы или отчётные сроки вашей компании?",
                       "Какие первичные документы и действующие правила нужны для проверки применимости?"],
        "director": ["Какие действующие операции или проекты компании связаны с этим событием?",
                     "Какие условия должны выполниться, чтобы потребовалось пересмотреть планы?"],
        "cfo": ["Какие статьи бюджета или условия финансирования могут быть связаны с этим событием?",
                "Каких параметров договоров и планов не хватает, чтобы оценить возможный эффект?"],
        "owner": ["Какие направления бизнеса действительно связаны с этим событием?",
                  "Какие факты нужно подтвердить перед пересмотром стратегии?"],
        "it": ["Затрагивает ли событие технологии, инфраструктуру или данные, которые использует компания?",
               "Какие требования совместимости, безопасности и внедрения стоит проверить?"],
        "sales": ["Связано ли событие с рынками, клиентами или каналами продаж компании?",
                  "Какие данные о спросе и действующих контрактах нужны для проверки этой связи?"],
        "procurement": ["Есть ли у компании закупки или поставки, относящиеся к теме новости?",
                        "Какие условия, сроки и альтернативы поставок стоит проверить?"],
    }
    questions_by_role["finance"] = questions_by_role["cfo"]
    questions = questions_by_role.get(viewer_role, [
        "Связана ли тема новости с фактическими операциями вашей компании?",
        "Какие договоры, сроки или планы нужно проверить, чтобы оценить применимость события?"])
    limitations = ["Связь с компанией предполагается по темам и ОКВЭД; фактическое влияние и денежный эффект не оценены.",
                   "Это извлечение из источника и объяснение отбора без генерации ИИ; позиция банка не добавлялась."]
    if not reasons:
        limitations.append("Прямая тематическая связь с компанией не подтверждена; материал может относиться к общей деловой повестке.")
    if review:
        limitations.append("Автоматическое тематическое совпадение требует проверки перед бизнес-выводами.")
    return {"mode": "source_based_explanation", "ai_generated": False,
            "title": title, "event": event, "why_for_company": reasons[:2],
            "questions": questions, "bank_view": None, "limitations": limitations,
            "source": {"id": article.get("article_id") or article.get("id"),
                       "url": article.get("url"), "published_at": article.get("published_at")},
            "viewer_role": viewer_role}
