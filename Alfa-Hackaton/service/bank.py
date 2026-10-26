"""Local page-aware OCR index. Retrieval candidates are not a claimed bank position."""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from .context import DATA

# Publication dates checked against document title pages. None means not usable as dated evidence.
DATES = {'ALFA-7M26.pdf':'2026-09-07','ALFA-Macro_Insights-Policy_Rate_11Sep.pdf':'2026-09-11',
 'ALFA-consumption.pdf':'2026-08-05','ALFA-macro_stat1H26.pdf':'2026-07-31',
 'ALFA_Russian_Steels_1К21PreviewUpdate_15Apr2021.pdf':'2021-04-15',
 'FI_Strategy_3Q26_22072026.pdf':'2026-07-22','Gold_digest_August26.pdf':None,
 'Inflation_tracker_02.pdf':'2026-09-02','Бонд_Бриф_14092026.pdf':'2026-09-14'}


def schema(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS bank_documents(id TEXT PRIMARY KEY,title TEXT,path TEXT,sha256 TEXT,published_at TEXT,pages INTEGER);
    CREATE TABLE IF NOT EXISTS bank_passages(id TEXT PRIMARY KEY,document_id TEXT,page INTEGER,text TEXT,method TEXT);
    CREATE VIRTUAL TABLE IF NOT EXISTS bank_fts USING fts5(passage_id UNINDEXED,text,tokenize='unicode61');''')


def build(target, reports=None, tessdata=None):
    import pypdfium2 as pdfium
    reports=Path(reports or DATA/'reports')
    with sqlite3.connect(target) as db:
        schema(db)
        for path in sorted(reports.glob('*.pdf')):
            digest=hashlib.sha256(path.read_bytes()).hexdigest();did='bank_'+digest[:16]
            if db.execute('SELECT 1 FROM bank_documents WHERE id=?',(did,)).fetchone():
                db.execute('UPDATE bank_documents SET published_at=? WHERE id=?',(DATES.get(path.name),did));db.commit();continue
            doc=pdfium.PdfDocument(str(path))
            # Per-document transaction: an interrupted OCR never publishes half a document.
            db.execute('INSERT INTO bank_documents VALUES(?,?,?,?,?,?)',(did,path.name,str(path.resolve()),digest,DATES.get(path.name),len(doc)))
            for number in range(len(doc)):
                page=doc[number];text=page.get_textpage().get_text_range()
                method='pdf_text'
                if len(text.strip())<80:
                    method='tesseract-rus-eng-unverified'
                    with tempfile.TemporaryDirectory() as tmp:
                        png=Path(tmp)/'page.png';page.render(scale=2.5).to_pil().save(png)
                        command=['tesseract',str(png),'stdout','-l','rus+eng','--psm','3']
                        if tessdata:command += ['--tessdata-dir',str(tessdata)]
                        text=subprocess.run(command,check=True,capture_output=True,text=True,timeout=120).stdout
                for i,start in enumerate(range(0,len(text),1800)):
                    chunk=text[start:start+2200].strip()
                    if len(chunk)<40:continue
                    pid=f'{did}_p{number+1}_{i}'
                    db.execute('INSERT INTO bank_passages VALUES(?,?,?,?,?)',(pid,did,number+1,chunk,method))
                    db.execute('INSERT INTO bank_fts VALUES(?,?)',(pid,chunk))
                page.close()
            doc.close();db.commit()
            print(json.dumps({'document':path.name,'indexed':True},ensure_ascii=False),flush=True)


def _semantic_candidates(assets,index,vector,encoder_sha,as_of):
    if vector is None or not encoder_sha or not index or not Path(index).is_file():return []
    import hashlib
    import numpy as np
    query=np.asarray(vector,dtype=np.float32)
    if query.shape!=(384,) or not np.isfinite(query).all() or float(np.linalg.norm(query))<1e-8:return []
    query/=np.linalg.norm(query)
    start=(datetime.fromisoformat(as_of.replace('Z','+00:00'))-timedelta(days=180)).date().isoformat()
    with sqlite3.connect(Path(index).resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        report=json.loads(db.execute("SELECT value FROM metadata WHERE key='report'").fetchone()[0])
        if report['encoder_sha256']!=encoder_sha:return []
        db.execute('ATTACH DATABASE ? AS assets',(Path(assets).resolve().as_uri()+'?mode=ro',))
        rows=db.execute("""SELECT p.id,d.id AS document_id,d.title AS document_title,d.published_at,p.page,p.text,p.method,
            e.vector,e.text_sha256,e.document_sha256,d.sha256 AS current_document_sha
            FROM embeddings e JOIN assets.bank_passages p ON p.id=e.id JOIN assets.bank_documents d ON d.id=p.document_id
            WHERE d.published_at IS NOT NULL AND d.published_at BETWEEN ? AND ?""",(start,as_of[:10])).fetchall()
    found=[]
    for row in rows:
        if row['document_sha256']!=row['current_document_sha'] or hashlib.sha256(row['text'].encode()).hexdigest()!=row['text_sha256']:continue
        embedding=np.frombuffer(row['vector'],dtype=np.float32)
        if embedding.shape!=(384,) or not np.isfinite(embedding).all():continue
        score=float(query@embedding)
        if score<.80:continue
        item={k:row[k] for k in ('id','document_id','document_title','published_at','page','text','method')}
        item['semantic_score']=score;found.append(item)
    return sorted(found,key=lambda r:(-r['semantic_score'],r['id']))[:24]


def semantic_candidates(*args):
    try:return _semantic_candidates(*args)
    except (sqlite3.Error,OSError,ValueError,KeyError,TypeError):return []


def retrieval_status(index,encoder_sha):
    result={'mode':'lexical','semantic_passages':0,'encoder_compatible':False,'quality_measured':False}
    if not Path(index).is_file():return result
    try:
        with sqlite3.connect(Path(index).resolve().as_uri()+'?mode=ro',uri=True) as db:
            report=json.loads(db.execute("SELECT value FROM metadata WHERE key='report'").fetchone()[0])
        result.update(encoder_compatible=encoder_sha==report['encoder_sha256'],semantic_passages=report.get('passages',0))
        if result['encoder_compatible']:result['mode']='hybrid_lexical_and_event_semantic'
    except (sqlite3.Error,OSError,ValueError,KeyError,TypeError):result['index_error']='unreadable'
    return result


def search(assets,query,as_of,limit=5,event_vector=None,encoder_sha=None,semantic_index=None):
    # Independent lexical and event-embedding channels, fused by reciprocal rank.
    stop={'котор','компа','новос','банка','этого','этой','также','после','перед','может','рубле','милли','росси','сегод','вопрос'}
    words=list(dict.fromkeys(w[:8] for w in re.findall(r'[а-яёa-z]{4,}',query.lower()) if w[:5] not in stop))[:24]
    limit=max(1,min(int(limit),10));rows=[]
    with sqlite3.connect(Path(assets).resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='bank_fts'").fetchone():return []
        if words:
            rows=[dict(r) for r in db.execute("""SELECT p.id,d.id AS document_id,d.title AS document_title,d.published_at,p.page,p.text,p.method,
                bm25(bank_fts) AS score FROM bank_fts JOIN bank_passages p ON p.id=bank_fts.passage_id
                JOIN bank_documents d ON d.id=p.document_id WHERE bank_fts MATCH ? AND d.published_at IS NOT NULL
                AND d.published_at BETWEEN ? AND ? ORDER BY score LIMIT ?""",
                (' OR '.join('"'+w+'"*' for w in words),(datetime.fromisoformat(as_of.replace('Z','+00:00'))-timedelta(days=180)).date().isoformat(),as_of[:10],60))]
    combined={}
    for rank,row in enumerate(rows,1):
        combined[row['id']]={**row,'lexical_score':row['score'],'retrieval_methods':['lexical'], 'fusion_score':1/(60+rank)}
    for rank,row in enumerate(semantic_candidates(assets,semantic_index,event_vector,encoder_sha,as_of),1):
        if row['id'] in combined:
            combined[row['id']]['semantic_score']=row['semantic_score']
            combined[row['id']]['retrieval_methods'].append('semantic_event')
            combined[row['id']]['fusion_score']+=1/(60+rank)
        else:combined[row['id']]={**row,'score':row['semantic_score'],'retrieval_methods':['semantic_event'],'fusion_score':1/(60+rank)}
    result=[];counts={}
    for item in sorted(combined.values(),key=lambda r:(-r['fusion_score'],r['id'])):
        text=item['text']
        if sum(c.isalpha() for c in text)/max(1,len(text))<.50:continue
        if counts.get(item['document_id'],0)>=2:continue
        counts[item['document_id']]=counts.get(item['document_id'],0)+1
        age=(datetime.fromisoformat(as_of.replace('Z','+00:00')).date()-datetime.fromisoformat(item['published_at']).date()).days
        item.update(locator=f"{item['document_title']}, с. {item['page']}",url=f"/api/live/bank-file?document_id={item['document_id']}#page={item['page']}",
                    age_days=age,relation='analogous',limitations='OCR: сверяйте числа с PDF. Близость события/слов не доказывает применимость позиции банка к компании.')
        result.append(item)
        if len(result)>=limit:break
    return result


def documents(assets):
    with sqlite3.connect(Path(assets).resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        return [{**dict(r),'url':'/api/live/bank-file?document_id='+r['id']} for r in db.execute('SELECT id,title,published_at,pages,sha256 FROM bank_documents ORDER BY published_at DESC')]

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--reports');p.add_argument('--tessdata');a=p.parse_args()
    build(a.output,a.reports,a.tessdata)


def compare_forecasts(assets,passages,as_of,max_extra=2):
    """Find exact-context later forecasts, without changing retrieval scores/order."""
    from pipeline.facts import compare,extract
    # The full dated pool is small; preserve all normal as_of and OCR text gates.
    max_extra=max(0,min(int(max_extra),2))
    if not passages:return {'report':compare([]),'additional_passages':[],'policy':'explicit-matching-forecast-companions-v1','retrieval_order_unchanged':True}
    start=(datetime.fromisoformat(as_of.replace('Z','+00:00'))-timedelta(days=180)).date().isoformat()
    def source(row):
        return {**row,'title':row.get('document_title',''),'owner':'alfa_bank'}
    with sqlite3.connect(Path(assets).resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        rows=[dict(r) for r in db.execute('''SELECT p.id,d.id AS document_id,d.title AS document_title,d.published_at,p.page,p.text,p.method
            FROM bank_passages p JOIN bank_documents d ON d.id=p.document_id
            WHERE d.published_at IS NOT NULL AND d.published_at BETWEEN ? AND ? ORDER BY d.published_at DESC,p.id LIMIT 500''',(start,as_of[:10]))]
    rows=[r for r in rows if sum(c.isalpha() for c in r['text'])/max(1,len(r['text']))>=.50]
    selected={p['id'] for p in passages}
    original=[source(p) for p in passages]
    # Restrict candidates to explicit matching context before pair comparisons.
    def key(f):
        return (f['metric'],f['subject']['id'],f['period']['key'],f['unit'],f['measure'],f['aggregation'],f['frequency'],f['accounting'],f['valuation'],f['scenario'])
    original_facts=[f for s in original for f in extract(s) if f['comparable']]
    keys={key(f) for f in original_facts}
    candidates=[source(r) for r in rows if r['id'] not in selected and any(f['comparable'] and key(f) in keys for f in extract(source(r)))] if keys else []
    # Compare each candidate against retrieved context; other candidate pairs cannot
    # introduce unrelated sources or push a retrieved passage out of the result.
    updates=[]
    for candidate in candidates if max_extra else []:
        report=compare([*original,candidate])
        facts={f['id']:f for f in report['facts']}
        preferred=[facts[c['preferred_fact_id']] for c in report['comparisons'] if c['preferred_fact_id'] and c['status'] in ('forecast_revision','later_forecast') and candidate['id'] in c['source_ids']]
        if any(f['source_id']==candidate['id'] for f in preferred):updates.append(candidate)
        if len(updates)>=max_extra:break
    for p in updates:
        p.update(url=f"/api/live/bank-file?document_id={p['document_id']}#page={p['page']}",
                 locator=f"{p['document_title']}, с. {p['page']}",retrieval_methods=['forecast_context_companion'],
                 relation='analogous',limitations='Дополнение к найденному прогнозу с совпавшим показателем и горизонтом; не самостоятельная оценка применимости к компании.')
    return {'report':compare([*original,*updates]),'additional_passages':updates,
            'policy':'explicit-matching-forecast-companions-v1','retrieval_order_unchanged':True}
