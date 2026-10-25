"""Assign activity-grounded news interests to every source company record. Stdlib only."""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = 'company-interests.v1'
PRODUCT_INTERESTS = {
 'CL_PRODUCT_RKO_MARK': [('settlement_fees','Тарифы расчётного обслуживания'),('settlement_continuity','Непрерывность банковских расчётов')],
 'CL_PRODUCT_LOA_MARK': [('credit_cost','Стоимость кредитного финансирования'),('credit_terms','Изменение условий кредитования')],
 'CL_PRODUCT_GAR_MARK': [('guarantee_cost','Стоимость банковских гарантий'),('guarantee_rules','Изменение требований к банковским гарантиям')],
 'CL_PRODUCT_LEA_MARK': [('lease_cost','Стоимость лизингового финансирования'),('lease_terms','Изменение условий лизинга')],
 'CL_PRODUCT_DEP_MARK': [('deposit_yield','Доходность корпоративных депозитов'),('deposit_terms','Условия размещения временно свободных средств')],
 'CL_PRODUCT_ZPP_MARK': [('payroll_fees','Тарифы зарплатного проекта'),('payroll_continuity','Непрерывность зарплатных выплат')],
 'FACTORING_MARK': [('factoring_cost','Стоимость факторингового финансирования'),('factoring_terms','Изменение условий факторинга')],
 'FTS_FLAG': [('crossborder_rules','Правила внешнеторговых расчётов'),('crossborder_access','Доступность трансграничных расчётов')],
}


def active(value):
    return str(value).strip() in ('1','1.0','True','true')


def applicable_aspects(row, rules):
    base = [dict(a) for a in aspects_for(row['MAINOKVED_CODE'].strip(), rules)]
    for field, interests in PRODUCT_INTERESTS.items():
        if active(row.get(field, '')):
            for key, name in interests:
                base.append(dict(key='product_' + field.lower() + '_' + key, name=name, why=f'В исходной записи активен признак {field}; изменения условий этого направления могут быть важны для указанной деятельности.', required_flag=field))
    unique = {}
    for aspect in base:
        unique.setdefault(aspect['name'].casefold().replace('ё','е'), aspect)
    return list(unique.values())



def stable_id(kind, *values):
    return kind + '_' + hashlib.sha256('|'.join(values).encode()).hexdigest()[:16]


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def load_rules():
    rules = {}
    for path in sorted((ROOT/'company_rules').glob('*_rules.json')):
        data = json.loads(path.read_text())
        assert not (set(data) & set(rules)), f'Duplicate divisions in {path}'
        rules.update(data)
    return rules


def aspects_for(code, rules):
    rule = rules[code[:2]]
    return rule.get('overrides', {}).get(code, rule['aspects'])


def build_catalog(rows, rules):
    catalog, by_activity = {}, {}
    seen_variants = set()
    for row in rows:
        code, activity = row['MAINOKVED_CODE'].strip(), row['MAINOKVED_NAME'].strip()
        key = (code, activity)
        variant = (code, activity, *(f for f in PRODUCT_INTERESTS if active(row.get(f,''))))
        if variant in seen_variants:
            continue
        seen_variants.add(variant)
        aspects = applicable_aspects(row, rules)
        assert len(aspects) >= 12, code
        assert len({a['key'] for a in aspects}) == len(aspects), code
        assert len({a['name'].casefold() for a in aspects}) == len(aspects), code
        ids = []
        for aspect in aspects:
            tid = stable_id('ci', code, activity, aspect['key'])
            record = dict(topic_id=tid, name=f"{activity} — {aspect['name']}",
                activity_code=code, activity_name=activity, aspect=aspect['name'],
                aspect_key=aspect['key'], rationale=aspect['why'],
                taxonomy_version=VERSION, origin='activity_grounded_agent_rules',
                status='inferred_interest_not_user_confirmed',
                required_flag=aspect.get('required_flag'),
                news_matching_context={'activity': activity, 'aspect': aspect['name'],
                    'require_activity_context': True})
            if tid in catalog:
                assert catalog[tid] == record, 'Hash collision'
            catalog[tid] = record
            ids.append(tid)
        by_activity[key] = list(dict.fromkeys(by_activity.get(key, []) + ids))
    return catalog, by_activity


def assign(source, output):
    output.mkdir(parents=True, exist_ok=True)
    with source.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f, delimiter=';'))
    assert all(r.get('SYNTHETIC_U') and r.get('MAINOKVED_CODE') and r.get('MAINOKVED_NAME') for r in rows)
    rules = load_rules()
    divisions = {r['MAINOKVED_CODE'][:2] for r in rows}
    assert not (divisions-set(rules)), f'Missing divisions: {divisions-set(rules)}'
    catalog, by_activity = build_catalog(rows, rules)
    by_company = defaultdict(list)
    signatures = defaultdict(set)
    for n, row in enumerate(rows, 2):
        by_company[row['SYNTHETIC_U']].append(n)
        signatures[row['SYNTHETIC_U']].add((row['MAINOKVED_CODE'], row['MAINOKVED_NAME'], row['REGION']))
    conflicts = {uid for uid, sig in signatures.items() if len(sig) > 1}
    with (output/'activity_interest_catalog.jsonl').open('w', encoding='utf-8') as f:
        for item in catalog.values():
            f.write(json.dumps(item, ensure_ascii=False)+'\n')
    with (output/'activity_interest_catalog.csv').open('w', encoding='utf-8-sig', newline='') as f:
        fields = ['topic_id','activity_code','activity_name','aspect','name','rationale','status']
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(catalog.values())
    counts = Counter()
    sample_profiles = []
    csv_fields = ['source_record_id','company_id','source_line','okved','activity','region','topic_count','topic_ids','topic_names','status']
    with (output/'company_interests.jsonl').open('w', encoding='utf-8') as jf, (output/'company_interests.csv').open('w', encoding='utf-8-sig', newline='') as cf:
        writer = csv.DictWriter(cf, fieldnames=csv_fields)
        writer.writeheader()
        for line, row in enumerate(rows, 2):
            uid, code, activity = row['SYNTHETIC_U'], row['MAINOKVED_CODE'].strip(), row['MAINOKVED_NAME'].strip()
            ids = [t for t in by_activity[(code, activity)] if not catalog[t]['required_flag'] or active(row.get(catalog[t]['required_flag'], ''))]
            profile = dict(source_record_id=f'{uid}:line:{line}', company_id=uid, source_line=line,
                okved=code, activity=activity, region=row['REGION'], topic_count=len(ids), topic_ids=ids,
                topic_names=[catalog[t]['name'] for t in ids],
                evidence={'MAINOKVED_CODE': code, 'MAINOKVED_NAME': activity, **{f: row[f] for f in PRODUCT_INTERESTS if active(row.get(f,''))}},
                assignment_method='exact_activity_context_plus_division_specific_aspects',
                taxonomy_version=VERSION,
                status='conflicting_company_records_review_required' if uid in conflicts else 'inferred_activity_interests',
                inference_scope='Potential business information interests; no claim of actual products, transactions or user preference.')
            jf.write(json.dumps(profile, ensure_ascii=False)+'\n')
            writer.writerow({k:json.dumps(profile[k], ensure_ascii=False) if isinstance(profile[k],list) else profile[k] for k in csv_fields})
            counts[len(ids)] += 1
            if len(sample_profiles)<15 and code[:2] not in {p['okved'][:2] for p in sample_profiles}:
                sample_profiles.append(profile)
    with (output/'company_interest_index.jsonl').open('w', encoding='utf-8') as f:
        for uid, lines in by_company.items():
            f.write(json.dumps(dict(company_id=uid, source_record_ids=[f'{uid}:line:{line}' for line in lines],
                status='conflicting_company_records_review_required' if uid in conflicts else 'single_record',
                merge_policy='separate_source_profiles_no_automatic_union'), ensure_ascii=False)+'\n')
    report = dict(version=VERSION, input_file=str(source.resolve()), input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        rule_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'company_rules').glob('*_rules.json'))},
        source_rows=len(rows), unique_companies=len(by_company), unique_activity_codes=len({r['MAINOKVED_CODE'] for r in rows}),
        unique_activity_contexts=len(by_activity), covered_divisions=len(divisions), catalog_topics=len(catalog),
        assigned_rows=sum(counts.values()), records_below_10=sum(n for size,n in counts.items() if size<10),
        minimum_topics=min(counts), maximum_topics=max(counts), distribution=dict(counts),
        duplicate_company_ids={uid:lines for uid,lines in by_company.items() if len(lines)>1},
        conflicting_company_ids=sorted(conflicts), missing_activity_records=0,
        method='Three subagents authored division-specific rules; every source record expanded deterministically using exact observed activity.',
        scope='All source rows, no revenue or segment filter.',
        not_measured=['semantic precision','actual user preference','news recommendation quality'],
        compatibility='Separate company-interests.v1 catalog; ci_ IDs do not belong to the earlier 10000 bt_ topic catalog.')
    dump(output/'company_interests_examples.json', sample_profiles)
    verify(source, output)
    report['validation_status'] = 'passed'
    report['total_assignments'] = sum(int(k)*v for k,v in report['distribution'].items())
    report['checks'] = ['all source rows preserved','minimum 10 distinct topics per record','exact activity code and name match','active product flag for every product topic','no duplicate topic names per record','complete unique-company index','CSV and JSONL record counts match']
    dump(output/'company_interests_validation.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def verify(source, output):
    with source.open(encoding='utf-8-sig', newline='') as f:
        source_rows=list(csv.DictReader(f, delimiter=';'))
    catalog={t['topic_id']:t for t in map(json.loads,(output/'activity_interest_catalog.jsonl').read_text().splitlines())}
    count=0
    with (output/'company_interests.jsonl').open() as f:
        for count, line in enumerate(f, 1):
            p=json.loads(line); r=source_rows[count-1]
            assert p['company_id']==r['SYNTHETIC_U']
            assert p['source_line']==count+1
            assert p['okved']==r['MAINOKVED_CODE'].strip()
            assert p['activity']==r['MAINOKVED_NAME'].strip()
            assert len(p['topic_ids'])==len(set(p['topic_ids']))==p['topic_count']>=10
            for tid in p['topic_ids']:
                t=catalog[tid]
                assert t['activity_code']==p['okved'] and t['activity_name']==p['activity']
                assert not t['required_flag'] or active(r.get(t['required_flag'],''))
            assert p['topic_names']==[catalog[tid]['name'] for tid in p['topic_ids']]
            assert len({n.casefold().replace('ё','е') for n in p['topic_names']})==p['topic_count']
    assert count==len(source_rows), (count,len(source_rows))
    with (output/'company_interests.csv').open(encoding='utf-8-sig',newline='') as f:
        assert sum(1 for _ in csv.DictReader(f))==count
    with (output/'company_interest_index.jsonl').open() as f:
        index=[json.loads(l) for l in f]
    assert {x['company_id'] for x in index}=={r['SYNTHETIC_U'] for r in source_rows}
    assert sum(len(x['source_record_ids']) for x in index)==count
    return count


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,default=ROOT/'output/company_interests')
    p.add_argument('--verify-only',action='store_true')
    args=p.parse_args()
    if args.verify_only:
        print('Verified records:',verify(args.source,args.output))
    else:
        assign(args.source,args.output)
