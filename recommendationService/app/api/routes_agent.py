"""
LangChain Tourist Agent Endpoints with Conversation History.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    ConversationItem,
    ConversationMessageItem,
)
from app.schemas.assistant import ChatMessageItem
from app.agent.agent import AndoTouristAgent
from app.services.chat_history_service import (
    ChatHistoryService,
    DEFAULT_DEMO_USER_ID,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


@router.get(
    "/conversations",
    response_model=List[ConversationItem],
    status_code=status.HTTP_200_OK,
    summary="Listar historial de conversaciones del usuario",
)
def list_conversations(
    user_id: Optional[str] = Query(default=None, description="UUID del usuario"),
    limit: int = Query(default=30, ge=1, le=100),
) -> List[ConversationItem]:
    try:
        service = ChatHistoryService(user_id=user_id or DEFAULT_DEMO_USER_ID)
        conversations = service.list_conversations(limit=limit)
        return [ConversationItem(**c) for c in conversations]
    except Exception:
        logger.exception("Error al listar conversaciones del usuario")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener las conversaciones.",
        )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=List[ConversationMessageItem],
    status_code=status.HTTP_200_OK,
    summary="Obtener mensajes de una conversación",
)
def get_conversation_messages(
    conversation_id: str,
    user_id: Optional[str] = Query(default=None, description="UUID del usuario"),
) -> List[ConversationMessageItem]:
    try:
        service = ChatHistoryService(user_id=user_id or DEFAULT_DEMO_USER_ID)
        messages = service.get_conversation_messages(conversation_id)
        return [ConversationMessageItem(**m) for m in messages]
    except Exception:
        logger.exception("Error al obtener mensajes de la conversación")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al recuperar los mensajes.",
        )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_200_OK,
    summary="Eliminar una conversación",
)
def delete_conversation(
    conversation_id: str,
    user_id: Optional[str] = Query(default=None, description="UUID del usuario"),
):
    try:
        service = ChatHistoryService(user_id=user_id or DEFAULT_DEMO_USER_ID)
        deleted = service.delete_conversation(conversation_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversación no encontrada o no pertenece al usuario.",
            )
        return {"status": "ok", "deleted": True}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error al eliminar conversación")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar la conversación.",
        )


@router.post(
    "/chat",
    response_model=AgentChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Conversar con el Agente Turístico Inteligente (LangChain + Tools + Historial)",
    description=(
        "Envía un mensaje al agente conversacional de Ando. El agente decide autónomamente "
        "qué herramientas invocar (búsqueda en base de datos de POIs, recomendaciones, "
        "opiniones, itinerarios) para brindar una respuesta enriquecida y contextualizada."
    ),
)
def agent_chat_endpoint(payload: AgentChatRequest) -> AgentChatResponse:
    try:
        effective_user_id = payload.user_id or DEFAULT_DEMO_USER_ID
        history_service = ChatHistoryService(user_id=effective_user_id)

        # 1. Obtener o crear conversación en base de datos si aplica
        conv_id = None
        is_first_message = False
        try:
            conv_id = history_service.get_or_create_conversation(
                conversation_id=payload.conversation_id,
                title=payload.message[:40],
            )
            # Determinar si es el primer mensaje de la conversación para titularla
            existing_msgs = history_service.get_conversation_messages(conv_id)
            is_first_message = len(existing_msgs) == 0
        except Exception:
            logger.warning("No se pudo acceder a la BD para persistir la conversación. Continuando sin persistencia.")
            conv_id = payload.conversation_id

        # 2. Reconstruir historial si no vino en el payload pero existe en la BD
        effective_history = list(payload.history)
        if not effective_history and conv_id:
            try:
                db_messages = history_service.get_conversation_messages(conv_id)
                for msg in db_messages:
                    effective_history.append(
                        ChatMessageItem(rol=msg["rol"], contenido=msg["contenido"])
                    )
            except Exception:
                pass

        # 3. Ejecutar el agente turístico
        agent = AndoTouristAgent(user_id=effective_user_id)
        result = agent.run(
            message=payload.message,
            chat_history=effective_history,
        )

        response_text = result["output"]
        model_used = result["model_used"]

        # 4. Persistir mensaje del usuario y respuesta del agente en la base de datos
        if conv_id:
            try:
                history_service.add_message(
                    conversation_id=conv_id,
                    role="usuario",
                    content=payload.message,
                    update_title_if_first=is_first_message,
                )
                history_service.add_message(
                    conversation_id=conv_id,
                    role="asistente",
                    content=response_text,
                )
            except Exception:
                logger.warning("No se pudieron guardar los mensajes en la BD.")

        return AgentChatResponse(
            response=response_text,
            model_used=model_used,
            conversation_id=conv_id,
        )
    except Exception:
        # El detalle (SQL, trazas del proveedor LLM) va al log, nunca al cliente.
        logger.exception("Error al procesar mensaje con el agente")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al procesar el mensaje. Intentá de nuevo más tarde.",
        )
