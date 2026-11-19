"""
LangChain Tool de recomendaciones colaborativas ("a usuarios con gustos parecidos les gustó...").
Envuelve el motor de similitud coseno; complementa a la tool de historial.
"""

from typing import Any, Dict

from langchain_core.tools import tool

from app.core.config import settings
from app.core.database import get_session_factory
from app.schemas.collaborative_recommendation import CollaborativeRecommendationRequest
from app.services.collaborative_service import CollaborativeRecommendationService

MAX_LIMIT = settings.agent_max_limit


def build_collaborative_tool(user_id: str):
    @tool
    def get_similar_users_recommendations_tool(limit: int = settings.agent_default_limit) -> Dict[str, Any]:
        """
        Recomienda lugares que les gustaron a otros turistas con gustos parecidos al usuario actual.
        Parámetros:
        - limit: Cantidad de recomendaciones deseadas (si no lo pasas se usa el valor por defecto del servidor; se recorta al máximo del servidor).
        """
        with get_session_factory()() as db:
            response = CollaborativeRecommendationService(db).get_collaborative_recommendations(
                CollaborativeRecommendationRequest(user_id=user_id, limit=max(1, min(limit, MAX_LIMIT)))
            )

        if not response.has_sufficient_data or not response.recommendations:
            return {
                "mensaje": "Todavía no hay datos de otros turistas para recomendar. Usa get_personalized_recommendations_tool o search_pois_tool."
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
                }
                for r in response.recommendations
            ]
        }

    return get_similar_users_recommendations_tool
