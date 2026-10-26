"""Shared budget admission and per-call checks. UTC reset equals 03:00 Moscow."""
from datetime import datetime,timedelta,timezone
import json
import os

CALL_RESERVE=30000
MIN_JOB_CALLS=2
POLICY='minimum-verified-answer-v1'


def snapshot(db,required_calls=MIN_JOB_CALLS,at=None):
    at=at or datetime.now(timezone.utc)
    day=at.astimezone(timezone.utc).date().isoformat()
    reset=(at.astimezone(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=1)).isoformat()
    base={'available':True,'reason':'available','message':'Анализ доступен.','resets_at':reset,'day':day,'policy':POLICY}
    try:
        max_calls=int(os.getenv('ALFA_MAX_CALLS_PER_DAY','30'))
        max_tokens=int(os.getenv('ALFA_MAX_TOKENS_PER_DAY','300000'))
        if min(max_calls,max_tokens)<0:raise ValueError('Negative limit')
    except ValueError:return {**base,'available':False,'reason':'configuration','message':'Анализ временно недоступен: проверьте настройки лимитов.','resets_at':None}
    blocked=db.execute("SELECT value FROM runtime_meta WHERE key='budget_blocked_day'").fetchone()
    if blocked and blocked[0]==day:return {**base,'available':False,'reason':'gateway_budget','message':'Шлюз сообщил об исчерпании общего бюджета. Новые разборы доступны после 03:00 МСК.'}
    rows=db.execute('SELECT status,usage FROM calls WHERE day=?',(day,)).fetchall()
    future=db.execute('SELECT COALESCE(sum(remaining_calls),0) FROM job_budgets WHERE day=?',(day,)).fetchone()[0]
    tokens=0;permanent_unknown=0;active=0
    try:
        for status,raw in rows:
            usage=json.loads(raw) if raw else {};amount=usage.get('total_tokens')
            if amount is not None:
                if type(amount) is not int or amount<0:raise ValueError('Invalid token usage')
                tokens+=amount
            active+=status=='reserved'
            permanent_unknown+=status in ('interrupted','error_unknown_usage') or (amount is None and status in ('complete','error'))
    except (ValueError,TypeError,AttributeError):
        return {**base,'available':False,'reason':'ledger','message':'Анализ временно недоступен: не удалось проверить учёт лимита.','resets_at':None}
    if len(rows)+future+required_calls>max_calls:
        if future and len(rows)+required_calls<=max_calls:
            return {**base,'available':False,'reason':'reserved','resets_at':None,'message':'Ресурс анализа занят текущими разборами. Дождитесь их завершения.'}
        return {**base,'available':False,'reason':'calls','message':'Достигнут суточный лимит вызовов для новых разборов. Лимит обновится в 03:00 МСК.'}
    permanent=tokens+permanent_unknown*CALL_RESERVE
    if permanent+CALL_RESERVE*(active+future+required_calls)>max_tokens:
        if active+future and permanent+CALL_RESERVE*required_calls<=max_tokens:
            return {**base,'available':False,'reason':'reserved','resets_at':None,'message':'Ресурс анализа занят текущими разборами. Дождитесь их завершения.'}
        return {**base,'available':False,'reason':'tokens','message':'Достигнут суточный лимит токенов для новых разборов. Лимит обновится в 03:00 МСК.'}
    return base


def require(db,required_calls=MIN_JOB_CALLS):
    status=snapshot(db,required_calls)
    if not status['available']:raise RuntimeError(status['message'])
    return status['day']
