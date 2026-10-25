"""Export company demand without treating inferred interests as observed preferences."""
import csv
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/company_topic_demand'
OUT.mkdir(exist_ok=True)
db = sqlite3.connect(ROOT / 'output/okved_topic_mapping/okved_topics.sqlite')
topics = [json.loads(line) for line in open(ROOT / 'output/business_topics.jsonl')]
companies = defaultdict(set)
for uid, code in db.execute('select distinct company_id,okved from companies'):
    companies[code].add(uid)
relations = ['declared_activity', 'activity_scope_candidate', 'operating_exposure']
links = defaultdict(lambda: defaultdict(set))
for topic, code, relation in db.execute('select distinct topic_id,okved,relation from mapping'):
    links[topic][relation].add(code)

def counts(mapping):
    groups = [{uid for code in mapping.get(r, ()) for uid in companies[code]} for r in relations]
    total = set().union(*groups)
    return [len(total), *map(len, groups), ', '.join(sorted(total)[:5])]

def save(name, header, rows):
    with open(OUT / name, 'w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream, delimiter=';')
        writer.writerow(header)
        writer.writerows(rows)

count_headers = ['Компаний всего', 'Прямая деятельность по ОКВЭД', 'Возможная специализация', 'Косвенный операционный интерес', 'Примеры ID компаний']
rows = []
family_links = defaultdict(lambda: defaultdict(set))
family_members = defaultdict(list)
for t in topics:
    rows.append([t['topic_id'], t['name'], t['sector_name'], t['object'], t['signal'], *counts(links[t['topic_id']])])
    key = (t['sector_id'], t['sector_name'], t['object'])
    family_members[key].append(t['topic_id'])
    for relation, codes in links[t['topic_id']].items():
        family_links[key][relation].update(codes)
rows.sort(key=lambda r: (-r[6], -r[5], r[1]))
header = ['ID темы', 'Тема', 'Отрасль', 'Объект', 'Событие', *count_headers]
save('all_10000_topics.csv', header, rows)
save('topics_with_company_interest.csv', header, [r for r in rows if r[5]])
family_rows = [[key[0] + '::' + key[2], key[1], key[2], *counts(family_links[key]), ', '.join(family_members[key])] for key in family_members]
family_rows.sort(key=lambda r: (-r[4], -r[3], r[2]))
save('objects_company_interest.csv', ['ID группы', 'Отрасль', 'Объект', *count_headers, 'Входящие ID тем'], family_rows)
binding_rows = list(db.execute('select distinct m.okved,a.activity,m.topic_id,t.name,m.relation,b.reason from mapping m join topics t using(topic_id) join activities a using(okved) join bindings b using(binding_id) order by m.okved,m.topic_id'))
save('okved_topic_reasons.csv', ['ОКВЭД', 'Деятельность', 'ID темы', 'Тема', 'Тип связи', 'Почему связаны'], binding_rows)
summary = {'topics': len(rows), 'topics_with_companies': sum(bool(r[5]) for r in rows), 'object_groups': len(family_rows), 'object_groups_with_companies': sum(bool(r[3]) for r in family_rows), 'unique_company_ids': db.execute('select count(distinct company_id) from companies').fetchone()[0], 'okved_topic_reason_rows': len(binding_rows)}
(OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
(OUT / 'README.txt').write_text('''КАК ЧИТАТЬ ВЫГРУЗКУ
Начните с objects_company_interest.csv: одна строка — объект (например, пшеница), без разделения на события роста, падения и т.п. Удобно для проверки покрытия новостями.
topics_with_company_interest.csv — только темы, связанные хотя бы с одной компанией.
all_10000_topics.csv — весь исходный словарь, включая темы без компаний.
okved_topic_reasons.csv — объяснение каждой связи ОКВЭД с темой.

Числа — уникальные ID компаний, а не исходные записи. Сначала сортируем по числу компаний с прямой деятельностью, затем по общему числу.
Прямая деятельность: тема соответствует формулировке ОКВЭД. Возможная специализация: код допускает это направление, но конкретная специализация компании неизвестна. Косвенный интерес: тема может влиять на работу компании, но не описывает ее деятельность.
Это предполагаемые интересы по ОКВЭД, а не подтвержденные предпочтения пользователей. Платежные связи и персональные роли в эту выгрузку не включены.
Компании могут входить в несколько категорий: их количества нельзя складывать. У одного ID есть конфликтующие профили; он учитывается по всем имеющимся ОКВЭД.
Пять ID — только примеры, не полный список компаний. Полный индекс находится в ../okved_topic_mapping/company_topic_index.csv.
Нулевое количество присвоенных новостям меток не доказывает отсутствия новостей по теме: разметка новостей еще проверяется. В этой выгрузке представлены потребности компаний, а не окончательные пробелы новостного покрытия.
CSV: UTF-8 с BOM, разделитель — точка с запятой. Источники: business_topics.jsonl и okved_topic_mapping/okved_topics.sqlite.
''', encoding='utf-8')
assert len(rows) == 10000 and len(family_rows) == 1000
assert all(max(r[6:9]) <= r[5] for r in rows)
print(json.dumps(summary, ensure_ascii=False))
