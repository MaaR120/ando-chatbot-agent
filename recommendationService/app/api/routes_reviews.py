"""
Review Summary API Endpoints (US-RYV-06).
Ando Recommendation & Routing Service (MRIA).
"""
from fastapi import APIRouter, HTTPException, status
from app.schemas.reviews_summary import (
    ReviewSummaryRequest,
    ReviewSummaryResponse,
)
from app.services.review_summary_service import ReviewSummaryService

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post(
    "/summary",
    response_model=ReviewSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Generar resumen automático de reseñas con IA (US-RYV-06)",
    description=(
        "Analiza las opiniones y puntuaciones registradas para un POI y genera un resumen conciso "
        "en lenguaje natural estructurado con fortalezas, aspectos negativos recurrentes y temas clave."
    ),
)
def generate_review_summary_endpoint(payload: ReviewSummaryRequest) -> ReviewSummaryResponse:
    try:
        service = ReviewSummaryService()
        return service.generate_summary(payload)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al generar resumen de reseñas con IA: {str(e)}",
        )
