"""
Tests for the route optimization tool: input validation (unit) and optimization (integration).
"""
import unittest

from app.agent.tools.poi_search_tool import search_pois_tool
from app.agent.tools.route_optimization_tool import MAX_POIS, optimize_route_tool
from tests.live_db import requires_db


class TestRouteToolValidation(unittest.TestCase):
    def run_tool(self, **kwargs):
        return optimize_route_tool.invoke(kwargs)

    def test_needs_at_least_two_pois(self):
        self.assertIn("error", self.run_tool(poi_ids=["a"]))

    def test_rejects_too_many_pois(self):
        ids = [f"00000000-0000-0000-0000-{i:012d}" for i in range(MAX_POIS + 1)]
        self.assertIn("error", self.run_tool(poi_ids=ids))

    def test_rejects_non_uuid(self):
        self.assertIn("error", self.run_tool(poi_ids=["x", "y"]))

    def test_rejects_unknown_travel_mode(self):
        ids = ["00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"]
        self.assertIn("error", self.run_tool(poi_ids=ids, modo_viaje="teletransporte"))


@requires_db
class TestRouteToolIntegration(unittest.TestCase):
    def test_orders_real_pois(self):
        ids = [p["id"] for p in search_pois_tool.invoke({"department": "Maipú", "limit": 3})]
        result = optimize_route_tool.invoke({"poi_ids": ids})
        self.assertNotIn("error", result)
        self.assertEqual({s["id"] for s in result["paradas"]}, set(ids))
        self.assertEqual([s["orden"] for s in result["paradas"]], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
