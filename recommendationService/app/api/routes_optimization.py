"""
Route Optimization API Endpoints (US-MRIA-05).
Ando Recommendation & Routing Service (MRIA).
"""
from fastapi import APIRouter, HTTPException, status
from app.schemas.route_optimization import (
    RouteOptimizationRequest,
    RouteOptimizationResponse,
)
from app.services.route_optimization_service import RouteOptimizationService

router = APIRouter(prefix="/optimization", tags=["optimization"])


@router.post(
    "/route",
    response_model=RouteOptimizationResponse,
    status_code=status.HTTP_200_OK,
    summary="Optimizar ruta e itinerario diario de POIs mediante Google OR-Tools (US-MRIA-05)",
    description=(
        "Ordena automáticamente las paradas de un itinerario minimizando tiempos y distancias "
        "de traslado mediante algoritmos determinísticos de ruteo con ventanas de tiempo (TSPTW). "
        "Calcula horas estimadas de llegada, tiempos de traslado y detecta conflictos de horario comercial."
    ),
)
def optimize_route_endpoint(payload: RouteOptimizationRequest) -> RouteOptimizationResponse:
    try:
        service = RouteOptimizationService()
        return service.optimize_route(payload)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno al optimizar la ruta con OR-Tools: {str(e)}",
        )
