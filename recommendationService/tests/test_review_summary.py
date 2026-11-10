"""
Unit and Integration Tests for AI Review Summary Service (US-RYV-06).
"""
import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.reviews_summary import (
    ReviewSummaryRequest,
    ReviewItemPayload,
)
from app.services.review_summary_service import ReviewSummaryService


class TestReviewSummary(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_review_summary_endpoint_success(self):
        payload = {
            "poi_id": "550e8400-e29b-41d4-a716-446655440001",
            "poi_nombre": "Bodega Catena Zapata",
            "categorias": ["Bodegas y Viñedos", "Gastronomía"],
            "reviews": [
                {
                    "id": "rev-1",
                    "comentario": "Excelente atención y hermosa vista a los viñedos.",
                    "puntuacion": 5.0,
                },
                {
                    "id": "rev-2",
                    "comentario": "Los vinos son excelentes, aunque hay cierta demora en la atención sin reserva.",
                    "puntuacion": 4.0,
                },
                {
                    "id": "rev-3",
                    "comentario": "Gran experiencia y degustación de primer nivel.",
                    "puntuacion": 5.0,
                },
                {
                    "id": "rev-4",
                    "comentario": "Muy lindo lugar, precios algo elevados pero vale la pena.",
                    "puntuacion": 4.5,
                },
                {
                    "id": "rev-5",
                    "comentario": "Todo impecable, el paisaje de la cordillera es inigualable.",
                    "puntuacion": 5.0,
                },
            ],
        }

        response = self.client.post("/reviews/summary", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["poi_id"], "550e8400-e29b-41d4-a716-446655440001")
        self.assertTrue(len(data["resumen"]) > 10)
        self.assertTrue(len(data["puntos_positivos"]) >= 1)
        self.assertEqual(data["total_resenas"], 5)
        self.assertEqual(data["puntuacion_promedio"], 4.7)

    def test_review_summary_service_deterministic_fallback(self):
        service = ReviewSummaryService(gemini_api_key="", openai_api_key="", groq_api_key="")
        request = ReviewSummaryRequest(
            poi_id="poi-123",
            poi_nombre="Restaurante Cordillera",
            categorias=["Gastronomía"],
            reviews=[
                ReviewItemPayload(id="1", comentario="Muy rica comida y excelente atención del mozo", puntuacion=5.0),
                ReviewItemPayload(id="2", comentario="Demora un poco en traer los platos pero todo delicioso", puntuacion=4.0),
                ReviewItemPayload(id="3", comentario="Hermosa vista y platos abundantes", puntuacion=5.0),
                ReviewItemPayload(id="4", comentario="Precios algo elevados pero muy buena calidad", puntuacion=4.0),
                ReviewItemPayload(id="5", comentario="Excelente experiencia gastronómica", puntuacion=5.0),
            ],
        )

        res = service.generate_summary(request)
        self.assertEqual(res.poi_id, "poi-123")
        self.assertIn("Restaurante Cordillera", res.resumen)
        self.assertEqual(res.total_resenas, 5)
        self.assertEqual(res.puntuacion_promedio, 4.6)
        self.assertTrue(len(res.puntos_positivos) >= 1)
        self.assertTrue(len(res.puntos_negativos) >= 1)

    def test_review_summary_endpoint_empty_reviews(self):
        payload = {
            "poi_id": "poi-empty",
            "poi_nombre": "Lugar Sin Reseñas",
            "categorias": [],
            "reviews": [],
        }
        # Validates min_length=1 in schema
        response = self.client.post("/reviews/summary", json=payload)
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
