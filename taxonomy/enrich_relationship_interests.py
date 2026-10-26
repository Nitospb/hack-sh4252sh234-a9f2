"""Explainable graph-based interest propagation; no supplier/customer role claims."""
import argparse
import csv
import hashlib
import heapq
import json
import math
import sqlite3
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = 'company-relationship-interests.v1'
TOP_PER_KIND = 2
ASPECTS_PER_LINK = 4


def jid(prefix, *values):
    return prefix+'_'+hashlib.sha256('|'.join(map(str, values)).encode()).hexdigest()[:16]


def dump(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def read_rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        yield from csv.DictReader(f,delimiter=';')


def push(heap, score, peer, payload, limit=TOP_PER_KIND):
    entry=(score,peer,payload)
    if len(heap)<limit:
        heapq.heappush(heap,entry)
    elif entry[:2]>heap[0][:2]:
        heapq.heapreplace(heap,entry)


def payment_score(amount, count, total_amount, total_count):
    return .75*float(amount/total_amount)+.25*count/total_count


def prepare_payments(path, db_path, known, conflicts):
    if db_path.exists():
        db_path.unlink()
    db=sqlite3.connect(db_path)
    db.execute('PRAGMA journal_mode=OFF')
    db.execute('PRAGMA synchronous=OFF')
    db.create_function('decimal_add',2,lambda a,b:str(Decimal(a)+Decimal(b)))
    db.execute('CREATE TABLE payments(payer TEXT,beneficiary TEXT,amount TEXT,payment_count INTEGER,source_rows INTEGER,PRIMARY KEY(payer,beneficiary)) WITHOUT ROWID')
    # Totals include all eligible peers, even peers without an activity profile.
    totals=defaultdict(lambda:dict(out_amount=Decimal(0),in_amount=Decimal(0),out_count=0,in_count=0,
                                  out_peers=0,in_peers=0,out_profiled_amount=Decimal(0),in_profiled_amount=Decimal(0)))
    stats=Counter();batch=[]
    sql='INSERT INTO payments VALUES(?,?,?,?,1) ON CONFLICT(payer,beneficiary) DO UPDATE SET amount=decimal_add(amount,excluded.amount),payment_count=payment_count+excluded.payment_count,source_rows=source_rows+1'
    for r in read_rows(path):
        stats['source_payment_rows']+=1
        payer,beneficiary=r['PAYER'],r['BENEFICIARY']
        amount=Decimal(r['PAY_AMT']);count=Decimal(r['PAY_CNT'])
        if not amount.is_finite() or not count.is_finite() or amount<=0 or count<=0 or count!=int(count):
            stats['excluded_invalid_payment_rows']+=1
            continue
        if payer==beneficiary:
            stats['excluded_self_payment_rows']+=1
            continue
        count=int(count);batch.append((payer,beneficiary,str(amount),count))
        if payer in known:
            totals[payer]['out_amount']+=amount;totals[payer]['out_count']+=count
        if beneficiary in known:
            totals[beneficiary]['in_amount']+=amount;totals[beneficiary]['in_count']+=count
        if len(batch)>=10000:
            db.executemany(sql,batch);batch=[]
    if batch:db.executemany(sql,batch)
    db.commit()
    outgoing=defaultdict(list);incoming=defaultdict(list)
    for payer,beneficiary,raw,count,source_rows in db.execute('SELECT * FROM payments'):
        stats['aggregated_nonself_pairs']+=1
        amount=Decimal(raw)
        if source_rows>1:stats['duplicate_rows_aggregated']+=source_rows-1
        if payer in known:
            total=totals[payer];total['out_peers']+=1
            if beneficiary in known and beneficiary not in conflicts:
                total['out_profiled_amount']+=amount
                score=payment_score(amount,count,total['out_amount'],total['out_count'])
                push(outgoing[payer],score,beneficiary,(raw,count,source_rows))
        if beneficiary in known:
            total=totals[beneficiary];total['in_peers']+=1
            if payer in known and payer not in conflicts:
                total['in_profiled_amount']+=amount
                score=payment_score(amount,count,total['in_amount'],total['in_count'])
                push(incoming[beneficiary],score,payer,(raw,count,source_rows))
    db.execute('CREATE INDEX payments_beneficiary ON payments(beneficiary)')
    db.commit();db.close()
    return totals,outgoing,incoming,stats


def selected_context_peers(uid, members, profiles, limit=TOP_PER_KIND):
    """Represent largest observed activity clusters; selection is not economic importance."""
    eligible=[peer for peer in members if peer!=uid and peer in profiles]
    counts=Counter(profiles[p]['code'] for p in eligible)
    representatives={}
    for peer in sorted(eligible):
        representatives.setdefault(profiles[peer]['code'],peer)
    ordered=sorted(representatives,key=lambda c:(-counts[c],c))
    chosen=[(representatives[c],counts[c]) for c in ordered[:limit]]
    return chosen,len(eligible),len(counts)


def select_topics(peer, kind, catalog_by_context, selector, override_codes):
    code,activity=peer['code'],peer['activity']
    available=catalog_by_context[(code,activity)]
    mode=kind if kind in ('outgoing_payment','incoming_payment') else 'related_company'
    keys=selector[code[:2]][mode]
    # Override keys are positional in the source rules, not semantic equivalents.
    if code in override_codes:
        return list(available.values())[:ASPECTS_PER_LINK]
    selected=[available[k] for k in keys if k in available]
    selected += [tid for tid in available.values() if tid not in selected]
    return selected[:ASPECTS_PER_LINK]


def format_explanation(policy, kind, uid, peer_id, activity, share=None, amount=None, count=None):
    return policy[kind]['impact_template'].format(company_id=uid,related_company_id=peer_id,
        activity=activity,share_pct=f'{100*share:.2f}' if share is not None else '',
        amount=amount or '',count=count or '')


def build(source_dir, output, base_dir):
    output.mkdir(parents=True,exist_ok=True)
    source=source_dir/'df_Uid_data_hack.csv'
    metadata=[];all_by_id=defaultdict(list);groups=defaultdict(set)
    for line,r in enumerate(read_rows(source),2):
        m=dict(uid=r['SYNTHETIC_U'],code=r['MAINOKVED_CODE'].strip(),activity=r['MAINOKVED_NAME'].strip(),
               group=r['GROUP_ID'],region=r['REGION'],line=line)
        metadata.append(m);all_by_id[m['uid']].append(m)
        if m['group']:groups[m['group']].add(m['uid'])
    conflicts={u for u,rows in all_by_id.items() if len({(r['code'],r['activity'],r['region']) for r in rows})>1}
    profiles={u:rows[0] for u,rows in all_by_id.items() if u not in conflicts}
    known=set(all_by_id)
    person_companies=defaultdict(set);company_people=defaultdict(set)
    for r in read_rows(source_dir/'df_Fid_Uid_link_hack.csv'):
        person_companies[r['SYNTHETIC_F']].add(r['SYNTHETIC_U'])
        company_people[r['SYNTHETIC_U']].add(r['SYNTHETIC_F'])
    catalog={};catalog_by_context=defaultdict(dict)
    with (base_dir/'activity_interest_catalog.jsonl').open() as f:
        for line in f:
            t=json.loads(line);catalog[t['topic_id']]=t
            if not t.get('required_flag'):
                catalog_by_context[(t['activity_code'],t['activity_name'])][t['aspect_key']]=t['topic_id']
    selector=json.loads((ROOT/'relation_aspect_selection.json').read_text())
    policy=json.loads((ROOT/'relation_policy.json').read_text())
    override_codes=set()
    for p in (ROOT/'company_rules').glob('*_rules.json'):
        for r in json.loads(p.read_text()).values():override_codes.update(r.get('overrides',{}))
    totals,outgoing,incoming,payment_stats=prepare_payments(source_dir/'df_Uid_payment_hack.csv',output/'payment_graph.sqlite',known,conflicts)
    print('Payment graph prepared:',dict(payment_stats),flush=True)
    stats=Counter();distribution=Counter();examples=[];seen_ids=set();example_kinds=set()
    link_fields=['relationship_id','source_record_id','company_id','related_company_id','kind','observed_label','possible_role','related_okved','related_activity','amount','payment_count','direction_amount_share','direction_count_share','ranking_weight','why_interesting','role_caveat','topic_ids','topic_names','evidence']
    company_fields=['source_record_id','company_id','okved','activity','own_topic_count','related_topic_count','total_topic_count','topic_ids','topic_names','relationship_ids','status']
    with (base_dir/'company_interests.jsonl').open() as base, (output/'company_interests_enriched.jsonl').open('w') as jf, (output/'company_interests_enriched.csv').open('w',encoding='utf-8-sig',newline='') as cf, (output/'relationships.jsonl').open('w') as rf, (output/'relationships.csv').open('w',encoding='utf-8-sig',newline='') as rcf:
        cw=csv.DictWriter(cf,fieldnames=company_fields);cw.writeheader()
        rw=csv.DictWriter(rcf,fieldnames=link_fields);rw.writeheader()
        for row_number,line in enumerate(base):
            original=json.loads(line);m=metadata[row_number];uid=m['uid'];record_id=original['source_record_id']
            assert original['company_id']==uid and original['okved']==m['code'] and original['activity']==m['activity']
            links=[]
            for kind,heaps,direction in [('outgoing_payment',outgoing,'out'),('incoming_payment',incoming,'in')]:
                t=totals[uid]
                for selection_score,peer_id,(amount,count,source_rows) in sorted(heaps.get(uid,[]),reverse=True):
                    share=float(Decimal(amount)/t[direction+'_amount']);count_share=count/t[direction+'_count']
                    links.append(dict(kind=kind,peer=peer_id,amount=amount,payment_count=count,
                        direction_amount_share=share,direction_count_share=count_share,ranking_weight=.6+.4*selection_score,
                        evidence={'table':'df_Uid_payment_hack.csv','payer':uid if direction=='out' else peer_id,
                            'beneficiary':peer_id if direction=='out' else uid,'source_rows':source_rows,
                            'all_direction_amount':str(t[direction+'_amount']),'all_direction_payment_count':t[direction+'_count'],
                            'units_and_period':'not specified','role_status':'possible_not_verified'}))
            person_candidates=[]
            for person in sorted(company_people.get(uid,[])):
                members=person_companies[person]
                peers,pool,activities=selected_context_peers(uid,members,profiles)
                for peer_id,support in peers:
                    person_candidates.append((.25/math.sqrt(max(1,len(members)-1)),person,peer_id,pool,activities,len(members),support))
            used_peers=set()
            for weight,person,peer_id,pool,activities,degree,support in sorted(person_candidates,reverse=True):
                if peer_id in used_peers:continue
                used_peers.add(peer_id)
                links.append(dict(kind='shared_person',peer=peer_id,ranking_weight=weight,
                    evidence={'table':'df_Fid_Uid_link_hack.csv','shared_person_id':person,'person_degree':degree,
                        'eligible_related_companies':pool,'related_activity_count':activities,'same_activity_support':support,
                        'selection':'representative_of_largest_activity_cluster_then_id_tiebreak',
                        'ownership_or_role':'unknown'}))
                if len(used_peers)>=TOP_PER_KIND:break
            if m['group']:
                members=groups[m['group']];peers,pool,activities=selected_context_peers(uid,members,profiles)
                for peer_id,support in peers:
                    links.append(dict(kind='same_group',peer=peer_id,ranking_weight=.1/math.sqrt(max(1,len(members)-1)),
                        evidence={'table':'df_Uid_data_hack.csv','shared_group_id':m['group'],'group_size':len(members),
                            'eligible_related_companies':pool,'related_activity_count':activities,'same_activity_support':support,
                            'selection':'representative_of_largest_activity_cluster_then_id_tiebreak',
                            'legal_or_financial_liability':'not established'}))
            assignments={tid:dict(topic_id=tid,own_interest=True,relationship_ids=[],ranking_weight=1.0) for tid in original['topic_ids']}
            for link in links:
                peer=profiles[link['peer']];kind=link['kind']
                tids=select_topics(peer,kind,catalog_by_context,selector,override_codes)
                rid=jid('rel',record_id,kind,link['peer'],json.dumps(link['evidence'],sort_keys=True))
                description=format_explanation(policy,kind,uid,link['peer'],peer['activity'],link.get('direction_amount_share'),link.get('amount'),link.get('payment_count'))
                output_link=dict(relationship_id=rid,source_record_id=record_id,company_id=uid,
                    related_company_id=link['peer'],kind=kind,observed_label=policy[kind]['observed_label'],
                    possible_role=policy[kind]['possible_role'],role_caveat=policy[kind]['role_caveat'],
                    related_okved=peer['code'],related_activity=peer['activity'],
                    amount=link.get('amount'),payment_count=link.get('payment_count'),
                    direction_amount_share=link.get('direction_amount_share'),direction_count_share=link.get('direction_count_share'),
                    ranking_weight=round(link['ranking_weight'],8),why_interesting=description,
                    topic_ids=tids,topic_names=[catalog[t]['name'] for t in tids],evidence=link['evidence'])
                rf.write(json.dumps(output_link,ensure_ascii=False)+'\n')
                rw.writerow({k:json.dumps(output_link[k],ensure_ascii=False) if isinstance(output_link[k],(list,dict)) else output_link[k] for k in link_fields})
                link['relationship_id']=rid;link['topic_ids']=tids;link['description']=description
                stats['relationships_'+kind]+=1
                for tid in tids:
                    a=assignments.setdefault(tid,dict(topic_id=tid,own_interest=False,relationship_ids=[],ranking_weight=0))
                    a['relationship_ids'].append(rid);a['ranking_weight']=max(a['ranking_weight'],round(link['ranking_weight'],8))
                if kind not in example_kinds and len(examples)<12:
                    examples.append({'source_record_id':record_id,'company_id':uid,'own_activity':m['activity'],'relationship':output_link})
                    example_kinds.add(kind)
            own_count=len(original['topic_ids']);related_count=sum(not t['own_interest'] for t in assignments.values())
            t=totals[uid]
            flow={k:str(v) if isinstance(v,Decimal) else v for k,v in t.items()}
            flow.update(out_profiled_amount_share=float(t['out_profiled_amount']/t['out_amount']) if t['out_amount'] else None,
                        in_profiled_amount_share=float(t['in_profiled_amount']/t['in_amount']) if t['in_amount'] else None)
            record=dict(source_record_id=record_id,company_id=uid,okved=m['code'],activity=m['activity'],
                region=m['region'],own_topic_count=own_count,related_topic_count=related_count,total_topic_count=len(assignments),
                topic_ids=list(assignments),interests=list(assignments.values()),relationship_ids=[l['relationship_id'] for l in links],
                observed_flow_summary=flow,shared_person_ids=sorted(company_people.get(uid,[])),group_id=m['group'],
                group_size=len(groups[m['group']]) if m['group'] else 0,
                relationship_selection={'limit_per_kind':TOP_PER_KIND,'topics_per_relationship':ASPECTS_PER_LINK,
                    'outgoing_profiled_peers_selected':len(outgoing.get(uid,[])),
                    'incoming_profiled_peers_selected':len(incoming.get(uid,[])),
                    'full_nonself_payment_graph':'payment_graph.sqlite',
                    'group_and_person_selection':'bounded_activity_cluster_representatives_not_economic_ranking'},
                status=original['status'],version=VERSION,
                relation_status='inferred_indirect_interests' if links else 'no_usable_profiled_relationship_found')
            jf.write(json.dumps(record,ensure_ascii=False)+'\n')
            csv_record={**record,'topic_names':[catalog[tid]['name'] for tid in record['topic_ids']]}
            cw.writerow({k:json.dumps(csv_record[k],ensure_ascii=False) if isinstance(csv_record[k],list) else csv_record[k] for k in company_fields})
            stats['source_records']+=1;stats['records_with_selected_relationships']+=bool(links)
            stats['records_with_new_related_topics']+=related_count>0
            stats['own_topic_assignments']+=own_count;stats['new_related_topic_assignments']+=related_count
            stats['records_without_observed_payments']+=not(t['out_count'] or t['in_count'])
            stats['records_below_10']+=len(assignments)<10
            distribution[len(assignments)]+=1;seen_ids.add(uid)
    assert stats['source_records']==len(metadata) and seen_ids==known
    assert stats['records_below_10']==0
    # Copy the normalized dictionary, not the large prior company files.
    (output/'interest_catalog.jsonl').write_bytes((base_dir/'activity_interest_catalog.jsonl').read_bytes())
    dump(output/'relationship_examples.json',examples)
    report=dict(version=VERSION,validation_status='generation_checks_passed',unique_companies=len(known),
        source_records=len(metadata),conflicting_company_ids=sorted(conflicts),stats=stats,payment_stats=payment_stats,
        topic_count_distribution=dict(sorted(distribution.items())),min_topics=min(distribution),max_topics=max(distribution),
        selection={'per_kind':TOP_PER_KIND,'aspects_per_link':ASPECTS_PER_LINK,'payment_rank':'.75*direction_amount_share + .25*direction_count_share',
            'person_weight':'.25/sqrt(person_degree-1)','group_weight':'.1/sqrt(group_size-1)'},
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source_dir.glob('*.csv'))},
        rule_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'relation_policy.json',ROOT/'relation_aspect_selection.json']},
        limitations=['Supplier/customer roles are hypotheses; observed direction is certain.',
            'Missing or conflicting activity profiles are excluded from topic propagation, not from payment denominators.',
            'Only selected relationships propagate topics; full aggregated nonself payments remain in SQLite.',
            'Shared person/group membership does not establish ownership or economic dependency.',
            'Ranking weights are heuristics, not probabilities or measured business impact.',
            'Unknown payment period/currency; no comparison to revenue.',
            'No individual LLM call per company; subagent-authored rules applied to all source records.'])
    dump(output/'validation.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,default=ROOT/'output/relationship_interests')
    p.add_argument('--base-dir',type=Path,default=ROOT/'output/company_interests')
    a=p.parse_args();build(a.source_dir,a.output,a.base_dir)
