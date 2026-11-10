"""
LangChain Tourist Agent Endpoints.
"""
from fastapi import APIRouter, HTTPException, status
from app.schemas.agent import AgentChatRequest, AgentChatResponse
from app.agent.agent import AndoTouristAgent

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
        agent = AndoTouristAgent()
        result = agent.run(
            message=payload.message,
            chat_history=payload.history,
            user_id=payload.user_id,
        )
        return AgentChatResponse(
            response=result["output"],
            model_used=result["model_used"],
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al procesar mensaje con el agente: {str(e)}",
        )

