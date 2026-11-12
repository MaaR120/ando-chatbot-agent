"""
Tests for the POI search tool: keyword filter (unit) and search (integration).
"""
import unittest

from app.agent.tools.poi_search_tool import MAX_LIMIT, keyword_filter, search_pois_tool
from tests.live_db import requires_db


class TestKeywordFilter(unittest.TestCase):
    def test_one_condition_per_word(self):
        sql, params = keyword_filter("vino  malbec")
        self.assertEqual(sql.count(" AND "), 2)
        self.assertEqual(params, {"q0": "%vino%", "q1": "%malbec%"})

    def test_like_wildcards_are_escaped(self):
        _, params = keyword_filter("50%_off")
        self.assertEqual(params["q0"], "%50\\%\\_off%")


@requires_db
class TestPoiSearchTool(unittest.TestCase):
    def search(self, **kwargs):
        return search_pois_tool.invoke(kwargs)

    def test_words_match_separately(self):
        names = [r["nombre"] for r in self.search(query="parque rosedal")]
        self.assertIn("Lago del Parque General San Martín y El Rosedal", names)

    def test_percent_sign_is_literal(self):
        self.assertEqual(self.search(query="%"), [])

    def test_rejected_poi_is_not_returned(self):
        names = [r["nombre"] for r in self.search(query="Mirador del Valle Malargüe")]
        self.assertNotIn("Mirador del Valle Malargüe", names)

    def test_real_category_name_returns_results(self):
        results = self.search(category="Bodega")
        self.assertTrue(results)
        for r in results:
            self.assertIn("Bodega", r["categorias"])

    def test_limit_above_max_is_clamped(self):
        self.assertEqual(len(self.search(limit=100)), MAX_LIMIT)


if __name__ == "__main__":
    unittest.main()
