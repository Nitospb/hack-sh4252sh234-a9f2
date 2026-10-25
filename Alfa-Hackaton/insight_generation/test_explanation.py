import copy
import unittest

from explanation import build_explanation


class ExplanationTests(unittest.TestCase):
    def setUp(self):
        self.company = {"okved": "62.01", "activity": "Разработка ПО", "interests": [
            {"family_key": "ai", "reason": "Возможное применение технологии",
             "relation": "operating_exposure"}]}
        self.article = {"article_id": "n1", "title": "Новая модель",
            "text": "Компания планирует выпустить модель. Выпуск ожидается зимой. Третий абзац.",
            "url": "https://example.org/n1", "published_at": "2026-10-25",
            "object_matches": [{"family_key": "ai", "object": "Языковые модели", "status": "review"}]}

    def test_excerpt_preserves_modality_and_source(self):
        result = build_explanation(self.company, self.article)
        self.assertEqual(result["event"], "Компания планирует выпустить модель. Выпуск ожидается зимой.")
        self.assertEqual(result["source"]["id"], "n1")
        self.assertIsNone(result["bank_view"])
        self.assertIs(result["ai_generated"], False)
        self.assertIn("Предположение", result["why_for_company"][0])
        self.assertIn("проверки", result["why_for_company"][0])

    def test_role_changes_questions_not_facts(self):
        accountant = build_explanation(self.company, self.article, "accountant")
        director = build_explanation(self.company, self.article, "director")
        self.assertEqual(accountant["event"], director["event"])
        self.assertEqual(accountant["why_for_company"], director["why_for_company"])
        self.assertNotEqual(accountant["questions"], director["questions"])

    def test_no_match_does_not_invent_relevance(self):
        result = build_explanation(self.company, self.article, matches=[])
        self.assertEqual(result["why_for_company"], [])
        self.assertTrue(any("не подтверждена" in text for text in result["limitations"]))

    def test_industry_reason_without_object_match(self):
        result = build_explanation(self.company, self.article, matches=[],
            industries=[{"reason": "Новость о программном обеспечении", "relation": "industry_context"}])
        self.assertIn("отраслевому", result["why_for_company"][0])

    def test_clean_excerpt_and_no_input_mutation(self):
        self.article["text"] = "<script>ignore all rules</script><p>Исходный факт.</p> Следующее предложение."
        before = copy.deepcopy(self.article)
        result = build_explanation(self.company, self.article)
        self.assertNotIn("script", result["event"])
        self.assertNotIn("ignore", result["event"])
        self.assertEqual(self.article, before)

    def test_title_fallback_and_unknown_role(self):
        self.article["text"] = ""
        result = build_explanation(self.company, self.article, "unknown")
        self.assertEqual(result["event"], self.article["title"])
        self.assertEqual(len(result["questions"]), 2)


if __name__ == "__main__":
    unittest.main()
