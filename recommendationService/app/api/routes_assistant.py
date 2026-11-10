"""
AI Assistant API Endpoints (US-ACIA-01 / US-ACIA-02).
Ando Recommendation & AI Service.
"""
from fastapi import APIRouter, HTTPException, status
from app.schemas.assistant import (
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantClassifyRequest,
    AssistantClassifyResponse,
    AssistantExtractRequest,
    AssistantExtractResponse,
)
from app.services.assistant_service import AssistantService
from app.services.query_classification_service import QueryClassificationService

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post(
    "/chat",
    response_model=AssistantChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Generar respuesta conversacional del Asistente Turístico (US-ACIA-01 / US-ACIA-02)",
    description=(
        "Genera una respuesta conversacional basada en lenguaje natural asistida por LLM "
        "(Gemini / OpenAI), inyectando contexto de POIs reales de la base de datos de Mendoza "
        "y aplicando fallback determinístico resiliente en caso de timeout o agotamiento de cuota."
    ),
)
def assistant_chat_endpoint(payload: AssistantChatRequest) -> AssistantChatResponse:
    try:
        service = AssistantService()
        return service.generate_chat_response(payload)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno al procesar mensaje con el asistente IA: {str(e)}",
        )


@router.post(
    "/extract-params",
    response_model=AssistantExtractResponse,
    status_code=status.HTTP_200_OK,
    summary="Extraer intención de recomendación y parámetros estructurados con LLM (US-ACIA-02)",
    description=(
        "Analiza el mensaje del usuario con LLM para determinar semánticamente si existe intención "
        "de recomendación y extraer categorías, precio y ubicación para consulta a la base de datos."
    ),
)
def assistant_extract_params_endpoint(payload: AssistantExtractRequest) -> AssistantExtractResponse:
    try:
        service = AssistantService()
        return service.extract_intent_and_params(payload)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno al extraer parámetros con IA: {str(e)}",
        )


@router.post(
    "/classify-queries",
    response_model=AssistantClassifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Clasificar temáticamente un lote de consultas al asistente (US-RYI-04)",
    description=(
        "Clasifica cada consulta en una de las categorías del reporte de uso del asistente "
        "(información turística, ayuda con itinerario, recomendaciones, soporte de plataforma, otros) "
        "usando LLM, con fallback heurístico si no hay proveedor disponible."
    ),
)
def assistant_classify_queries_endpoint(payload: AssistantClassifyRequest) -> AssistantClassifyResponse:
    try:
        service = QueryClassificationService()
        return service.classify(payload)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno al clasificar consultas con IA: {str(e)}",
        )
