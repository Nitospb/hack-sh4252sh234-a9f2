"""Independent streaming integrity verification of relationship interest exports."""
import argparse
import csv
import json
import math
import sqlite3
from collections import Counter, defaultdict
from decimal import Decimal
from itertools import zip_longest
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        yield from csv.DictReader(f, delimiter=';')

def lines(path):
    with path.open(encoding='utf-8') as f:
        for line in f:
            yield json.loads(line)

def verify(source, output, base):
    errors = Counter(); samples = []; stats = Counter()
    def check(condition, name, detail=''):
        if not condition:
            errors[name] += 1
            if len(samples) < 40:
                samples.append(dict(check=name, detail=str(detail)))
    metadata = []; profiles = defaultdict(set); groups = defaultdict(set)
    for line, r in enumerate(rows(source/'df_Uid_data_hack.csv'), 2):
        uid = r['SYNTHETIC_U']; record = uid+':line:'+str(line)
        context = (r['MAINOKVED_CODE'].strip(), r['MAINOKVED_NAME'].strip(), r['REGION'])
        metadata.append((record, uid, context, r['GROUP_ID']))
        profiles[uid].add(context)
        if r['GROUP_ID']: groups[r['GROUP_ID']].add(uid)
    conflicts = {u for u, contexts in profiles.items() if len(contexts)>1}
    people = defaultdict(set)
    for r in rows(source/'df_Fid_Uid_link_hack.csv'):
        people[r['SYNTHETIC_F']].add(r['SYNTHETIC_U'])
    catalog = {r['topic_id']: r for r in lines(base/'activity_interest_catalog.jsonl')}
    check(catalog == {r['topic_id']: r for r in lines(output/'interest_catalog.jsonl')}, 'catalog_copy_matches')
    # Independent Decimal totals include unprofiled counterparties and exclude self payments.
    totals = defaultdict(lambda: [Decimal(0), 0, Decimal(0), 0])
    for r in rows(source/'df_Uid_payment_hack.csv'):
        payer, beneficiary = r['PAYER'], r['BENEFICIARY']
        a, c = Decimal(r['PAY_AMT']), Decimal(r['PAY_CNT'])
        if payer == beneficiary or not a.is_finite() or not c.is_finite() or a<=0 or c<=0 or c!=int(c): continue
        if payer in profiles: totals[payer][0]+=a; totals[payer][1]+=int(c)
        if beneficiary in profiles: totals[beneficiary][2]+=a; totals[beneficiary][3]+=int(c)
    temp = output/'verify_relationships.sqlite'
    if temp.exists(): temp.unlink()
    db = sqlite3.connect(str(temp)); db.execute('PRAGMA journal_mode=OFF'); db.execute('PRAGMA synchronous=OFF')
    db.execute('CREATE TABLE links(rid TEXT PRIMARY KEY, record TEXT, uid TEXT, topics TEXT, used INTEGER DEFAULT 0)')
    payment = sqlite3.connect('file:'+str((output/'payment_graph.sqlite').resolve())+'?mode=ro', uri=True)
    # Track only selected payment pairs; validate their exact source aggregates in a second source pass.
    selected_payments = {}; record_metadata = {m[0]:m for m in metadata}
    for link in lines(output/'relationships.jsonl'):
        stats['relationship_rows']+=1
        rid, record, uid, peer = (link[k] for k in ('relationship_id','source_record_id','company_id','related_company_id'))
        check(record in record_metadata and record_metadata[record][1]==uid, 'relationship_source_record', rid)
        check(uid!=peer, 'no_self_relationship', rid)
        check(peer in profiles and peer not in conflicts, 'peer_has_unambiguous_profile', rid)
        if peer in profiles and peer not in conflicts:
            context = next(iter(profiles[peer]))
            check((link['related_okved'],link['related_activity'])==context[:2], 'peer_context', rid)
        else: context = (None,None,None)
        tids = link['topic_ids']
        for tid in tids:
            check(tid in catalog, 'relationship_topic_exists', tid)
            if tid in catalog:
                t=catalog[tid]
                check(not t.get('required_flag'), 'no_counterparty_product_topic', rid)
                check((t['activity_code'],t['activity_name'])==context[:2], 'topic_matches_exact_peer_activity', rid)
        check(link['topic_names']==[catalog[t]['name'] for t in tids if t in catalog], 'relationship_topic_names', rid)
        evidence, kind = link['evidence'], link['kind']
        stats['kind_'+kind]+=1
        if kind in ('outgoing_payment','incoming_payment'):
            pair = (uid,peer) if kind=='outgoing_payment' else (peer,uid)
            check((evidence['payer'],evidence['beneficiary'])==pair, 'payment_direction', rid)
            found=payment.execute('SELECT amount,payment_count,source_rows FROM payments WHERE payer=? AND beneficiary=?',pair).fetchone()
            check(found is not None, 'payment_pair_exists', rid)
            if found:
                check(Decimal(link['amount'])==Decimal(found[0]) and link['payment_count']==found[1] and evidence['source_rows']==found[2], 'payment_exact_graph_values', rid)
                selected_payments[pair]=(Decimal(found[0]),found[1],found[2])
            offset=0 if kind=='outgoing_payment' else 2
            amount,count=totals[uid][offset:offset+2]
            check(Decimal(evidence['all_direction_amount'])==amount and evidence['all_direction_payment_count']==count, 'direction_denominator_matches_source', rid)
            check(amount>0 and math.isclose(link['direction_amount_share'],float(Decimal(link['amount'])/amount),rel_tol=1e-12,abs_tol=1e-15), 'amount_share', rid)
            check(count>0 and math.isclose(link['direction_count_share'],link['payment_count']/count,rel_tol=1e-12,abs_tol=1e-15), 'count_share', rid)
        elif kind=='shared_person':
            members=people.get(evidence['shared_person_id'],set())
            check(uid in members and peer in members, 'shared_person_real_both_members', rid)
            check(evidence['person_degree']==len(members), 'person_degree', rid)
        elif kind=='same_group':
            group=evidence['shared_group_id']
            check(record in record_metadata and record_metadata[record][3]==group and peer in groups[group], 'exact_source_record_group_membership', rid)
            check(evidence['group_size']==len(groups[group]), 'group_size', rid)
        else: check(False,'known_relationship_kind',kind)
        try: db.execute('INSERT INTO links(rid,record,uid,topics) VALUES(?,?,?,?)',(rid,record,uid,json.dumps(tids)))
        except sqlite3.IntegrityError: check(False,'unique_relationship_id',rid)
    db.commit(); payment.close()
    # Confirm selected graph pairs independently against raw source, including duplicate aggregation.
    aggregates = defaultdict(lambda:[Decimal(0),0,0])
    for r in rows(source/'df_Uid_payment_hack.csv'):
        pair=(r['PAYER'],r['BENEFICIARY'])
        if pair in selected_payments:
            a=aggregates[pair];a[0]+=Decimal(r['PAY_AMT']);a[1]+=int(Decimal(r['PAY_CNT']));a[2]+=1
    for pair, expected in selected_payments.items(): check(tuple(aggregates[pair])==expected,'selected_graph_pair_matches_raw_source',pair)
    seen_uids=set(); seen_records=set()
    for expected, original, enriched in zip_longest(metadata,lines(base/'company_interests.jsonl'),lines(output/'company_interests_enriched.jsonl')):
        stats['company_rows']+=1
        if expected is None or original is None or enriched is None:
            check(False,'same_company_row_count'); continue
        record,uid,context,group=expected
        check(original['source_record_id']==enriched['source_record_id']==record, 'source_record_order_preserved',record)
        check(original['company_id']==enriched['company_id']==uid, 'source_company_preserved',record)
        check((enriched['okved'],enriched['activity'])==context[:2], 'own_activity_preserved',record)
        check(record not in seen_records, 'unique_source_record_id',record)
        seen_records.add(record);seen_uids.add(uid)
        tids=set(enriched['topic_ids']);own=set(original['topic_ids'])
        check(own<=tids,'original_own_topics_preserved',record)
        check(tids<=catalog.keys(),'company_topics_exist',record)
        check(len(tids)==len(enriched['topic_ids'])==enriched['total_topic_count'],'company_topic_count',record)
        check(enriched['own_topic_count']==len(own),'own_topic_count',record)
        linked=set();related=set();topic_links=defaultdict(set)
        for rid in enriched['relationship_ids']:
            found=db.execute('SELECT record,uid,topics FROM links WHERE rid=?',(rid,)).fetchone()
            check(found is not None,'referenced_relationship_exists',rid)
            if not found: continue
            check(found[:2]==(record,uid),'relationship_belongs_to_record',rid)
            linked.add(rid);peer_topics=json.loads(found[2]);related.update(peer_topics)
            for tid in peer_topics:topic_links[tid].add(rid)
            db.execute('UPDATE links SET used=used+1 WHERE rid=?',(rid,))
        check(tids==own|related,'exact_own_plus_related_topic_union',record)
        check(enriched['related_topic_count']==len(related-own),'related_topic_count',record)
        check(len(enriched['interests'])==len(tids),'interest_assignment_count',record)
        for assignment in enriched['interests']:
            tid=assignment['topic_id']
            check(tid in tids and assignment['own_interest']==(tid in own),'interest_assignment_origin',record)
            check(set(assignment['relationship_ids'])==topic_links[tid],'interest_relationship_evidence',record)
        check(enriched['group_id']==group,'enriched_group_matches_source_row',record)
    check(seen_uids==set(profiles),'all_source_company_ids_preserved')
    orphan=db.execute('SELECT count(*) FROM links WHERE used!=1').fetchone()[0]
    check(orphan==0,'all_relationships_referenced_once',orphan)
    db.close();temp.unlink()
    report=dict(status='passed' if not errors else 'failed',checks='independent_streaming_source_and_export_integrity',stats=dict(stats),unique_company_ids=len(seen_uids),source_record_ids=len(seen_records),conflicting_ids=sorted(conflicts),selected_payment_pairs_verified=len(selected_payments),error_counts=dict(errors),error_samples=samples)
    (output/'verify_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return not errors

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-dir',type=Path,required=True);p.add_argument('--output',type=Path,default=ROOT/'output/relationship_interests');p.add_argument('--base-dir',type=Path,default=ROOT/'output/company_interests')
    a=p.parse_args();raise SystemExit(0 if verify(a.source_dir,a.output,a.base_dir) else 1)
