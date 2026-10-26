"""Compact business context derived from declared activities and observed relationships."""
import json
import math
import sqlite3
from pathlib import Path

# Readable groupings for navigation; the original OKVED and activity stay available.
GROUPS=[(1,1,'Сельское хозяйство'),(2,2,'Лесное хозяйство'),(3,3,'Рыболовство'),
 (5,9,'Добыча полезных ископаемых'),(10,12,'Пищевая промышленность'),(13,15,'Лёгкая промышленность'),
 (16,18,'Деревообработка и полиграфия'),(19,22,'Нефтепереработка и химия'),(23,25,'Материалы и металлургия'),
 (26,33,'Промышленное производство'),(35,35,'Энергетика'),(36,39,'Коммунальное хозяйство'),
 (41,43,'Строительство'),(45,47,'Торговля'),(49,53,'Транспорт и логистика'),(55,56,'Гостиницы и общепит'),
 (58,60,'Медиа и издательское дело'),(61,61,'Телекоммуникации'),(62,63,'IT и технологии'),
 (64,66,'Финансы и страхование'),(68,68,'Недвижимость'),(69,75,'Профессиональные услуги'),
 (77,82,'Услуги для бизнеса'),(84,84,'Государственное управление'),(85,85,'Образование'),
 (86,88,'Здравоохранение и социальные услуги'),(90,93,'Культура, спорт и отдых'),(94,99,'Прочие услуги')]

def broad_activity(code, fallback='Деятельность не указана'):
    try:number=int(str(code).split('.')[0])
    except (ValueError,TypeError):return fallback
    return next((label for lo,hi,label in GROUPS if lo<=number<=hi),fallback)

def business_context(assets, company):
    result={'activity_group':broad_activity(company.get('okved'),company.get('activity') or 'Деятельность не указана'),'partner_sectors':[]}
    if not Path(assets).is_file():return result
    with sqlite3.connect(Path(assets).resolve().as_uri()+'?mode=ro',uri=True) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='relationships'").fetchone():return result
        rows=db.execute('SELECT payload FROM relationships WHERE record_id=?',(company['source_record_id'],)).fetchall()
    sectors={}
    for row in rows:
        item=json.loads(row[0]);kind=item.get('kind')
        if kind not in ('incoming_payment','outgoing_payment','same_group'):continue
        label=broad_activity(item.get('related_okved'),item.get('related_activity') or 'Неизвестная деятельность')
        if label=='Неизвестная деятельность':continue
        sector=sectors.setdefault(label,{'label':label,'relationship_count':0,'kinds':set(),'related_company_ids':set(),'_priority':0,'_share':0.})
        sector['relationship_count']+=1;sector['kinds'].add(kind)
        if item.get('related_company_id'):sector['related_company_ids'].add(item['related_company_id'])
        share=item.get('direction_amount_share')
        if isinstance(share,(float,int)) and math.isfinite(share):sector['_share']=max(sector['_share'],max(0.,min(1.,share)))
        sector['_priority']=max(sector['_priority'],int(kind!='same_group'))
    selected=sorted(sectors.values(),key=lambda s:(-s['_priority'],-s['_share'],-len(s['related_company_ids']),s['label']))[:2]
    result['partner_sectors']=[{'label':s['label'],'relationship_count':s['relationship_count'],'kinds':sorted(s['kinds']),'company_count':len(s['related_company_ids'])} for s in selected]
    return result
