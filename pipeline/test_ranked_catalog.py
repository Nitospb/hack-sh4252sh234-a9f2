import unittest
from ranked_catalog import article_quality, thematic_candidate, OPERATING_NAMES

class RankingEnrichmentTests(unittest.TestCase):
    def test_business_headline_with_substantive_lead(self):
        score, general, roles, reason = article_quality('Налоговая реформа для бизнеса: что изменится для компаний','Компании будут платить НДС. Налог на прибыль изменится для бизнеса.')
        self.assertGreaterEqual(score,.5);self.assertTrue(general);self.assertIn('accountant',roles)
    def test_incident_not_general_business(self):
        for title in ['В ДТП погиб директор компании','Банк открыл офис после пожара','Футбольный клуб получил прибыль','Новый маникюр для бизнес-леди','Гороскоп для предпринимателей','Поухаживайте за клубникой и соберите урожай','Как студенту использовать ИИ, чтобы не вылететь из вуза','Сухогрузы: Украина теряет тыловую логистику']:
            self.assertEqual(article_quality(title,'Компания банк бизнес инвестиции')[0],0.)
    def test_only_body_mention_not_business(self):
        self.assertFalse(article_quality('В городе открылся памятник','Банк поддержал мероприятие, компания инвестировала средства')[1])
    def test_role_is_content_category(self):
        self.assertIn('it',article_quality('Нейросети помогают бизнесу','Компании внедряют технологии и цифровизацию')[2])
    def test_russia_suffix_does_not_mean_ai(self):
        self.assertNotIn('it',article_quality('Банк России изменил ключевую ставку','В России компании получают кредиты и платят налоги')[2])
    def test_retrieval_is_not_acceptance(self):
        self.assertTrue(thematic_candidate({'embedding_cosine':.82,'reranker_logit':-2.9},.7))
        self.assertFalse(thematic_candidate({'embedding_cosine':.82,'reranker_logit':-2.9},.2))
        self.assertFalse(thematic_candidate({'embedding_cosine':.9,'reranker_logit':-7},.7))
    def test_operating_topics_varied(self):
        self.assertEqual(len(OPERATING_NAMES),len(set(OPERATING_NAMES)))
        self.assertGreaterEqual(len(OPERATING_NAMES),20)

if __name__=='__main__':unittest.main()
