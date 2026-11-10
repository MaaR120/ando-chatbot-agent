"""
Content Moderation API Endpoints (US-MRIA-10).
Ando Recommendation & Routing Service (MRIA).
"""
from typing import List
from fastapi import APIRouter, HTTPException, status
from app.schemas.content_moderation import (
    ModerationRequest,
    ModerationResponse,
    ModerationCategoryItem,
)
from app.services.content_moderator import (
    ContentModeratorService,
    MODERATION_CATEGORIES,
)

router = APIRouter(prefix="/moderation", tags=["moderation"])


@router.post(
    "/analyze",
    response_model=ModerationResponse,
    status_code=status.HTTP_200_OK,
    summary="Analizar texto de reseña o comentario con Inteligencia Artificial (US-MRIA-10)",
    description=(
        "Analiza el contenido contextual de reseñas publicadas por turistas o respuestas de prestadores "
        "para detectar spam comercial, acoso, amenazas, estafas o doxxing mediante LLM (Gemini Flash / OpenAI). "
        "Retorna un dictamen estructurado indicando si requiere revisión administrativa humana."
    ),
)
def analyze_content_endpoint(payload: ModerationRequest) -> ModerationResponse:
    try:
        service = ContentModeratorService()
        return service.analyze_content(payload)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno al analizar contenido con IA: {str(e)}",
        )


@router.get(
    "/categories",
    response_model=List[ModerationCategoryItem],
    status_code=status.HTTP_200_OK,
    summary="Listar categorías de moderación contextual (US-MRIA-10)",
    description="Retorna el catálogo de categorías y políticas de moderación aplicadas por la Inteligencia Artificial.",
)
def get_moderation_categories() -> List[ModerationCategoryItem]:
    return MODERATION_CATEGORIES
