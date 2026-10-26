"""Expose only summaries of an operator-installed, versioned offline evaluation."""
import json
from pathlib import Path
import re


def status(directory):
    directory=Path(directory);path=directory/'evaluation-report.json'
    result={'status':'not_measured','approved_pairs':0,'systems':{},'versions':None}
    pilot=directory/'evaluation-pilot-status.json'
    if pilot.is_file() and pilot.stat().st_size<65536:
        try:
            pool=json.loads(pilot.read_text());result['pending_tasks']=int(pool['tasks']);result['pilot_queries']=int(pool['queries'])
        except (ValueError,OSError,TypeError):result['pilot_error']='unreadable'
    if not path.exists():return result
    try:
        if path.stat().st_size>8*1024*1024:raise ValueError('Report too large')
        report=json.loads(path.read_text())
        if not re.fullmatch('[0-9a-f]{64}',report.get('input_sha256','')):raise ValueError('Input SHA required')
        count=report['adjudicated_human_pairs']
        if type(count) is not int or count<0:raise ValueError('Invalid labels count')
        systems={}
        for name,system in report['systems'].items():
            metrics={}
            for field in ('precision_at_k','ndcg_at_k_judged_pool','judgment_coverage'):
                metric=system['metrics'][field];value=metric['mean']
                if value is not None and (type(value) not in (int,float) or not 0<=value<=1):raise ValueError('Invalid metric')
                metrics[field]={'mean':value,'evaluated_queries':metric['evaluated_queries']}
            systems[name]=metrics
        result.update(status='partially_measured' if count else 'not_measured',approved_pairs=count,systems=systems,
                      versions=report['versions'],input_sha256=report['input_sha256'],k=report['k'])
    except (KeyError,ValueError,OSError,TypeError):result.update(status='invalid_report',report_error='Отчёт оценки не прошёл проверку')
    return result
