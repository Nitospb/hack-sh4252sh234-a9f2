import unittest
from map_okved_to_topics import expand_mapping, topic_matches


def sample(object_name='Пшеница', signal='Рост цен', tid='bt_test', sector='industry_01'):
    return dict(topic_id=tid,object=object_name,signal=signal,name=object_name+': '+signal,
                sector_id=sector,sector_name='Растениеводство',object_keywords=[object_name],signal_keywords=[signal])


class OkvedMappingTests(unittest.TestCase):
    def record(self, **changes):
        mapping=dict(sector_id='industry_01',objects=['Пшеница'],relation='activity_scope_candidate',reason='Входит в область зерновых.',signal_names=[])
        mapping.update(changes)
        return dict(okved='01.11',mappings=[mapping])

    def test_selects_only_chosen_objects_from_original_ids(self):
        topics=[sample(),sample(signal='Снижение цен',tid='bt_down'),sample('Рис',tid='bt_rice')]
        out=expand_mapping(self.record(),{'industry_01':topics})
        self.assertEqual(out[0]['topic_ids'],['bt_test','bt_down'])
        self.assertEqual(out[0]['relation'],'activity_scope_candidate')

    def test_can_limit_signals(self):
        out=expand_mapping(self.record(signal_names=['Рост цен']),{'industry_01':[sample(),sample(signal='Снижение цен',tid='bt_down')]})
        self.assertEqual(out[0]['topic_ids'],['bt_test'])

    def test_rejects_invented_object_and_signal(self):
        with self.assertRaises(AssertionError):
            expand_mapping(self.record(objects=['Несуществующий объект']),{'industry_01':[sample()]})
        with self.assertRaises(AssertionError):
            expand_mapping(self.record(signal_names=['Несуществующий сигнал']),{'industry_01':[sample()]})

    def test_rejects_missing_reason_and_duplicate_binding(self):
        with self.assertRaises(AssertionError):expand_mapping(self.record(reason=''),{'industry_01':[sample()]})
        r=self.record();r['mappings']*=2
        with self.assertRaises(AssertionError):expand_mapping(r,{'industry_01':[sample()]})

    def test_ai_alias_is_not_substring_of_company(self):
        self.assertFalse(topic_matches(sample(object_name='Компания'),'ИИ'))
        self.assertTrue(topic_matches(sample(object_name='Языковая модель',sector='crosscut_28'),'ИИ'))
        self.assertTrue(topic_matches(sample(object_name='Языковая модель',sector='crosscut_28'),'AI'))

    def test_whole_phrase_boundaries(self):
        self.assertFalse(topic_matches(sample(object_name='Газовая станция'),'газ'))
        self.assertFalse(topic_matches(sample(),' '))
        self.assertTrue(topic_matches(sample(),'пшеница'))


if __name__=='__main__':unittest.main()
