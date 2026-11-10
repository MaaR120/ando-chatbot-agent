"""
LangChain Tool for personalized user recommendations.
Wraps History and Collaborative scoring engines.
"""
from typing import Optional, List, Dict, Any
from langchain_core.tools import tool
from app.core.database import get_session_factory
from app.services.history_recommendation_service import HistoryRecommendationService
from app.schemas.recommendation_history import HistoryRecommendationRequest


@tool
def get_personalized_recommendations_tool(
    user_id: str,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Obtiene recomendaciones personalizadas basadas en el historial previo, favoritos y valoraciones del turista.
    Parámetros:
    - user_id: UUID del usuario en la base de datos de Ando.
    - limit: Cantidad de recomendaciones deseadas (por defecto 5).
    """
    session_factory = get_session_factory()
    db = session_factory()
    try:
        service = HistoryRecommendationService(db)
        request = HistoryRecommendationRequest(user_id=user_id, limit=limit)
        response = service.get_recommendations(request)

        if not response or not response.recommendations:
            return []

        return [
            {
                "id": str(r.poi_id),
                "nombre": r.nombre,
                "score": round(r.score, 3),
                "motivo": r.motivo,
                "categorias": r.categorias,
                "departamento": r.departamento,
            }
            for r in response.recommendations
        ]
    except Exception as e:
        return [{"error": f"No se pudieron calcular recomendaciones personalizadas: {str(e)}"}]
    finally:
        db.close()

