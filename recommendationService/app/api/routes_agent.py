"""
LangChain Tourist Agent Endpoints.
"""
import logging

from fastapi import APIRouter, HTTPException, status
from app.schemas.agent import AgentChatRequest, AgentChatResponse
from app.agent.agent import AndoTouristAgent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


@router.post(
    "/chat",
    response_model=AgentChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Conversar con el Agente Turístico Inteligente (LangChain + Tools)",
    description=(
        "Envía un mensaje al agente conversacional de Ando. El agente decide autónomamente "
        "qué herramientas invocar (búsqueda en base de datos de POIs, recomendaciones, "
        "opiniones, itinerarios) para brindar una respuesta enriquecida y contextualizada."
    ),
)
def agent_chat_endpoint(payload: AgentChatRequest) -> AgentChatResponse:
    try:
        agent = AndoTouristAgent(user_id=payload.user_id)
        result = agent.run(
            message=payload.message,
            chat_history=payload.history,
        )
        return AgentChatResponse(
            response=result["output"],
            model_used=result["model_used"],
        )
    except Exception:
        # El detalle (SQL, trazas del proveedor LLM) va al log, nunca al cliente.
        logger.exception("Error al procesar mensaje con el agente")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al procesar el mensaje. Intentá de nuevo más tarde.",
        )

