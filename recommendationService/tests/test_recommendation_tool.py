"""
Integration tests for get_personalized_recommendations_tool against the local database (init.sql seed).
"""
import unittest
import uuid

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.agent.tools.recommendation_tool import MAX_LIMIT, get_personalized_recommendations_tool as tool
from app.core.database import get_engine

USER_WITH_HISTORY = "8addc001-3489-4811-b84f-4c7be7bfce02"


def database_available() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


@unittest.skipUnless(database_available(), "requires the ando-agent-db Postgres container")
class TestRecommendationTool(unittest.TestCase):
    def test_user_without_history_gets_fallback_message(self):
        result = tool.invoke({"user_id": str(uuid.uuid4())})
        self.assertIn("search_pois_tool", result["mensaje"])

    def test_user_with_history_gets_recommendations_with_department(self):
        result = tool.invoke({"user_id": USER_WITH_HISTORY, "limit": 3})
        recs = result["recomendaciones"]
        self.assertEqual(len(recs), 3)
        for rec in recs:
            self.assertTrue(rec["departamento"])
            self.assertTrue(rec["motivo"])

    def test_limit_above_max_is_clamped(self):
        result = tool.invoke({"user_id": USER_WITH_HISTORY, "limit": 100})
        self.assertLessEqual(len(result["recomendaciones"]), MAX_LIMIT)


if __name__ == "__main__":
    unittest.main()
