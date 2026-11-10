"""
Content Moderation Service using AI / LLM (US-MRIA-10).
Analyzes reviews and responses for contextual infractions (spam, doxxing, harassment, threats).
"""
import re
import json
from typing import Dict, Any, Optional, List
import httpx
from app.core.config import settings
from app.schemas.content_moderation import (
    ModerationRequest,
    ModerationResponse,
    ModerationCategoryItem,
)

MODERATION_CATEGORIES: List[ModerationCategoryItem] = [
    ModerationCategoryItem(
        codigo="SPAM_COMERCIAL",
        nombre="Spam o Publicidad No Solicitada",
        descripcion="Promoción encubierta de agencias externas, guías informales, números de contacto para venta de servicios o enlaces comerciales.",
        ejemplo="No compren acá, escríbanme al WhatsApp +54 9 261 555-1234 que les hago el tour por la mitad.",
    ),
    ModerationCategoryItem(
        codigo="CONTENIDO_ENGANOSO",
        nombre="Contenido Engañoso o Fraudulento",
        descripcion="Reseñas con información deliberadamente falsa, estafas o promociones dudosas.",
        ejemplo="Entren a este link http://premio-mendoza.com para ganar degustaciones gratis.",
    ),
    ModerationCategoryItem(
        codigo="ACOSO_HOSTIGAMIENTO",
        nombre="Acoso, Hostigamiento o Difamación",
        descripcion="Ataques dirigidos, escraches o difamación personal hacia guías, mozos, prestadores o turistas específicos.",
        ejemplo="El mozo Juan es un incompetente total y vamos a ir todos los días a arruinarle el negocio.",
    ),
    ModerationCategoryItem(
        codigo="AMENAZAS_VIOLENCIA",
        nombre="Amenazas o Incitación a la Violencia",
        descripcion="Mensajes con intimidación explícita, amenazas de daño físico o destrucción material.",
        ejemplo="Te voy a buscar a la salida del restaurante para romperte todo el auto.",
    ),
    ModerationCategoryItem(
        codigo="CONTENIDO_SEXUAL",
        nombre="Contenido Sexual Explícito",
        descripcion="Insinuaciones o descripciones sexuales inapropiadas en el marco de la reseña turística.",
        ejemplo="Servicios íntimos con las chicas de la cabaña llamar al...",
    ),
    ModerationCategoryItem(
        codigo="DIVULGACION_DATOS_SENSIBLES",
        nombre="Divulgación de Datos Personales (Doxxing)",
        descripcion="Publicación no autorizada de números de DNI, domicilios particulares, teléfonos privados o información sensible de terceros.",
        ejemplo="El dueño vive en calle Belgrano 450 y su DNI es 35.123.456, vayan a buscarlo ahí.",
    ),
]


SYSTEM_PROMPT = """Eres el motor de Inteligencia Artificial para la moderación contextual de contenido de 'Ando', una plataforma turística de Mendoza, Argentina.
Tu misión es analizar el texto de una reseña o respuesta y determinar si contiene infracciones graves que requieran REVISIÓN ADMINISTRATIVA humana.

Categorías posibles de infracción:
1. SPAM_COMERCIAL: Venta de tours privados por fuera, enlaces, solicitudes de contacto a WhatsApp externo, publicidad no autorizada.
2. CONTENIDO_ENGANOSO: Estafas, links dudosos, promociones falsas.
3. ACOSO_HOSTIGAMIENTO: Escraches personales, ataques sistemáticos o difamación hacia trabajadores o turistas.
4. AMENAZAS_VIOLENCIA: Amenazas de agresiones físicas o daños materiales.
5. CONTENIDO_SEXUAL: Contenido sexual explícito.
6. DIVULGACION_DATOS_SENSIBLES: Publicación de teléfonos particulares, DNI o direcciones privadas (Doxxing).

IMPORTANTE:
- Críticas negativas legítimas sobre el servicio, la comida, los precios o las demoras NO son infracciones (requiere_revision = false).
- Solo marca requiere_revision = true si detectas claramente una de las categorías anteriores.

Debes responder ÚNICAMENTE un objeto JSON válido con la siguiente estructura exacta:
{
  "requiere_revision": true o false,
  "categoria": "CODIGO_DE_CATEGORIA" o null,
  "motivo": "Explicación breve en español" o null,
  "nivel_confianza": float entre 0.0 y 1.0,
  "palabras_clave_detectadas": ["fragmento1", "fragmento2"]
}
"""


class ContentModeratorService:
    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        llm_model: Optional[str] = None,
        timeout_seconds: float = 8.0,
    ):
        self.gemini_api_key = gemini_api_key if gemini_api_key is not None else settings.gemini_api_key
        self.openai_api_key = openai_api_key if openai_api_key is not None else settings.openai_api_key
        self.llm_model = llm_model or settings.llm_model or "gemini-3-flash-preview"
        self.timeout_seconds = timeout_seconds

    def analyze_content(self, request: ModerationRequest) -> ModerationResponse:
        """
        Analiza el texto mediante el LLM configurado (Gemini / OpenAI).
        Si no hay API key o hay fallo de red, recurre al motor heurístico de respaldo.
        """
        text = request.text.strip()
        if not text:
            return ModerationResponse(
                requiere_revision=False,
                categoria=None,
                motivo=None,
                nivel_confianza=1.0,
                palabras_clave_detectadas=[],
                modelo_utilizado="rule-validator",
            )

        # 1. Intentar con Google Gemini si la key está disponible
        if self.gemini_api_key:
            try:
                res = self._call_gemini_api(text, request.entity_type)
                if res:
                    return res
            except Exception:
                pass  # Fallback a heurístico

        # 2. Intentar con OpenAI si la key está disponible
        if self.openai_api_key and settings.llm_provider == "openai":
            try:
                res = self._call_openai_api(text, request.entity_type)
                if res:
                    return res
            except Exception:
                pass

        # 3. Motor Heurístico de Respaldo (NLP Regex & Patterns)
        return self._heuristic_analysis(text, request.entity_type)

    def _call_gemini_api(self, text: str, entity_type: str) -> Optional[ModerationResponse]:
        user_message = f"Contenido a analizar (Tipo: {entity_type}):\n\"\"\"\n{text}\n\"\"\""
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": SYSTEM_PROMPT},
                        {"text": user_message},
                    ]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1,
            },
        }

        candidate_models = [m for m in [self.llm_model, "gemini-3-flash-preview", "gemini-3.1-flash-lite-preview", "gemini-flash-latest"] if m and m.startswith("gemini")]
        # Eliminar duplicados preservando orden
        seen = set()
        models_to_try = [m for m in candidate_models if not (m in seen or seen.add(m))]

        with httpx.Client(timeout=self.timeout_seconds) as client:
            for model_name in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.gemini_api_key}"
                try:
                    resp = client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_text = (
                            data.get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [{}])[0]
                            .get("text", "")
                        )
                        if raw_text:
                            parsed = json.loads(raw_text)
                            return ModerationResponse(
                                requiere_revision=bool(parsed.get("requiere_revision", False)),
                                categoria=parsed.get("categoria"),
                                motivo=parsed.get("motivo"),
                                nivel_confianza=float(parsed.get("nivel_confianza", 0.95)),
                                palabras_clave_detectadas=parsed.get("palabras_clave_detectadas", []),
                                modelo_utilizado=model_name,
                            )
                except Exception:
                    continue
        return None

    def _call_openai_api(self, text: str, entity_type: str) -> Optional[ModerationResponse]:
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Tipo: {entity_type}\nTexto: {text}"},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }

        with httpx.Client(timeout=self.timeout_seconds) as client:
            resp = client.post(
                url,
                headers={"Authorization": f"Bearer {self.openai_api_key}"},
                json=payload,
            )
            if resp.status_code == 200:
                data = resp.json()
                raw_json = data["choices"][0]["message"]["content"]
                parsed = json.loads(raw_json)
                return ModerationResponse(
                    requiere_revision=bool(parsed.get("requiere_revision", False)),
                    categoria=parsed.get("categoria"),
                    motivo=parsed.get("motivo"),
                    nivel_confianza=float(parsed.get("nivel_confianza", 0.95)),
                    palabras_clave_detectadas=parsed.get("palabras_clave_detectadas", []),
                    modelo_utilizado="gpt-4o-mini",
                )
        return None

    def _heuristic_analysis(self, text: str, entity_type: str) -> ModerationResponse:
        """
        Análisis heurístico determinístico de reglas para offline, pruebas y fallback.
        """
        text_lower = text.lower()

        # 1. Detección de Teléfonos / WhatsApp comercial (SPAM_COMERCIAL / DIVULGACION_DATOS_SENSIBLES)
        phone_match = re.search(
            r"(?:(?:\+?54\s?9?\s?)?(?:0?[1-9]\d{1,3})[\s\-]?(?:15[\s\-]?)?\d{3}[\s\-]?\d{4})|(?:\b\d{7,11}\b)",
            text,
        )
        has_whatsapp = any(w in text_lower for w in ["whatsapp", "wsp", "escribime al", "comunicate al", "llamame al", "tour privado", "chofer privado", "mi número es", "mi numero es"])
        has_url = bool(re.search(r"https?://[^\s]+|www\.[^\s]+", text_lower))

        if phone_match and has_whatsapp:
            matched_phone = phone_match.group(0)
            return ModerationResponse(
                requiere_revision=True,
                categoria="SPAM_COMERCIAL",
                motivo="Se detectó promoción de servicios externos o contacto comercial no autorizado.",
                nivel_confianza=0.92,
                palabras_clave_detectadas=[matched_phone, "contacto_externo"],
                modelo_utilizado="heuristic-nlp-engine",
            )

        if has_url:
            matched_url = re.search(r"https?://[^\s]+|www\.[^\s]+", text).group(0)
            return ModerationResponse(
                requiere_revision=True,
                categoria="SPAM_COMERCIAL",
                motivo="El comentario contiene enlaces externos no permitidos.",
                nivel_confianza=0.90,
                palabras_clave_detectadas=[matched_url],
                modelo_utilizado="heuristic-nlp-engine",
            )

        # 2. Detección de DNI o Doxxing (DIVULGACION_DATOS_SENSIBLES)
        dni_match = re.search(r"\b(?:dni|documento|cuil|cuit)\s*(?:es|:|=|número|numero)?\s*([0-9\.\s]{7,12})\b", text_lower)
        if dni_match or (phone_match and any(w in text_lower for w in ["su teléfono personal", "su celular", "su casa", "vive en", "su domicilio"])):
            return ModerationResponse(
                requiere_revision=True,
                categoria="DIVULGACION_DATOS_SENSIBLES",
                motivo="El contenido parece divulgar datos personales o sensibles de terceros (Doxxing).",
                nivel_confianza=0.91,
                palabras_clave_detectadas=[dni_match.group(0) if dni_match else phone_match.group(0)],
                modelo_utilizado="heuristic-nlp-engine",
            )

        # 3. Detección de Amenazas y Violencia (AMENAZAS_VIOLENCIA)
        threat_patterns = [
            "te voy a romper", "te vamos a romper", "te voy a buscar", "lo voy a buscar",
            "sé dónde vivís", "se donde vivis", "lo vamos a prender fuego", "van a pagar",
            "lo voy a matar", "les vamos a destruir", "te voy a hacer mierda"
        ]
        detected_threats = [p for p in threat_patterns if p in text_lower]
        if detected_threats:
            return ModerationResponse(
                requiere_revision=True,
                categoria="AMENAZAS_VIOLENCIA",
                motivo="Se detectaron expresiones con amenazas directas o intimidación física.",
                nivel_confianza=0.95,
                palabras_clave_detectadas=detected_threats,
                modelo_utilizado="heuristic-nlp-engine",
            )

        # 4. Detección de Acoso u Hostigamiento (ACOSO_HOSTIGAMIENTO)
        harass_patterns = [
            "escrachar", "escrache", "haganle un escrache",
            "arruinarle el negocio", "arruinar el negocio", "fundir el negocio", "vamos a fundir",
            "hay que lincharlo", "es un ladrón y estafador", "son unos chorros y delincuentes"
        ]
        detected_harass = [h for h in harass_patterns if h in text_lower]
        if detected_harass:
            return ModerationResponse(
                requiere_revision=True,
                categoria="ACOSO_HOSTIGAMIENTO",
                motivo="Se detectaron intenciones de difamación, acoso u hostigamiento sistemático.",
                nivel_confianza=0.88,
                palabras_clave_detectadas=detected_harass,
                modelo_utilizado="heuristic-nlp-engine",
            )

        # 5. Texto limpio
        return ModerationResponse(
            requiere_revision=False,
            categoria=None,
            motivo=None,
            nivel_confianza=0.95,
            palabras_clave_detectadas=[],
            modelo_utilizado="heuristic-nlp-engine",
        )
