"""Join candidate news topics with candidate company exposures; no confirmed impact claims."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from taxonomy import ROOT, Matcher

matcher = Matcher([json.loads(line) for line in (ROOT/'output/business_topics.jsonl').read_text().splitlines()])
company = json.loads((ROOT/'examples/company.json').read_text())
article = json.loads((ROOT/'examples/article.json').read_text())
profile = matcher.profile(company)
news = matcher.classify(article, limit=10000)
sectors = {s['sector_id'] for s in profile['candidate_sectors']}
print(json.dumps({'company_id': profile['company_id'], 'article_id': news['article_id'],
    'candidate_matches': [t for t in news['topics'] if t['sector_id'] in sectors],
    'status': 'requires_company_exposure_and_news_context_verification'}, ensure_ascii=False, indent=2))
