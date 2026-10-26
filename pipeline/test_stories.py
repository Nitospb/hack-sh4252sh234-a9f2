import unittest
import numpy as np
from pipeline.stories import group,quantities


def record(aid,title,day='2026-10-26',text='Ставка снижена до 15%.',kind='news'):
    return {'article_id':aid,'title':title,'text':text,'published_at':day+'T12:00:00Z','kind':kind,'content_hash':aid,'text_hash':aid}


class StoryTests(unittest.TestCase):
    def test_same_event_groups_without_rewriting_ids_and_keeps_anchor(self):
        rows=[record('a','ЦБ снизил ключевую ставку до 15%'),record('b','Центробанк снизил ключевую ставку до 15%')]
        vec=np.ones(384)/np.sqrt(384);vectors={a['article_id']:vec for a in rows}
        groups,members,_=group(rows,vectors)
        self.assertEqual(len(groups),1);sid=members['a']['story_id']
        self.assertEqual(members['b']['story_id'],sid)
        added=record('earlier','Центробанк снизил ключевую ставку до 15%')
        groups,members,_=group([added,*rows],{**vectors,'earlier':vec},{'a':sid})
        self.assertEqual(members['earlier']['story_id'],sid);self.assertEqual(groups[sid]['anchor'],'a')

    def test_distinct_episode_and_telegram_do_not_merge(self):
        rows=[record('a','ЦБ снизил ключевую ставку'),record('b','ЦБ снизил ключевую ставку','2026-10-20'),
              record('tg','ЦБ снизил ключевую ставку',kind='telegram_post')]
        vec=np.ones(384)/np.sqrt(384)
        self.assertEqual(len(group(rows,{r['article_id']:vec for r in rows})[0]),3)

    def test_numeric_variants_are_visible_and_never_silently_deduplicated(self):
        rows=[record('a','ЦБ снизил ключевую ставку до 15%'),record('b','ЦБ снизил ключевую ставку до 15%',text='Ставка снижена до 16%.')]
        vec=np.ones(384)/np.sqrt(384)
        groups,members,numbers=group(rows,{r['article_id']:vec for r in rows})
        self.assertEqual(len(groups),1);self.assertFalse(next(iter(groups.values()))['dedup_safe'])
        self.assertEqual(numbers['a'][0]['value'],'15');self.assertEqual(numbers['b'][0]['value'],'16')
        for r in rows:
            n=numbers[r['article_id']][0];self.assertIn(n['raw'],n['quote']);self.assertEqual(r['text'][n['start']:n['end']],n['raw'])

    def test_semantic_similarity_without_event_overlap_does_not_group(self):
        rows=[record('a','ЦБ снизил ключевую ставку'),record('b','Компания открыла новый завод')]
        vec=np.ones(384)/np.sqrt(384)
        self.assertEqual(len(group(rows,{r['article_id']:vec for r in rows})[0]),2)
        self.assertEqual(quantities('Выручка 1 200,5 млн рублей, рост 12,5%')[0]['value'],'1200.5')

    def test_similarity_chain_does_not_merge_unrelated_anchors(self):
        import math
        rows=[record(a,'Банк меняет ключевую ставку') for a in ('a','b','c')]
        vectors={aid:np.asarray([math.cos(angle),math.sin(angle)]) for aid,angle in [('a',0),('b',.24),('c',.48)]}
        groups,members,_=group(rows,vectors)
        self.assertEqual(len(groups),2)
        self.assertEqual(members['a']['story_id'],members['b']['story_id'])
        self.assertNotEqual(members['a']['story_id'],members['c']['story_id'])
