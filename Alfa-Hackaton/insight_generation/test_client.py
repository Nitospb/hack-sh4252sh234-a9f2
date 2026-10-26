"""Offline gateway contract tests; no real credentials, network or spending."""
import copy
import io
import json
import os
import unittest
from unittest.mock import patch

from client import generate, validate_result


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.payload = {"as_of": "2026-10-25", "company_facts": [
            {"id": "f1", "field": "credit", "value": True, "evidence_level": "confirmed"}],
            "news": {"id": "n1", "title": "Test", "text": "Test",
                     "published_at": "2026-10-25", "url": ""}, "bank_passages": []}
        self.result = {"status": "ready", "title": "Test", "event": {
            "text": "Test", "source_ids": ["n1"]}, "why_for_company": [{
                "text": "Проверить условия кредита", "company_fact_ids": ["f1"],
                "source_ids": ["n1"], "conditional": True}], "bank_view": None,
            "ai_application": [], "risks": [], "opportunities": [], "actions": [],
            "missing_context": [], "limitations": []}

    def call(self, content, finish="stop"):
        def transport(request, timeout):
            self.assertEqual(json.loads(request.data)["model"], "z-ai/glm-5.3-flash")
            return io.StringIO(json.dumps({"choices": [{"finish_reason": finish,
                "message": {"content": content}}], "usage": {"total_tokens": 1}}))
        with patch.dict(os.environ, {"ALFA_API_KEY": "test-only",
                                     "ALFA_MODEL": "z-ai/glm-5.3-flash",
                                     "ALFA_BASE_URL": "https://changellenge.up.railway.app/v1"}):
            return generate(self.payload, transport=transport)

    def test_json_and_fenced_json(self):
        for content in (json.dumps(self.result), "```json\n" + json.dumps(self.result) + "\n```"):
            self.assertEqual(self.call(content)["insight"], self.result)

    def test_truncated_answer_is_rejected(self):
        with self.assertRaises(ValueError):
            self.call(json.dumps(self.result), finish="length")

    def test_unknown_company_fact_is_rejected(self):
        result = copy.deepcopy(self.result)
        result["why_for_company"][0]["company_fact_ids"] = ["missing"]
        with self.assertRaises(ValueError):
            validate_result(result, self.payload)

    def test_news_cannot_be_bank_opinion_source(self):
        result = copy.deepcopy(self.result)
        result["bank_view"] = {"label": "Позиция Альфа-Банка по событию",
            "relation": "direct", "summary": "Test", "source_ids": ["n1"],
            "applicability": "Test", "limitations": ""}
        with self.assertRaises(ValueError):
            validate_result(result, self.payload)

    def test_candidate_only_cannot_be_ready(self):
        self.payload["company_facts"][0]["evidence_level"] = "candidate"
        with self.assertRaisesRegex(ValueError, "needs_context"):
            validate_result(self.result, self.payload)
        self.result["status"] = "needs_context"
        self.result["missing_context"] = ["Подтвердите наличие кредита"]
        self.assertEqual(validate_result(self.result, self.payload)["status"], "needs_context")

    def test_candidate_claim_must_remain_conditional(self):
        self.payload["company_facts"][0]["evidence_level"] = "candidate"
        self.result["status"] = "needs_context"
        self.result["missing_context"] = ["Подтвердите кредит"]
        self.result["why_for_company"][0]["conditional"] = False
        with self.assertRaisesRegex(ValueError, "условным"):
            validate_result(self.result, self.payload)

    def test_as_of_date_includes_day_but_rejects_future(self):
        self.payload["news"]["published_at"] = "2026-10-25T18:00:00Z"
        validate_result(self.result, self.payload)
        self.payload["news"]["published_at"] = "2026-10-26T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "после"):
            validate_result(self.result, self.payload)

    def test_bank_source_date_and_analogy_limits_are_required(self):
        self.payload["bank_passages"] = [{"id": "b1", "published_at": "2026-09-11"}]
        self.result["bank_view"] = {
            "label": "Позиция Альфа-Банка по схожей ситуации", "relation": "analogous",
            "summary": "Историческая оценка", "source_ids": ["b1"],
            "applicability": "Сходный механизм", "limitations": "Другой период"}
        validate_result(self.result, self.payload)
        for date in (None, "2026-10-26"):
            self.payload["bank_passages"][0]["published_at"] = date
            with self.assertRaises(ValueError):
                validate_result(self.result, self.payload)
        self.payload["bank_passages"][0]["published_at"] = "2026-09-11"
        self.result["bank_view"]["limitations"] = ""
        with self.assertRaisesRegex(ValueError, "ограничения"):
            validate_result(self.result, self.payload)

    def test_related_source_ids_are_allowed_only_with_current_date(self):
        self.payload['related_news']=[{'id':'r1','published_at':'2026-10-24'}]
        self.result['actions']=[{'text':'Проверить срок','company_fact_ids':['f1'],'source_ids':['r1'],'conditional':True}]
        validate_result(self.result,self.payload)
        self.payload['related_news'][0]['published_at']='2026-10-26'
        with self.assertRaises(ValueError):validate_result(self.result,self.payload)


    def test_supported_assessment_can_be_ready_without_a_separate_why_block(self):
        self.result['ai_application']=self.result['why_for_company']
        self.result['why_for_company']=[]
        validate_result(self.result,self.payload)
        self.payload['company_facts'][0]['evidence_level']='candidate'
        with self.assertRaises(ValueError):validate_result(self.result,self.payload)

if __name__ == "__main__":
    unittest.main()
