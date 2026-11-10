"""
Tests de la clasificación temática de consultas al asistente (US-RYI-04).
"""
import json

from app.schemas.assistant import QUERY_TOPIC_CATEGORIES, AssistantClassifyRequest
from app.services.query_classification_service import (
    QueryClassificationService,
    classify_heuristically,
)


def _service_without_llm() -> QueryClassificationService:
    return QueryClassificationService(gemini_api_key="", openai_api_key="", groq_api_key="")


def test_heuristic_classification_covers_each_category():
    assert classify_heuristically("¿Qué bodegas me recomendás visitar?") == "recomendaciones"
    assert classify_heuristically("Quiero modificar mi itinerario del sábado") == "ayuda con itinerario"
    assert classify_heuristically("No puedo iniciar sesión en la app") == "soporte de plataforma"
    assert classify_heuristically("Horario del museo") == "información turística"
    assert classify_heuristically("hola") == "otros"


def test_fallback_without_llm_returns_one_category_per_query():
    response = _service_without_llm().classify(
        AssistantClassifyRequest(queries=["Horario del museo", "hola", "x" * 200])
    )

    assert response.model_used == "deterministic-fallback"
    assert response.categories == ["información turística", "otros", "otros"]
    assert all(category in QUERY_TOPIC_CATEGORIES for category in response.categories)


def test_empty_batch_returns_no_categories():
    response = _service_without_llm().classify(AssistantClassifyRequest(queries=[]))
    assert response.categories == []


def test_llm_answer_is_validated_and_normalized(monkeypatch):
    service = QueryClassificationService(gemini_api_key="", openai_api_key="", groq_api_key="key")
    answer = json.dumps({"categorias": ["Recomendaciones", "categoría inventada"]})
    monkeypatch.setattr(service, "_call_groq", lambda _prompt: (answer, 42, "groq/test"))

    response = service.classify(AssistantClassifyRequest(queries=["a", "b"]))

    assert response.categories == ["recomendaciones", "otros"]
    assert response.tokens_used == 42
    assert response.model_used == "groq/test"


def test_malformed_llm_answer_falls_back_to_heuristics(monkeypatch):
    service = QueryClassificationService(gemini_api_key="", openai_api_key="", groq_api_key="key")
    # Devuelve una categoría de menos: no se puede asignar a cada consulta
    monkeypatch.setattr(
        service, "_call_groq", lambda _prompt: (json.dumps({"categorias": ["otros"]}), 10, "groq/test")
    )

    response = service.classify(AssistantClassifyRequest(queries=["Horario del museo", "hola"]))

    assert response.model_used == "deterministic-fallback"
    assert response.categories == ["información turística", "otros"]
