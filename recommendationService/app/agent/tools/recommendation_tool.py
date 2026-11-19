"""
LangChain Tool for personalized user recommendations.
Wraps the History scoring engine.
"""

from typing import Any, Dict

from langchain_core.tools import tool

from app.core.config import settings
from app.core.database import get_session_factory
from app.schemas.recommendation_history import HistoryRecommendationRequest
from app.services.history_recommendation_service import HistoryRecommendationService

MAX_LIMIT = settings.agent_max_limit


def build_recommendation_tool(user_id: str):
    @tool
    def get_personalized_recommendations_tool(
        limit: int = settings.agent_default_limit,
    ) -> Dict[str, Any]:
        """
        Obtiene recomendaciones personalizadas basadas en el historial previo, favoritos y valoraciones del turista.
        Parámetros:
        - limit: Cantidad de recomendaciones deseadas (si no lo pasas se usa el valor por defecto del servidor; se recorta al máximo del servidor).
        """
        with get_session_factory()() as db:
            request = HistoryRecommendationRequest(
                user_id=user_id, limit=min(limit, MAX_LIMIT)
            )
            response = HistoryRecommendationService(db).get_history_recommendations(
                request
            )

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

    return get_personalized_recommendations_tool
