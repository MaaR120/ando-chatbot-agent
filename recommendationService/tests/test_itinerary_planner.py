"""
Tests de la planificación de itinerarios con LLM (US-GDI-02 / US-GDI-04).
"""
import json

import httpx
import pytest

from app.schemas.itinerary_plan import ItineraryPlanRequest, PlanCandidatePoi, PlanDayInfo
from app.services.itinerary_planner_service import ItineraryPlannerService, LlmUnavailableError


def _request(modo: str = "seleccionar") -> ItineraryPlanRequest:
    return ItineraryPlanRequest(
        modo=modo,
        dias=[
            PlanDayInfo(dia=1, fecha="2026-11-02", dia_semana="lunes"),
            PlanDayInfo(dia=2, fecha="2026-11-03", dia_semana="martes"),
        ],
        candidatos=[
            PlanCandidatePoi(poi_id="bodega", nombre="Bodega", categoria="Bodega", latitud=-33.0, longitud=-68.8),
            PlanCandidatePoi(poi_id="resto", nombre="Resto", categoria="Gastronomía", latitud=-33.0, longitud=-68.8),
            PlanCandidatePoi(
                poi_id="museo", nombre="Museo", categoria="Historia", latitud=-32.9, longitud=-68.8, dias_abierto=[2]
            ),
        ],
        intereses=["Bodega", "Gastronomía"],
        tipo_viaje="Pareja",
        cantidad_personas=2,
        presupuesto_diario=65000,
    )


def _service_with_answer(monkeypatch, answer: dict) -> ItineraryPlannerService:
    service = ItineraryPlannerService(gemini_api_key="", openai_api_key="", groq_api_key="key")
    monkeypatch.setattr(service, "_call_groq", lambda _prompt: (json.dumps(answer), 321, "groq/test"))
    return service


def test_prompt_includes_trip_data_and_real_places():
    prompt = ItineraryPlannerService(groq_api_key="key")._build_user_prompt(_request())

    assert "Tipo de viaje: Pareja" in prompt
    assert "65000" in prompt
    assert "[1] Bodega" in prompt
    assert "Abre: Días 2" in prompt


def test_numeric_ids_plan_is_resolved_to_uuids(monkeypatch):
    service = _service_with_answer(
        monkeypatch,
        {
            "dias": [
                {"dia": 1, "poi_ids": [1, 2]},
                {"dia": 2, "poi_ids": [3]},
            ],
        },
    )

    plan = service.plan(_request())

    assert [d.poi_ids for d in plan.dias] == [["bodega", "resto"], ["museo"]]


def test_valid_plan_is_returned_with_model_metadata(monkeypatch):
    service = _service_with_answer(
        monkeypatch,
        {
            "dias": [
                {"dia": 1, "poi_ids": ["bodega", "resto"], "motivo": "Vino y almuerzo"},
                {"dia": 2, "poi_ids": ["museo"]},
            ],
            "resumen": "Dos días tranquilos",
        },
    )

    plan = service.plan(_request())

    assert [d.poi_ids for d in plan.dias] == [["bodega", "resto"], ["museo"]]
    assert plan.dias[0].motivo == "Vino y almuerzo"
    assert plan.resumen == "Dos días tranquilos"
    assert plan.tokens_used == 321 and plan.model_used == "groq/test"


def test_invented_repeated_and_closed_places_are_discarded(monkeypatch):
    service = _service_with_answer(
        monkeypatch,
        {
            "dias": [
                # "inventado" no existe; "museo" no abre el día 1
                {"dia": 1, "poi_ids": ["bodega", "inventado", "museo"]},
                # "bodega" ya se usó el día 1; el día 9 no existe
                {"dia": 2, "poi_ids": ["bodega", "resto"]},
                {"dia": 9, "poi_ids": ["museo"]},
            ]
        },
    )

    plan = service.plan(_request())

    assert [d.poi_ids for d in plan.dias] == [["bodega"], ["resto"]]


def test_organize_mode_reports_leftovers(monkeypatch):
    service = _service_with_answer(monkeypatch, {"dias": [{"dia": 1, "poi_ids": ["bodega"]}]})

    plan = service.plan(_request("organizar"))

    assert [d.dia for d in plan.dias] == [1, 2]
    assert sorted(plan.sobrantes) == ["museo", "resto"]


def test_without_any_provider_configured_raises():
    service = ItineraryPlannerService(gemini_api_key="", openai_api_key="", groq_api_key="")
    with pytest.raises(LlmUnavailableError):
        service.plan(_request())


def test_timeout_or_unusable_answer_raises_instead_of_inventing_a_plan(monkeypatch):
    service = ItineraryPlannerService(gemini_api_key="", openai_api_key="", groq_api_key="key")

    def _timeout(_prompt):
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(service, "_call_groq", _timeout)
    with pytest.raises(LlmUnavailableError, match=r"(?:15|25) segundos"):
        service.plan(_request())

    monkeypatch.setattr(service, "_call_groq", lambda _prompt: ("esto no es json", 5, "groq/test"))
    with pytest.raises(LlmUnavailableError):
        service.plan(_request())

    monkeypatch.setattr(
        service, "_call_groq", lambda _prompt: (json.dumps({"dias": [{"dia": 1, "poi_ids": ["x"]}]}), 5, "groq/test")
    )
    with pytest.raises(LlmUnavailableError):
        service.plan(_request())
