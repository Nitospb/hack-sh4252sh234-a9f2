import unittest
from taxonomy import Matcher


def topic():
    return dict(topic_id='test', name='Природный газ: рост цен', sector_id='gas',
                sector_name='Газ', object_keywords=['газ'], signal_keywords=['рост цен'],
                okved_prefixes=['06.2'], company_conditions=['FTS_FLAG'])


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.matcher = Matcher([topic()])

    def test_requires_object_and_signal_in_local_context(self):
        self.assertFalse(self.matcher.classify({'text': 'Рост цен на газ'})['abstained'])
        self.assertTrue(self.matcher.classify({'text': 'Добыча газа'})['abstained'])
        self.assertTrue(self.matcher.classify({'text': 'Газ ' + 'далеко ' * 100 + 'рост цен'})['abstained'])

    def test_no_substring_false_positive(self):
        self.assertTrue(self.matcher.classify({'text': 'Магазин сообщил про рост цен'})['abstained'])

    def test_okved_hierarchy_and_unknown(self):
        self.assertFalse(self.matcher.profile({'MAINOKVED_CODE': '06.20.1'})['abstained'])
        self.assertTrue(self.matcher.profile({'MAINOKVED_CODE': '06.30'})['abstained'])
        self.assertTrue(self.matcher.profile({})['abstained'])

    def test_flag_is_evidence_and_zero_is_not(self):
        self.assertFalse(self.matcher.profile({'FTS_FLAG': '1.0'})['abstained'])
        self.assertTrue(self.matcher.profile({'FTS_FLAG': '0.0'})['abstained'])


if __name__ == '__main__':
    unittest.main()
