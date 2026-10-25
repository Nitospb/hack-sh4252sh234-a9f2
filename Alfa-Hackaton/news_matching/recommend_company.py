"""Read-only company feed from accepted labels and the original OKVED→bt_ mapping."""
import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SCOPES={'strict':('declared_activity',),'activity':('declared_activity','activity_scope_candidate'),
        'interest':('declared_activity','activity_scope_candidate','operating_exposure')}
WEIGHTS={'declared_activity':1.,'activity_scope_candidate':.65,'operating_exposure':.35}


def recommend(company_id,scope='strict',limit=10,source_record_id=None):
    db=sqlite3.connect('file:'+str((ROOT/'output/news_topics.sqlite').resolve())+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    profiles=db.execute('SELECT c.*,a.activity FROM companies c JOIN company_activities a USING(okved) WHERE company_id=? ORDER BY source_line',(company_id,)).fetchall()
    if not profiles:return {'company_id':company_id,'status':'company_not_found','items':[]}
    if len(profiles)>1 and not source_record_id:
        return {'company_id':company_id,'status':'conflicting_profiles_choose_source_record','profiles':[dict(p) for p in profiles],'items':[]}
    profile=next((p for p in profiles if not source_record_id or p['source_record_id']==source_record_id),None)
    if profile is None:return {'company_id':company_id,'status':'source_record_not_found','items':[]}
    allowed=SCOPES[scope];marks=','.join('?' for _ in allowed)
    query=f'''SELECT a.*,n.topic_id,n.embedding_cosine,n.reranker_logit,n.evidence,n.modality,t.name AS topic_name,m.relation,b.reason
 FROM company_mapping m JOIN assignments n USING(topic_id) JOIN articles a USING(article_id)
 JOIN topics t USING(topic_id) JOIN company_bindings b ON b.binding_id=m.binding_id
 WHERE m.okved=? AND m.relation IN ({marks}) AND a.eligible_delivery=1'''
    matches=db.execute(query,(profile['okved'],*allowed)).fetchall();by_article={}
    for r in matches:
        item=by_article.setdefault(r['article_id'],dict(article_id=r['article_id'],title=r['title'],url=r['url'],source=r['source'],published_at=r['published_at'],score=-999.,matches=[]))
        score=r['reranker_logit']+2*r['embedding_cosine']+WEIGHTS[r['relation']]
        item['score']=max(item['score'],round(score,6))
        item['matches'].append({'topic_id':r['topic_id'],'topic_name':r['topic_name'],'company_relation':r['relation'],
            'why_for_company':r['reason'],'news_evidence':r['evidence'],'news_modality':r['modality'],
            'embedding_cosine':r['embedding_cosine'],'reranker_logit':r['reranker_logit']})
    db.close();ranked=sorted(by_article.values(),key=lambda x:(-x['score'],str(x['published_at']),x['article_id']))
    return dict(company_id=company_id,source_record_id=profile['source_record_id'],okved=profile['okved'],activity=profile['activity'],scope=scope,
        status='matched' if ranked else 'no_articles_passed_news_quality_and_company_scope_gates',total_eligible_matches=len(ranked),items=ranked[:limit],
        interpretation='Topic-based relevance candidates, not established business impact. Activity-scope candidates are not verified specializations; operating exposures do not establish own activity.',
        graph_relationships_used=False,ranking_scores_are_probabilities=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('company_id');p.add_argument('--scope',choices=SCOPES,default='strict');p.add_argument('--limit',type=int,default=10);p.add_argument('--source-record-id')
    a=p.parse_args();print(json.dumps(recommend(a.company_id,a.scope,a.limit,a.source_record_id),ensure_ascii=False,indent=2))
