"""
LangChain Tool for personalized user recommendations.
Wraps the History scoring engine.
"""

from typing import Any, Dict

from langchain_core.tools import tool

from app.core.database import get_session_factory
from app.schemas.recommendation_history import HistoryRecommendationRequest
from app.services.history_recommendation_service import HistoryRecommendationService

MAX_LIMIT = 20


@tool
def get_personalized_recommendations_tool(
    user_id: str,
    limit: int = 5,
) -> Dict[str, Any]:
    """
    Obtiene recomendaciones personalizadas basadas en el historial previo, favoritos y valoraciones del turista.
    Parámetros:
    - user_id: UUID del usuario en la base de datos de Ando.
    - limit: Cantidad de recomendaciones deseadas (por defecto 5, máximo 20).
    """
    with get_session_factory()() as db:
        request = HistoryRecommendationRequest(user_id=user_id, limit=min(limit, MAX_LIMIT))
        response = HistoryRecommendationService(db).get_history_recommendations(request)

    if not response.has_sufficient_history:
        return {
            "mensaje": "El usuario no tiene historial suficiente para recomendación personalizada. Usá search_pois_tool."
        }

    return {
        "recomendaciones": [
            {
                "id": r.poi_id,
                "nombre": r.nombre,
                "motivo": r.reason,
                "categorias": r.categorias,
                "precio_min": r.precio_min,
                "precio_max": r.precio_max,
                "ya_visitado": r.ya_visitado,
                "departamento": r.departamento,
            }
            for r in response.recommendations
        ]
    }
