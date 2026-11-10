"""
Integration tests for FastAPI recommendation routes (US-MRIA-04).
"""
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import get_db


class TestRecommendationRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_check(self):
        """Verifica el endpoint de healthcheck."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")

    def test_weights_config_endpoint(self):
        """Verifica el endpoint de consulta de configuración."""
        response = self.client.get("/recommendations/history/config")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("history_weights", data)
        self.assertIn("positive_rating", data["history_weights"])

    @patch("app.services.history_recommendation_service.HistoryRecommendationService.get_history_recommendations")
    def test_history_recommendation_endpoint_insufficient_history(self, mock_get_rec):
        """Verifica que un usuario sin historial suficiente retorne has_sufficient_history: False y total: 0 sin error."""
        mock_get_rec.return_value = {
            "user_id": "usr-cold-start",
            "has_sufficient_history": False,
            "total": 0,
            "metadata": {
                "has_sufficient_history": False,
                "finished_itineraries_count": 0,
                "total_ratings_count": 0,
                "positive_ratings_count": 0,
                "favorites_count": 0,
                "visited_pois_count": 0,
                "used_fallback": True,
                "fallback_strategy": "preferences",
            },
            "recommendations": [],
        }

        # Override get_db dependency
        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            response = self.client.post(
                "/recommendations/history",
                json={"user_id": "usr-cold-start", "limit": 10},
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertFalse(data["has_sufficient_history"])
            self.assertEqual(data["total"], 0)
            self.assertTrue(data["metadata"]["used_fallback"])
            self.assertEqual(data["metadata"]["fallback_strategy"], "preferences")
        finally:
            app.dependency_overrides.pop(get_db, None)

    @patch("app.services.history_recommendation_service.HistoryRecommendationService.get_history_recommendations")
    def test_history_recommendation_endpoint_success(self, mock_get_rec):
        """Verifica que un usuario con historial suficiente retorne las recomendaciones estructuradas."""
        mock_get_rec.return_value = {
            "user_id": "usr-with-history",
            "has_sufficient_history": True,
            "total": 1,
            "metadata": {
                "has_sufficient_history": True,
                "finished_itineraries_count": 2,
                "total_ratings_count": 6,
                "positive_ratings_count": 4,
                "favorites_count": 1,
                "visited_pois_count": 3,
                "used_fallback": False,
                "fallback_strategy": None,
            },
            "recommendations": [
                {
                    "poi_id": "poi-rec-1",
                    "nombre": "Bodega Catena Zapata",
                    "score": 0.88,
                    "reason": "Basado en tus valoraciones de 4★ y 5★ de Bodegas y visitas frecuentes.",
                    "ya_visitado": False,
                    "categorias": ["Bodegas", "Enoturismo"],
                    "precio_min": 15000,
                    "precio_max": 25000,
                    "subscores": {
                        "positive_rating_score": 0.9,
                        "category_frequency_score": 1.0,
                        "favorite_affinity_score": 0.5,
                        "recency_score": 0.95,
                        "price_compatibility_score": 1.0,
                        "final_score": 0.88,
                        "active_weights": {
                            "positive_rating": 0.3,
                            "category_frequency": 0.25,
                            "favorite_affinity": 0.2,
                            "recency": 0.15,
                            "price_compatibility": 0.1,
                        },
                    },
                }
            ],
        }

        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            response = self.client.post(
                "/recommendations/history",
                json={"user_id": "usr-with-history", "limit": 5, "include_visited": False},
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["has_sufficient_history"])
            self.assertEqual(data["total"], 1)
            self.assertEqual(data["recommendations"][0]["nombre"], "Bodega Catena Zapata")
            self.assertAlmostEqual(data["recommendations"][0]["score"], 0.88)
        finally:
            app.dependency_overrides.pop(get_db, None)


if __name__ == "__main__":
    unittest.main()
