"""
Unit and integration tests for AI Content Moderation Engine & Endpoints (US-MRIA-10).
"""
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.content_moderation import ModerationRequest
from app.services.content_moderator import ContentModeratorService


class TestContentModeratorService(unittest.TestCase):
    def setUp(self):
        # Usar motor heurístico para pruebas determinísticas y offline
        self.service = ContentModeratorService(gemini_api_key="", openai_api_key="")

    def test_clean_review_requires_no_revision(self):
        """Una reseña normal o crítica legítima no debe requerir revisión."""
        req = ModerationRequest(
            text="Excelente degustación y recorrido por los viñedos. La comida estuvo un poco demorada pero muy rica.",
            entity_type="review",
        )
        res = self.service.analyze_content(req)
        self.assertFalse(res.requiere_revision)
        self.assertIsNone(res.categoria)
        self.assertIsNone(res.motivo)

    def test_commercial_spam_with_phone_detected(self):
        """Detecta publicidad no autorizada o contacto comercial encubierto."""
        req = ModerationRequest(
            text="No contraten los tours de la app, escríbanme al WhatsApp +54 9 261 555-1234 que les hago el tour privado.",
            entity_type="review",
        )
        res = self.service.analyze_content(req)
        self.assertTrue(res.requiere_revision)
        self.assertEqual(res.categoria, "SPAM_COMERCIAL")
        self.assertIn("contacto comercial", res.motivo)
        self.assertGreaterEqual(res.nivel_confianza, 0.70)

    def test_external_url_spam_detected(self):
        """Detecta enlaces externos promocionales."""
        req = ModerationRequest(
            text="Entren a https://tours-truchos.com/promo para reservar traslados directos.",
            entity_type="review",
        )
        res = self.service.analyze_content(req)
        self.assertTrue(res.requiere_revision)
        self.assertEqual(res.categoria, "SPAM_COMERCIAL")
        self.assertIn("enlaces externos", res.motivo)

    def test_doxxing_sensitive_data_detected(self):
        """Detecta publicación no autorizada de DNI o datos personales."""
        req = ModerationRequest(
            text="El guía se llama Carlos, su DNI es 34888999 y vive en su domicilio particular.",
            entity_type="review",
        )
        res = self.service.analyze_content(req)
        self.assertTrue(res.requiere_revision)
        self.assertEqual(res.categoria, "DIVULGACION_DATOS_SENSIBLES")
        self.assertIn("datos personales", res.motivo)

    def test_threats_and_violence_detected(self):
        """Detecta amenazas e intimidación directa."""
        req = ModerationRequest(
            text="La próxima vez que vaya te voy a romper todo el auto a la salida.",
            entity_type="review",
        )
        res = self.service.analyze_content(req)
        self.assertTrue(res.requiere_revision)
        self.assertEqual(res.categoria, "AMENAZAS_VIOLENCIA")
        self.assertIn("amenazas", res.motivo)

    def test_harassment_smear_campaign_detected(self):
        """Detecta campañas de acoso o escrache dirigidas a fundir el negocio."""
        req = ModerationRequest(
            text="Vamos a ir todos los días a escrachar este local para arruinarle el negocio al dueño.",
            entity_type="review",
        )
        res = self.service.analyze_content(req)
        self.assertTrue(res.requiere_revision)
        self.assertEqual(res.categoria, "ACOSO_HOSTIGAMIENTO")


class TestModerationRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.patcher = patch("app.core.config.settings.gemini_api_key", "")
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_get_categories_endpoint(self):
        """Verifica que el catálogo de categorías devuelva las políticas definidas."""
        response = self.client.get("/moderation/categories")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(len(data), 5)
        codigos = [c["codigo"] for c in data]
        self.assertIn("SPAM_COMERCIAL", codigos)
        self.assertIn("ACOSO_HOSTIGAMIENTO", codigos)
        self.assertIn("AMENAZAS_VIOLENCIA", codigos)
        self.assertIn("DIVULGACION_DATOS_SENSIBLES", codigos)

    def test_analyze_endpoint_clean_content(self):
        """Verifica el endpoint POST /moderation/analyze con texto limpio."""
        response = self.client.post(
            "/moderation/analyze",
            json={
                "text": "Lugar muy lindo y tranquilo para ir con amigos a merendar.",
                "entity_type": "review",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["requiere_revision"])
        self.assertIsNone(data["categoria"])

    def test_analyze_endpoint_spam_content(self):
        """Verifica el endpoint POST /moderation/analyze con detección de spam."""
        response = self.client.post(
            "/moderation/analyze",
            json={
                "text": "Comunicate a mi WhatsApp 2614567890 para traslados privados.",
                "entity_type": "review",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["requiere_revision"])
        self.assertEqual(data["categoria"], "SPAM_COMERCIAL")


if __name__ == "__main__":
    unittest.main()
