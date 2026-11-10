"""
Recommendation API Endpoints.
US-MRIA-04: History-based POI Recommendation.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.schemas.recommendation_history import (
    HistoryRecommendationRequest,
    HistoryRecommendationResponse,
)
from app.schemas.collaborative_recommendation import (
    CollaborativeRecommendationRequest,
    CollaborativeRecommendationResponse,
)
from app.services.history_recommendation_service import HistoryRecommendationService
from app.services.collaborative_service import CollaborativeRecommendationService

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post(
    "/history",
    response_model=HistoryRecommendationResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtener recomendaciones de POIs basadas en el historial del turista (US-MRIA-04)",
    description=(
        "Calcula recomendaciones determinísticas basadas en las 3 fuentes de historial: "
        "itinerarios finalizados, valoraciones positivas (>=4 estrellas) y POIs favoritos. "
        "Si el usuario no cumple la precondición (>=1 itinerario finalizado o >=5 valoraciones), "
        "retorna has_sufficient_history: false y used_fallback: true sin producir error."
    ),
)
def get_history_recommendations(
    payload: HistoryRecommendationRequest,
    db: Session = Depends(get_db),
) -> HistoryRecommendationResponse:
    try:
        service = HistoryRecommendationService(db=db)
        return service.get_history_recommendations(payload, db=db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno al calcular recomendaciones por historial: {str(e)}",
        )


@router.get(
    "/history/config",
    summary="Obtener configuración de pesos del algoritmo de historial",
    description="Retorna los pesos y parámetros configurados para US-MRIA-04.",
)
def get_history_weights_config():
    return {
        "history_weights": settings.history_weights.to_dict(),
        "half_life_days": settings.half_life_days,
        "min_ratings_for_history": settings.min_ratings_for_history,
        "min_finished_itineraries_for_history": settings.min_finished_itineraries_for_history,
    }


@router.post(
    "/collaborative",
    response_model=CollaborativeRecommendationResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtener recomendaciones de POIs basadas en filtrado colaborativo - Otros como vos también visitaron (US-MRIA-09)",
    description=(
        "Aplica filtrado colaborativo basado en usuarios usando Cosine Similarity (Scikit-Learn). "
        "Compara preferencias de categorías, valoraciones, favoritos e itinerarios completados "
        "para encontrar los K usuarios más similares y sugerir POIs visitados por ellos que el "
        "usuario actual aún no conoce."
    ),
)
def get_collaborative_recommendations(
    payload: CollaborativeRecommendationRequest,
    db: Session = Depends(get_db),
) -> CollaborativeRecommendationResponse:
    try:
        service = CollaborativeRecommendationService(db=db)
        return service.get_collaborative_recommendations(payload, db=db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno al calcular recomendaciones colaborativas: {str(e)}",
        )


@router.get(
    "/collaborative/config",
    summary="Obtener configuración del algoritmo de filtrado colaborativo (US-MRIA-09)",
    description="Retorna los hiperparámetros y umbrales del modelo colaborativo.",
)
def get_collaborative_config():
    return {
        "min_global_ratings": 5,
        "default_k_neighbors": 10,
        "interaction_weight": 0.65,
        "category_weight": 0.35,
    }

