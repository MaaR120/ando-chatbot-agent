"""
Clasificación temática batch de consultas al asistente (US-RYI-04).

Recibe los primeros caracteres de los mensajes de usuario de una semana y devuelve,
para cada uno, una de las categorías temáticas del reporte de uso del asistente.
Usa el mismo orden de proveedores LLM que el resto del servicio (Groq / Gemini / OpenAI)
y, si ninguno responde, recurre a una clasificación heurística por palabras clave.
"""
import json
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.schemas.assistant import (
    QUERY_TOPIC_CATEGORIES,
    AssistantClassifyRequest,
    AssistantClassifyResponse,
)

CLASSIFICATION_SYSTEM_PROMPT = (
    "Clasificas consultas que turistas le hacen al asistente de 'Ando' (turismo en Mendoza). "
    "Para cada consulta numerada elegí EXACTAMENTE una categoría de esta lista: "
    + ", ".join(f'"{c}"' for c in QUERY_TOPIC_CATEGORIES)
    + ". Criterios: 'información turística' = datos sobre lugares, horarios, precios, clima o "
    "transporte; 'ayuda con itinerario' = crear, consultar o modificar un viaje/itinerario; "
    "'recomendaciones' = pide sugerencias de qué hacer, visitar o dónde comer; "
    "'soporte de plataforma' = uso de la app, cuenta, errores o contacto; 'otros' = el resto. "
    'Respondé solo JSON con la forma {"categorias": ["...", "..."]}, una entrada por consulta '
    "y en el mismo orden."
)

_KEYWORDS: List[Tuple[str, List[str]]] = [
    (
        "soporte de plataforma",
        ["contrasena", "cuenta", "sesion", "error", "no funciona", "no anda", "soporte",
         "app", "aplicacion", "perfil", "notificacion", "registr", "bug", "ayuda con la"],
    ),
    (
        "ayuda con itinerario",
        ["itinerario", "viaje", "ruta", "parada", "agenda", "planific", "organiz", "dia 1",
         "dias", "cronograma", "reorden"],
    ),
    (
        "recomendaciones",
        ["recomend", "suger", "que puedo hacer", "que hacer", "que visitar", "donde comer",
         "donde ir", "mejor", "mejores", "conviene", "opciones", "ideas"],
    ),
    (
        "información turística",
        ["horario", "abre", "cierra", "precio", "cuesta", "cuanto sale", "donde queda",
         "como llego", "clima", "bodega", "museo", "parque", "restaurante", "termas",
         "montana", "aconcagua", "transporte", "colectivo", "entrada", "mendoza"],
    ),
]


def _normalize(text: str) -> str:
    stripped = unicodedata.normalize("NFD", text or "")
    stripped = "".join(ch for ch in stripped if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", stripped.lower()).strip()


def classify_heuristically(text: str) -> str:
    normalized = _normalize(text)
    for category, keywords in _KEYWORDS:
        if any(keyword in normalized for keyword in keywords):
            return category
    return "otros"


class QueryClassificationService:
    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        timeout_seconds: float = 20.0,
    ):
        self.gemini_api_key = gemini_api_key if gemini_api_key is not None else settings.gemini_api_key
        self.openai_api_key = openai_api_key if openai_api_key is not None else settings.openai_api_key
        self.groq_api_key = groq_api_key if groq_api_key is not None else settings.groq_api_key
        self.timeout_seconds = timeout_seconds

    def classify(self, request: AssistantClassifyRequest) -> AssistantClassifyResponse:
        queries = [q[:50] for q in request.queries]
        if not queries:
            return AssistantClassifyResponse(categories=[], model_used="none")

        llm_result = self._classify_with_llm(queries)
        if llm_result:
            categories, tokens, model = llm_result
            return AssistantClassifyResponse(categories=categories, tokens_used=tokens, model_used=model)

        return AssistantClassifyResponse(
            categories=[classify_heuristically(q) for q in queries],
            tokens_used=0,
            model_used="deterministic-fallback",
        )

    def _classify_with_llm(self, queries: List[str]) -> Optional[Tuple[List[str], int, str]]:
        user_prompt = "\n".join(f"{idx + 1}. {query}" for idx, query in enumerate(queries))
        attempts = []
        if self.groq_api_key and settings.llm_provider in ["groq", "auto", "gemini"]:
            attempts.append(self._call_groq)
        if self.gemini_api_key:
            attempts.append(self._call_gemini)
        if self.openai_api_key and settings.llm_provider == "openai":
            attempts.append(self._call_openai)

        for attempt in attempts:
            try:
                result = attempt(user_prompt)
            except Exception:
                result = None
            if not result:
                continue
            raw_text, tokens, model = result
            categories = self._parse_categories(raw_text, len(queries))
            if categories:
                return categories, tokens, model
        return None

    @staticmethod
    def _parse_categories(raw_text: str, expected: int) -> Optional[List[str]]:
        try:
            parsed: Dict = json.loads(raw_text)
        except (TypeError, ValueError):
            return None
        raw_categories = parsed.get("categorias") if isinstance(parsed, dict) else None
        if not isinstance(raw_categories, list) or len(raw_categories) != expected:
            return None
        valid = {_normalize(c): c for c in QUERY_TOPIC_CATEGORIES}
        return [valid.get(_normalize(str(item)), "otros") for item in raw_categories]

    def _call_chat_completions(
        self, url: str, api_key: str, model: str, user_prompt: str
    ) -> Optional[Tuple[str, int]]:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            resp = client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
        if resp.status_code != 200:
            return None
        data = resp.json()
        raw_text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        tokens = data.get("usage", {}).get("total_tokens", 0)
        return (raw_text, tokens) if raw_text else None

    def _call_groq(self, user_prompt: str) -> Optional[Tuple[str, int, str]]:
        model = "openai/gpt-oss-120b"
        result = self._call_chat_completions(
            "https://api.groq.com/openai/v1/chat/completions", self.groq_api_key, model, user_prompt
        )
        return (result[0], result[1], f"groq/{model}") if result else None

    def _call_openai(self, user_prompt: str) -> Optional[Tuple[str, int, str]]:
        model = "gpt-4o-mini"
        result = self._call_chat_completions(
            "https://api.openai.com/v1/chat/completions", self.openai_api_key, model, user_prompt
        )
        return (result[0], result[1], model) if result else None

    def _call_gemini(self, user_prompt: str) -> Optional[Tuple[str, int, str]]:
        payload = {
            "contents": [{"parts": [{"text": CLASSIFICATION_SYSTEM_PROMPT}, {"text": user_prompt}]}],
            "generationConfig": {"response_mime_type": "application/json", "temperature": 0.0},
        }
        candidate_models = [m for m in [settings.llm_model, "gemini-2.5-flash", "gemini-flash-latest"] if m and m.startswith("gemini")]
        seen = set()
        models_to_try = [m for m in candidate_models if not (m in seen or seen.add(m))]

        with httpx.Client(timeout=self.timeout_seconds) as client:
            for model_name in models_to_try:
                url = (
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model_name}:generateContent?key={self.gemini_api_key}"
                )
                try:
                    resp = client.post(url, json=payload)
                except Exception:
                    continue
                if resp.status_code == 200:
                    data = resp.json()
                    raw_text = (
                        data.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", "")
                        .strip()
                    )
                    tokens = data.get("usageMetadata", {}).get("totalTokenCount", 0)
                    if raw_text:
                        return raw_text, tokens, model_name
                elif resp.status_code in [401, 402, 403, 429]:
                    break
        return None
