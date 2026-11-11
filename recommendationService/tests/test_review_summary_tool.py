"""
Integration tests for the POI reviews tool.
"""
import unittest

from app.agent.tools.review_summary_tool import get_poi_reviews_summary_tool as tool
from tests.live_db import requires_db


@requires_db
class TestReviewTool(unittest.TestCase):
    def test_exact_name_wins_over_more_reviewed_partial_matches(self):
        # "Lago del Parque General San Martín y El Rosedal" also matches and has 620 reviews.
        result = tool.invoke({"poi": "Parque General San Martín"})
        self.assertEqual(result["poi_nombre"], "Parque General San Martín")

    def test_uuid_finds_the_same_poi_as_its_name(self):
        by_name = tool.invoke({"poi": "Café Ando"})
        by_id = tool.invoke({"poi": by_name["poi_id"]})
        self.assertEqual(by_id["poi_nombre"], "Café Ando")

    def test_returns_latest_five_reviews_and_poi_rating(self):
        result = tool.invoke({"poi": "Café Ando"})
        self.assertEqual(len(result["opiniones_recientes"]), 5)
        self.assertEqual(result["cantidad_reviews"], 10)
        self.assertIn("puntuacion_promedio", result)

    def test_rejected_poi_is_not_found(self):
        self.assertIn("error", tool.invoke({"poi": "Mirador del Valle Malargüe"}))

    def test_unknown_text_returns_message(self):
        self.assertIn("error", tool.invoke({"poi": "abc-no-existe"}))


if __name__ == "__main__":
    unittest.main()
