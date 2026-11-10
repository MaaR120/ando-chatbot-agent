"""
Unit and integration tests for Collaborative Recommendation Engine & Endpoints (US-MRIA-09).
"""
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import get_db
from app.services.collaborative_engine import CollaborativeEngine


class TestCollaborativeEngine(unittest.TestCase):
    def setUp(self):
        self.engine = CollaborativeEngine(min_global_ratings=3)
        self.approved_pois = {
            "poi-bodega-1": {
                "id": "poi-bodega-1",
                "nombre": "Bodega Catena",
                "precio_min": 10000,
                "precio_max": 25000,
                "categorias": ["Enoturismo", "Bodegas"],
            },
            "poi-bodega-2": {
                "id": "poi-bodega-2",
                "nombre": "Bodega Norton",
                "precio_min": 8000,
                "precio_max": 20000,
                "categorias": ["Enoturismo"],
            },
            "poi-montana-1": {
                "id": "poi-montana-1",
                "nombre": "Cerro Aconcagua Base",
                "precio_min": 5000,
                "precio_max": 12000,
                "categorias": ["Aventura", "Montaña"],
            },
            "poi-ciudad-1": {
                "id": "poi-ciudad-1",
                "nombre": "Parque San Martín",
                "precio_min": 0,
                "precio_max": 0,
                "categorias": ["Parques", "Paseos"],
            },
        }
        self.categories = ["cat-vino", "cat-aventura", "cat-parque"]

    def test_cold_start_insufficient_global_ratings(self):
        """Si no hay suficientes valoraciones a nivel global (< min_global_ratings), devuelve has_sufficient_data: False."""
        res = self.engine.calculate_collaborative_recommendations(
            target_user_id="user-1",
            all_user_ids=["user-1", "user-2"],
            all_category_ids=self.categories,
            approved_pois=self.approved_pois,
            user_preferences={"user-1": {"cat-vino"}},
            user_ratings={("user-2", "poi-bodega-1"): 5.0},  # Solo 1 rating
            user_favorites={},
            user_visited_pois={},
        )
        self.assertFalse(res.has_sufficient_data)
        self.assertEqual(res.total, 0)
        self.assertTrue(res.metadata.used_fallback)

    def test_cold_start_target_user_no_history_or_preferences(self):
        """Si el usuario actual no tiene ni preferencias ni interacciones, se sugiere fallback."""
        res = self.engine.calculate_collaborative_recommendations(
            target_user_id="user-empty",
            all_user_ids=["user-empty", "user-2", "user-3"],
            all_category_ids=self.categories,
            approved_pois=self.approved_pois,
            user_preferences={"user-2": {"cat-vino"}, "user-3": {"cat-vino"}},
            user_ratings={
                ("user-2", "poi-bodega-1"): 5.0,
                ("user-2", "poi-bodega-2"): 5.0,
                ("user-3", "poi-bodega-1"): 4.0,
                ("user-3", "poi-bodega-2"): 5.0,
            },
            user_favorites={},
            user_visited_pois={},
        )
        self.assertFalse(res.has_sufficient_data)
        self.assertEqual(res.total, 0)
        self.assertEqual(res.metadata.fallback_strategy, "preferences")

    def test_similar_users_recommendation_and_visited_exclusion(self):
        """
        User-1 le gusta el vino (visitó poi-bodega-1).
        User-2 le gusta el vino (visitó poi-bodega-1 y poi-bodega-2).
        User-3 le gusta la montaña (visitó poi-montana-1).
        User-1 debería recibir recomendado poi-bodega-2 por similitud con User-2, y NO poi-bodega-1 (ya visitado).
        """
        user_ratings = {
            ("user-1", "poi-bodega-1"): 5.0,
            ("user-2", "poi-bodega-1"): 5.0,
            ("user-2", "poi-bodega-2"): 5.0,
            ("user-3", "poi-montana-1"): 5.0,
        }
        user_prefs = {
            "user-1": {"cat-vino"},
            "user-2": {"cat-vino"},
            "user-3": {"cat-aventura"},
        }
        user_visited = {
            "user-1": {"poi-bodega-1"},
            "user-2": {"poi-bodega-1", "poi-bodega-2"},
            "user-3": {"poi-montana-1"},
        }

        res = self.engine.calculate_collaborative_recommendations(
            target_user_id="user-1",
            all_user_ids=["user-1", "user-2", "user-3"],
            all_category_ids=self.categories,
            approved_pois=self.approved_pois,
            user_preferences=user_prefs,
            user_ratings=user_ratings,
            user_favorites={},
            user_visited_pois=user_visited,
            include_visited=False,
        )

        self.assertTrue(res.has_sufficient_data)
        self.assertGreaterEqual(res.total, 1)
        # La primera recomendación debe ser poi-bodega-2
        rec_ids = [r.poi_id for r in res.recommendations]
        self.assertIn("poi-bodega-2", rec_ids)
        self.assertNotIn("poi-bodega-1", rec_ids)  # Excluido por ya visitado

        top_rec = res.recommendations[0]
        self.assertEqual(top_rec.poi_id, "poi-bodega-2")
        self.assertGreater(top_rec.score, 0.0)
        self.assertIn("gustos", top_rec.reason)
        self.assertIsNotNone(top_rec.subscores.neighbor_similarity_avg)


class TestCollaborativeRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_collaborative_config_endpoint(self):
        """Verifica que el endpoint de configuración retorne los hiperparámetros."""
        response = self.client.get("/recommendations/collaborative/config")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("min_global_ratings", data)
        self.assertIn("default_k_neighbors", data)

    @patch("app.services.collaborative_service.CollaborativeRecommendationService.get_collaborative_recommendations")
    def test_collaborative_recommendations_endpoint(self, mock_get_rec):
        """Verifica la respuesta del endpoint POST /recommendations/collaborative."""
        mock_get_rec.return_value = {
            "user_id": "usr-123",
            "has_sufficient_data": True,
            "total": 1,
            "metadata": {
                "has_sufficient_data": True,
                "total_users_analyzed": 10,
                "neighbors_found_count": 3,
                "global_ratings_count": 25,
                "used_fallback": False,
                "fallback_strategy": None,
            },
            "recommendations": [
                {
                    "poi_id": "poi-999",
                    "nombre": "Bodega Experimental",
                    "score": 0.88,
                    "reason": "Recomendado por similitud con otros turistas.",
                    "subscores": {
                        "neighbor_similarity_avg": 0.90,
                        "interaction_strength": 0.85,
                        "final_score": 0.88,
                    },
                    "ya_visitado": False,
                    "categorias": ["Enoturismo"],
                    "precio_min": 1000,
                    "precio_max": 3000,
                    "similar_users_count": 2,
                }
            ],
        }

        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            response = self.client.post(
                "/recommendations/collaborative",
                json={"user_id": "usr-123", "limit": 5, "k_neighbors": 10},
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["has_sufficient_data"])
            self.assertEqual(data["total"], 1)
            self.assertEqual(data["recommendations"][0]["poi_id"], "poi-999")
        finally:
            app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
