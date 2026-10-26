"""Conservative extraction of explicit user declarations; never bank-confirmed facts."""
import hashlib
import json
import re

FIELDS={'loan_terms':('Условия кредита со слов пользователя',r'кредит\w*|займ\w*|ставк\w*|погашени\w*'),
        'trade_exposure':('Внешняя торговля со слов пользователя',r'экспорт\w*|импорт\w*|поставля\w*|закупа\w*'),
        'currency_exposure':('Валюта расчётов со слов пользователя',r'расч[её]т\w*|выручк\w*|плат[её]ж\w*')}

def declarations(text):
    result=[]
    for match in re.finditer(r'[^\n]+?(?:[.!?](?=\s|$)|(?=\n|$))',text):
        quote=match.group().strip()
        if not 8<=len(quote)<=700 or '?' in quote:continue
        if re.search(r'\b(если|допустим|предположим|возможно|вероятно|бы|будет ли|может|статье|источнике|цитата|например|игнорируй|инструкц\w*)\b',quote,re.I):continue
        if not re.search(r'^(?:у нас|наша компания|мы|наш[аи]?\s+(?:компани\w*|кредит\w*|займ\w*|расч[её]т\w*|выручк\w*)|кредит\w*\s+(?:с|у нас)|уточнение\s*:|исправление\s*:)',quote,re.I):continue
        for field,(label,pattern) in FIELDS.items():
            if not re.search(pattern,quote,re.I):continue
            # Loan statements must name an actual contract property, not a request.
            if field=='loan_terms' and not re.search(r'фиксирован\w*|плавающ\w*|погаш\w*|до\s*20\d{2}|нет\s+кредит\w*',quote,re.I):continue
            if field=='currency_exposure' and not re.search(r'рубл\w*|доллар\w*|юан\w*|евро|USD|EUR|CNY|RUB',quote,re.I):continue
            result.append({'field':field,'label':label,'quote':quote,
                           'offset':match.start()+len(match.group())-len(match.group().lstrip()),
                           'explicit_correction':bool(re.match(r'исправление\s*:',quote,re.I))})
            break
        if len(result)>=3:break
    return result


def remember(db,company,user,parent_id,text,created_at):
    db.execute('BEGIN IMMEDIATE')
    saved=[];skipped=[]
    message_id=hashlib.sha256(json.dumps([company['source_record_id'],user,parent_id,text],ensure_ascii=False).encode()).hexdigest()
    for item in declarations(text):
        nid=hashlib.sha256(json.dumps([company['source_record_id'],user,parent_id,item['quote']],ensure_ascii=False).encode()).hexdigest()[:32]
        scope=(company['company_id'],company['source_record_id'],user)
        if db.execute('SELECT 1 FROM clarifications WHERE id=?',(nid,)).fetchone():continue
        if db.execute('SELECT 1 FROM clarifications WHERE company=? AND record_id=? AND user=? AND kind=? AND field=? AND text=?',(*scope,'dialogue_declaration',item['field'],item['quote'])).fetchone():continue
        if db.execute('SELECT count(*) FROM clarifications WHERE company=? AND record_id=? AND user=?',scope).fetchone()[0]>=20:
            skipped.append('Достигнут лимит20 уточнений; удалите неактуальные в профиле.');continue
        # Only explicit correction replaces prior dialogue facts of the same category.
        if item['explicit_correction']:
            prior=db.execute('SELECT id,text FROM clarifications WHERE company=? AND record_id=? AND user=? AND field=? AND kind=?',(*scope,item['field'],'dialogue_declaration')).fetchall()
            if len(prior)==1 and not re.search(r'два|несколько|один из|разн\w* кредит',prior[0][1],re.I):
                db.execute('DELETE FROM clarifications WHERE id=?',(prior[0][0],))
            elif prior:
                skipped.append('Новое уточнение сохранено. Прежние условия неоднозначны: укажите, к какому договору относится исправление.')
        db.execute('INSERT OR IGNORE INTO dialogue_messages VALUES(?,?,?,?,?,?,?)',(message_id,*scope,parent_id,text,created_at))
        db.execute('INSERT INTO clarifications(id,company,record_id,user,text,created_at,field,kind,parent_run_id,quote_offset,message_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                   (nid,*scope,item['quote'],created_at,item['field'],'dialogue_declaration',parent_id,item['offset'],message_id))
        saved.append(nid)
    return {'saved_ids':saved,'not_saved_reasons':skipped}


def changes(before,after):
    old={f['id']:f for f in before};new={f['id']:f for f in after}
    return {'added':[f for key,f in new.items() if key not in old], 'removed':[f for key,f in old.items() if key not in new]}


def analysis_changes(before,after):
    sections=('ai_application','why_for_company','risks','opportunities','actions')
    a={c['text'] for key in sections for c in before.get(key,[])}
    b={c['text'] for key in sections for c in after.get(key,[])}
    return {'added':sorted(b-a),'removed':sorted(a-b),'previous_status':before.get('status'),'current_status':after.get('status')}
