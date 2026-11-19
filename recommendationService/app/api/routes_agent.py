"""
LangChain Tourist Agent Endpoints with Conversation History.
"""

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from langgraph.errors import GraphRecursionError

from app.agent.agent import AndoTouristAgent
from app.agent.tools.pdf import PDF_DIR
from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    ChatMessageItem,
    ConversationItem,
    ConversationMessageItem,
    DemoUserItem,
)
from app.services.chat_history_service import (
    DEFAULT_DEMO_USER_ID,
    ChatHistoryService,
)
from app.services.user_service import list_tourists

logger = logging.getLogger(__name__)

# 413 (petición demasiado grande para los tokens por minuto) y 429 del proveedor LLM.
LLM_LIMIT_STATUS_CODES = (413, 429)
router = APIRouter(prefix="/agent", tags=["agent"])


@router.get(
    "/users",
    response_model=List[DemoUserItem],
    summary="Cuentas de turistas para el selector de sesión de la demo",
)
def list_demo_users(limit: int = Query(default=10, ge=1, le=50)) -> List[DemoUserItem]:
    try:
        return [DemoUserItem(**u) for u in list_tourists(limit)]
    except Exception:
        logger.exception("Error al listar usuarios")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener los usuarios.",
        )


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


@dataclass
class ChatTurn:
    """Lo que necesita un turno del chat: servicio de historial, ids y el historial para sembrar."""

    history_service: Optional[ChatHistoryService]
    conv_id: Optional[str]
    thread_id: str
    is_first_message: bool
    history: List[ChatMessageItem]


def _prepare_turn(payload: AgentChatRequest) -> ChatTurn:
    if not payload.user_id:
        # Sin sesión: no se guarda en la BD (las conversaciones son de un usuario). La memoria de
        # corto plazo igual funciona: la UI reenvía el conversation_id que devolvió el primer turno.
        return ChatTurn(None, None, payload.conversation_id or str(uuid.uuid4()), False, list(payload.history))

    history_service = ChatHistoryService(user_id=payload.user_id)

    # 1. Obtener o crear la conversación en la base de datos
    conv_id = None
    is_first_message = False
    try:
        conv_id = history_service.get_or_create_conversation(
            conversation_id=payload.conversation_id,
            title=payload.message[:40],
        )
        is_first_message = len(history_service.get_conversation_messages(conv_id)) == 0
    except Exception:
        logger.warning(
            "No se pudo acceder a la BD para persistir la conversación. Continuando sin persistencia."
        )
        conv_id = payload.conversation_id

    # 2. Historial de la BD: sólo siembra el checkpointer si todavía no conoce este hilo
    #    (por ejemplo, conversación vieja reabierta después de reiniciar el servidor).
    history = list(payload.history)
    if not history and conv_id:
        try:
            for msg in history_service.get_conversation_messages(conv_id):
                history.append(ChatMessageItem(rol=msg["rol"], contenido=msg["contenido"]))
        except Exception:
            pass

    # Sin BD no hay conversation_id: el turno corre en un hilo nuevo, sin memoria previa.
    thread_id = conv_id or str(uuid.uuid4())
    return ChatTurn(history_service, conv_id, thread_id, is_first_message, history)


def _persist_turn(turn: ChatTurn, message: str, result: Dict[str, Any]) -> None:
    """Guarda el mensaje del usuario y la respuesta (con razonamiento y tools) en la BD."""
    if not turn.history_service or not turn.conv_id:
        return
    try:
        turn.history_service.add_message(
            conversation_id=turn.conv_id,
            role="usuario",
            content=message,
            update_title_if_first=turn.is_first_message,
        )
        turn.history_service.add_message(
            conversation_id=turn.conv_id,
            role="asistente",
            content=result["output"],
            reasoning={"thought": result.get("thought"), "steps": result.get("steps", [])},
        )
    except Exception:
        logger.warning("No se pudieron guardar los mensajes en la BD.")


def _error_response(exc: Exception) -> HTTPException:
    """Traduce una excepción a un error para el cliente. El detalle (SQL, trazas) va sólo al log."""
    if isinstance(exc, GraphRecursionError):
        logger.warning("El agente alcanzó el límite de pasos (AGENT_MAX_ITERATIONS)")
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La consulta necesitó demasiados pasos. Probá dividirla en pedidos más chicos.",
        )
    logger.error("Error al procesar mensaje con el agente", exc_info=exc)
    if getattr(exc, "status_code", None) in LLM_LIMIT_STATUS_CODES:
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="El proveedor de IA alcanzó su límite de uso. Esperá un minuto e intentá de nuevo.",
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Error al procesar el mensaje. Intentá de nuevo más tarde.",
    )


@router.post(
    "/chat",
    response_model=AgentChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Conversar con el Agente Turístico Inteligente (LangChain + Tools + Historial)",
    description=(
        "Envía un mensaje al agente conversacional de Ando y devuelve la respuesta completa al "
        "final. Para ver el progreso mientras el agente trabaja, usar /agent/chat/stream."
    ),
)
def agent_chat_endpoint(payload: AgentChatRequest) -> AgentChatResponse:
    try:
        turn = _prepare_turn(payload)
        agent = AndoTouristAgent(user_id=payload.user_id)
        result = agent.run(message=payload.message, thread_id=turn.thread_id, chat_history=turn.history)
        _persist_turn(turn, payload.message, result)
        return AgentChatResponse(
            response=result["output"],
            model_used=result["model_used"],
            conversation_id=turn.thread_id,
            thought=result.get("thought"),
            steps=result.get("steps", []),
        )
    except Exception as exc:
        raise _error_response(exc)


def _sse(event: Dict[str, Any]) -> str:
    """Un evento Server-Sent Events: una línea 'data: <json>' y una línea en blanco."""
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


@router.post(
    "/chat/stream",
    summary="Conversar con el agente viendo su trabajo en vivo (Server-Sent Events)",
    description=(
        "Igual que /agent/chat, pero responde con un stream text/event-stream. Cada evento es un "
        "JSON con `type`: `start` (conversation_id), `reasoning` y `token` (fragmentos de "
        "razonamiento y de respuesta), `tool_call` (tool, argumentos y motivo), `tool_result` "
        "(resultado de la tool), `done` (respuesta final completa) o `error` (detail)."
    ),
)
def agent_chat_stream_endpoint(payload: AgentChatRequest) -> StreamingResponse:
    def events() -> Iterator[str]:
        try:
            turn = _prepare_turn(payload)
            yield _sse({"type": "start", "conversation_id": turn.thread_id})
            agent = AndoTouristAgent(user_id=payload.user_id)
            for event in agent.stream(
                message=payload.message, thread_id=turn.thread_id, chat_history=turn.history
            ):
                if event["type"] == "done":
                    _persist_turn(turn, payload.message, event)
                    event = {**event, "conversation_id": turn.thread_id}
                yield _sse(event)
        except Exception as exc:
            # El status HTTP (200) ya se envió con el primer evento: el error viaja como evento.
            yield _sse({"type": "error", "detail": _error_response(exc).detail})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/pdfs/{file_id}", summary="Descargar un PDF generado por el agente")
def download_pdf(file_id: uuid.UUID, filename: str = "itinerario.pdf") -> FileResponse:
    path = PDF_DIR / f"{file_id}.pdf"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="PDF no encontrado.")
    return FileResponse(path, media_type="application/pdf", filename=filename)
