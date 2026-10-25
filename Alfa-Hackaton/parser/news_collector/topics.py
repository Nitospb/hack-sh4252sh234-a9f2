"""Transparent multilingual hints, not a trained semantic classifier."""
import re

TERMS = {
    "politics": r"\b(?:politic\w*|parliament\w*|election\w*|presiden\w*|government|diploma\w*|sanction\w*|geopolitic\w*|legislat\w*)\b|политик\w*|парламент\w*|выбор(?:ы|ов|ам|ами|ах|н[а-я]*)\b|президент\w*|правительств\w*|дипломат\w*|санкци\w*|геополит\w*|законопроект\w*|政治|政府|选举|外交|政権|選挙|gouvernement|élection|Regierung|Bundestag|gobierno|eleccion\w*",
    "ai": r"\b(?:AI|LLM|GPT\w*|OpenAI|Anthropic|DeepSeek|ChatGPT|Nvidia|machine learning|artificial intelligence)\b|искусственн\w* интеллект|нейросет\w*|машинн\w* обучен|人工智能|大模型",
    "business": r"\b(?:business|compan\w*|revenue|profit\w*|acquisition\w*|merger\w*|startup\w*|funding|IPO|earnings)\b|бизнес\w*|компани\w*|выручк\w*|прибыл\w*|стартап\w*|сделк\w*|企业|公司",
    "economy": r"\b(?:econom\w*|inflation|GDP|tariff\w*|trade|interest rates|unemployment|central bank)\b|эконом\w*|инфляц\w*|ВВП|ключев\w* ставк|безработиц\w*|пошлин\w*|经济|贸易",
    "finance": r"\b(?:bank\w*|stock\w*|bond\w*|invest\w*|market\w*|currency|credit|fintech)\b|банк\w*|финанс\w*|инвест\w*|акци[яийю]\w*|облигац\w*|кредит\w*|金融|投资",
    "technology": r"\b(?:tech\w*|software|chip\w*|semiconductor\w*|cloud|data cent\w*|cyber\w*|robot\w*)\b|технолог\w*|процессор\w*|микросхем\w*|кибер\w*|робот\w*|дата-?центр\w*|科技|芯片",
    "energy": r"\b(?:energy|oil|gas|renewable\w*|electricity)\b|нефт\w*|энерг\w*|газ[а-я]*|электр\w*|能源",
}
TERMS["finance"] += r"|\b(?:banqu\w*|banc\w*|bours\w*|marché\w*|Finanz\w*|Börse\w*|Aktien\w*|Anleihe\w*|mercado\w*|inversi[oó]n\w*|investimento\w*|credito\w*|giełd\w*|kredyt\w*)\b"
TERMS["economy"] += r"|\b(?:[ée]conomi\w*|Wirtschaft\w*|Konjunktur\w*|Inflation\w*|gospodar\w*|inflaci[oó]n\w*|inflaç[aã]o|comercio\w*|comércio\w*)\b"
TERMS["business"] += r"|\b(?:entreprise\w*|Unternehmen\w*|Umsatz\w*|Gewinn\w*|empresa\w*|neg[oó]cio\w*|ricavi|imprese|spółk\w*)\b"
TERMS["politics"] += r"|\b(?:pol[ií]tic\w*|parlament\w*|elecci[oó]n\w*|eleiç[oõ]es|governo\w*|pr[ée]sident\w*|sanktion\w*|sancion\w*|sanzion\w*)\b"
TERMS["politics"] += r"|Госдум\w*|Совет\w* Федераци\w*|конгресс\w*|сенат\w*|министр\w*|премьер\w*|губернатор\w*|\b(?:senate|congress|minister\w*|cabinet|governor\w*|duma)\b"
PATTERNS = {key: re.compile(value, re.I) for key, value in TERMS.items()}


def classify(title, description, text):
    lead = title + " " + (description or "")
    body = text[:12000]
    scores = {key: min(10, len(pattern.findall(lead)) * 3 + len(pattern.findall(body)))
              for key, pattern in PATTERNS.items()}
    return [key for key, score in scores.items() if score], min(100, sum(scores.values()) * 2)
