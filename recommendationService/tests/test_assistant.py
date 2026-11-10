"""
Unit and integration tests for AI Assistant Chat Service & Endpoint (US-ACIA-01 / US-ACIA-02 / US-ACIA-06).
"""
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.assistant import AssistantChatRequest
from app.services.assistant_service import AssistantService


class TestAssistantService(unittest.TestCase):
    def setUp(self):
        self.service = AssistantService(gemini_api_key="", openai_api_key="", groq_api_key="")
        self.client = TestClient(app)

    def test_deterministic_fallback_with_poi_links(self):
        """Verifica que el fallback estructurado extrae y presenta los enlaces a POIs reales."""
        poi_context = (
            "POIS_REALES_DISPONIBLES_EN_BD:\n"
            '[1] "Bodega Catena Zapata" | Link: [Bodega Catena Zapata](app://poi/poi-uuid-1)\n'
            '[2] "Bodega Norton" | Link: [Bodega Norton](app://poi/poi-uuid-2)\n'
        )
        req = AssistantChatRequest(
            message="¿Qué bodegas económicas me recomendás?",
            poi_context=poi_context,
            user_preferences=["Bodegas y Viñedos"],
            language="es",
        )
        res = self.service.generate_chat_response(req)

        self.assertEqual(res.model_used, "deterministic-fallback")
        self.assertEqual(res.tokens_used, 0)
        self.assertIn("**Bodega Catena Zapata**", res.response)
        self.assertIn("**Bodega Norton**", res.response)
        self.assertIn("Según lo que buscas en Mendoza", res.response)

    def test_deterministic_fallback_multilanguage_english(self):
        """Verifica que el fallback estructurado responda en inglés cuando language='en' (US-ACIA-06)."""
        poi_context = (
            "POIS_REALES_DISPONIBLES_EN_BD:\n"
            '[1] "Bodega Trapiche" | Link: [Bodega Trapiche](app://poi/poi-uuid-3)\n'
        )
        req = AssistantChatRequest(
            message="Which wineries do you recommend?",
            poi_context=poi_context,
            language="en",
        )
        res = self.service.generate_chat_response(req)

        self.assertEqual(res.model_used, "deterministic-fallback")
        self.assertIn("Based on what you're looking for in Mendoza", res.response)
        self.assertIn("**Bodega Trapiche**", res.response)
        self.assertIn("interactive cards below", res.response)

    def test_deterministic_fallback_multilanguage_portuguese(self):
        """Verifica que el fallback estructurado responda en portugués cuando language='pt' (US-ACIA-06)."""
        poi_context = (
            "POIS_REALES_DISPONIBLES_EN_BD:\n"
            '[1] "Bodega Trapiche" | Link: [Bodega Trapiche](app://poi/poi-uuid-3)\n'
        )
        req = AssistantChatRequest(
            message="Quais vinícolas você recomenda?",
            poi_context=poi_context,
            language="pt",
        )
        res = self.service.generate_chat_response(req)

        self.assertEqual(res.model_used, "deterministic-fallback")
        self.assertIn("De acordo com o que você procura em Mendoza", res.response)
        self.assertIn("**Bodega Trapiche**", res.response)
        self.assertIn("cards interativos abaixo", res.response)

    def test_deterministic_fallback_unsupported_language_defaults_to_spanish(self):
        """Verifica que si el idioma es nulo o no soportado ('de'), se use español por defecto."""
        poi_context = (
            "POIS_REALES_DISPONIBLES_EN_BD:\n"
            '[1] "Bodega Trapiche" | Link: [Bodega Trapiche](app://poi/poi-uuid-3)\n'
        )
        req = AssistantChatRequest(
            message="Welche Weingüter empfehlen Sie?",
            poi_context=poi_context,
            language="de",
        )
        res = self.service.generate_chat_response(req)

        self.assertIn("Según lo que buscas en Mendoza", res.response)

    def test_deterministic_fallback_with_relaxation_note(self):
        """Verifica que si hubo relajación de criterios se incluye la nota amigable al turista (CA 4)."""
        poi_context = (
            "NOTA_IMPORTANTE_RELAJACION: No encontramos opciones por debajo de $5000, pero te mostramos las mejores alternativas.\n"
            "POIS_REALES_DISPONIBLES_EN_BD:\n"
            '[1] "Bodega Trapiche" | Link: [Bodega Trapiche](app://poi/poi-uuid-3)\n'
        )
        req = AssistantChatRequest(
            message="Bodegas por $3000",
            poi_context=poi_context,
        )
        res = self.service.generate_chat_response(req)

        self.assertIn("No encontramos opciones por debajo de $5000", res.response)
        self.assertIn("**Bodega Trapiche**", res.response)

    def test_gemini_api_success_mock(self):
        """Verifica que cuando Gemini responde exitosamente, se capturan la respuesta y los tokens."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": "¡Hola! En Luján de Cuyo te sugiero visitar [Bodega Catena Zapata](app://poi/poi-uuid-1)."
                            }
                        ]
                    }
                }
            ],
            "usageMetadata": {
                "totalTokenCount": 92,
            },
        }

        with patch("httpx.Client.post", return_value=mock_response):
            gemini_service = AssistantService(gemini_api_key="fake-key-123")
            req = AssistantChatRequest(
                message="Recomiéndame una bodega",
                poi_context='[Bodega Catena Zapata](app://poi/poi-uuid-1)',
            )
            res = gemini_service.generate_chat_response(req)

            self.assertEqual(res.tokens_used, 92)
            self.assertIn("[Bodega Catena Zapata](app://poi/poi-uuid-1)", res.response)
            self.assertNotEqual(res.model_used, "deterministic-fallback")

    def test_gemini_api_language_directive_injection(self):
        """Verifica que cuando se especifica 'en' o 'pt', se inyecte la directiva de idioma a la API LLM."""
        captured_payloads = []

        def mock_post(url, json=None, **kwargs):
            captured_payloads.append(json)
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "candidates": [{"content": {"parts": [{"text": "Hello! I recommend [Bodega Norton](app://poi/uuid)."}]}}],
                "usageMetadata": {"totalTokenCount": 50},
            }
            return mock_resp

        with patch("httpx.Client.post", side_effect=mock_post):
            gemini_service = AssistantService(gemini_api_key="fake-key-123", groq_api_key="")
            req = AssistantChatRequest(
                message="Where to drink wine?",
                language="en",
            )
            res = gemini_service.generate_chat_response(req)
            self.assertEqual(res.tokens_used, 50)
            self.assertEqual(len(captured_payloads), 1)
            sys_text = captured_payloads[0].get("system_instruction", {}).get("parts", [{}])[0].get("text", "")
            self.assertIn("MANDATORY LANGUAGE REQUIREMENT", sys_text)
            self.assertIn("ENGLISH", sys_text)

    def test_assistant_chat_endpoint_integration(self):
        """Verifica que el endpoint /assistant/chat responda HTTP 200 con el contrato esperado."""
        payload = {
            "message": "¿Dónde comer buen asado en Mendoza?",
            "poi_context": "POIS_REALES_DISPONIBLES_EN_BD:\n[1] \"Don Mario Parrilla\" | Link: [Don Mario Parrilla](app://poi/poi-uuid-4)",
            "user_preferences": ["Gastronomía"],
            "language": "en",
        }
        with patch.object(AssistantService, "_call_groq_api", return_value=None), \
             patch.object(AssistantService, "_call_gemini_api", return_value=None), \
             patch.object(AssistantService, "_call_openai_api", return_value=None):
            resp = self.client.post("/assistant/chat", json=payload)
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("response", data)
            self.assertIn("tokens_used", data)
            self.assertIn("model_used", data)
            self.assertTrue(len(data["response"]) > 0)
            self.assertIn("Based on what you're looking for in Mendoza", data["response"])

    def test_assistant_supports_20_history_messages(self):
        """Verifica que el asistente acepte y procese hasta 20 mensajes de historial (US-ACIA-07)."""
        history = [{"rol": "usuario" if i % 2 == 0 else "asistente", "contenido": f"Mensaje {i}"} for i in range(20)]
        req = AssistantChatRequest(
            message="Mensaje final 21",
            history=history,
            language="es",
        )
        res = self.service.generate_chat_response(req)
        self.assertIsNotNone(res.response)

    def test_support_fallback_does_not_expose_documentation_or_configuration(self):
        req = AssistantChatRequest(
            message="\u00bfC\u00f3mo gestiono mis POIs?",
            role="turista",
            support_documentation='{"soporte": {"instruccion_fallback": "internal config"}}',
        )

        res = self.service.generate_chat_response(req)

        self.assertIn("Canal de Contacto", res.response)
        self.assertIn("Ayuda y Soporte", res.response)
        self.assertNotIn("internal config", res.response)
        self.assertNotIn("{\"soporte\"", res.response)
        self.assertNotIn("app://", res.response)

    def test_support_fallback_does_not_return_full_manual(self):
        req = AssistantChatRequest(
            message="\u00bfC\u00f3mo uso Ando?",
            role="prestador",
            support_documentation="[MANUAL] Perfil\nContenido interno vigente\n[FAQ] Pregunta\nRespuesta",
        )

        res = self.service.generate_chat_response(req)

        self.assertIn("Canal de Contacto", res.response)
        self.assertNotIn("Contenido interno vigente", res.response)
        self.assertNotIn("Respuesta", res.response)

    def test_assistant_extract_params_endpoint(self):
        """Verifica que el endpoint /assistant/extract-params detecte intención de recomendación."""
        payload = {
            "message": "que actividades al aire libre puedo hacer?",
            "available_categories": ["Naturaleza", "Turismo Aventura", "Bodegas y Viñedos", "Gastronomía"],
            "available_departments": ["Luján de Cuyo", "Maipú", "San Rafael"],
        }
        resp = self.client.post("/assistant/extract-params", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["is_recommendation"])
        self.assertIn("Naturaleza", data["categories"])

    def test_assistant_extract_params_with_recent_messages(self):
        """Verifica que /assistant/extract-params acepte recent_messages para seguimiento contextual."""
        payload = {
            "message": "¿y algo más barato?",
            "available_categories": ["Bodegas y Viñedos", "Gastronomía"],
            "available_departments": ["Maipú", "Luján de Cuyo"],
            "current_context": {"categories": ["Bodegas y Viñedos"], "department": "Maipú"},
            "recent_messages": [
                {"rol": "usuario", "contenido": "Quiero visitar bodegas en Maipú"},
                {"rol": "asistente", "contenido": "Te recomiendo Bodega Trapiche y Bodega López"},
            ],
        }
        resp = self.client.post("/assistant/extract-params", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["is_recommendation"])


if __name__ == "__main__":
    unittest.main()
