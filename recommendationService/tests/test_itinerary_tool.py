"""
Integration tests for the user itinerary tool.
"""
import unittest
import uuid

from app.agent.tools.itinerary_tool import build_itinerary_tool
from tests.live_db import ITINERARY_OF_USER, USER_WITH_HISTORY, requires_db


class TestItineraryToolSchema(unittest.TestCase):
    def test_llm_cannot_choose_the_user(self):
        self.assertNotIn("user_id", build_itinerary_tool(USER_WITH_HISTORY).args)


@requires_db
class TestItineraryTool(unittest.TestCase):
    def test_lists_at_most_five_itineraries_of_the_user(self):
        result = build_itinerary_tool(USER_WITH_HISTORY).invoke({})
        self.assertTrue(0 < len(result["itinerarios"]) <= 5)

    def test_owner_sees_itinerary_detail_with_stops(self):
        result = build_itinerary_tool(USER_WITH_HISTORY).invoke({"itinerary_id": ITINERARY_OF_USER})
        self.assertEqual(result["itinerario"]["nombre"], "Fin de semana en Mendoza")
        self.assertEqual(result["paradas"][0]["poi_nombre"], "Parque General San Martín")

    def test_other_user_cannot_see_the_itinerary(self):
        result = build_itinerary_tool(str(uuid.uuid4())).invoke({"itinerary_id": ITINERARY_OF_USER})
        self.assertNotIn("itinerario", result)

    def test_invalid_itinerary_id_returns_message(self):
        result = build_itinerary_tool(USER_WITH_HISTORY).invoke({"itinerary_id": "abc"})
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
