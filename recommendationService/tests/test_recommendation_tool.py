"""
Integration tests for the personalized recommendations tool.
"""
import unittest
import uuid

from app.agent.tools.recommendation_tool import MAX_LIMIT, build_recommendation_tool
from tests.live_db import USER_WITH_HISTORY, requires_db


class TestRecommendationToolSchema(unittest.TestCase):
    def test_llm_cannot_choose_the_user(self):
        self.assertNotIn("user_id", build_recommendation_tool(USER_WITH_HISTORY).args)


@requires_db
class TestRecommendationTool(unittest.TestCase):
    def test_user_without_history_gets_fallback_message(self):
        result = build_recommendation_tool(str(uuid.uuid4())).invoke({})
        self.assertIn("search_pois_tool", result["mensaje"])

    def test_user_with_history_gets_recommendations_with_department(self):
        result = build_recommendation_tool(USER_WITH_HISTORY).invoke({"limit": 3})
        recs = result["recomendaciones"]
        self.assertEqual(len(recs), 3)
        for rec in recs:
            self.assertTrue(rec["departamento"])
            self.assertTrue(rec["motivo"])

    def test_limit_above_max_is_clamped(self):
        result = build_recommendation_tool(USER_WITH_HISTORY).invoke({"limit": 100})
        self.assertLessEqual(len(result["recomendaciones"]), MAX_LIMIT)


if __name__ == "__main__":
    unittest.main()
