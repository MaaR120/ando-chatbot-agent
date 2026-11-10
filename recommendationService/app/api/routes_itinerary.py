"""
Planificación de itinerarios con LLM (US-GDI-02 / US-GDI-04).
Ando Recommendation & AI Service.
"""
from fastapi import APIRouter, HTTPException, status

from app.schemas.itinerary_plan import ItineraryPlanRequest, ItineraryPlanResponse
from app.services.itinerary_planner_service import ItineraryPlannerService, LlmUnavailableError

router = APIRouter(prefix="/itinerary", tags=["itinerary"])


@router.post(
    "/plan",
    response_model=ItineraryPlanResponse,
    status_code=status.HTTP_200_OK,
    summary="Planificar un itinerario día por día con LLM (US-GDI-02 / US-GDI-04)",
    description=(
        "El modelo decide qué lugares se visitan cada día a partir de los parámetros del viaje y de los "
        "POIs reales disponibles. Devuelve 504 si ningún proveedor de LLM responde a tiempo (15 s) o "
        "si no devuelve un plan válido; no hay planificación de respaldo por reglas."
    ),
)
def plan_itinerary_endpoint(payload: ItineraryPlanRequest) -> ItineraryPlanResponse:
    try:
        return ItineraryPlannerService().plan(payload)
    except LlmUnavailableError as e:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno al planificar el itinerario con IA: {str(e)}",
        )
