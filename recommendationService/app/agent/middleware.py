"""
Middleware propio del agente (hooks de create_agent escritos por el grupo).

No se usa middleware prearmado de LangChain: estos dos son unas pocas líneas cada uno y así
controlamos exactamente qué mensaje ve el modelo y qué se recorta.
"""

import logging
from typing import Any, Callable, List

from langchain.agents.middleware import (
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
    wrap_model_call,
    wrap_tool_call,
)
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


@wrap_tool_call
def tool_errors_as_messages(request: ToolCallRequest, handler: Callable[[ToolCallRequest], Any]) -> Any:
    """
    Si una tool lanza una excepción (BD caída, PDF que no se pudo escribir...), el ToolNode de
    LangGraph la re-lanza y corta el turno entero. Acá se convierte en un ToolMessage de error:
    el modelo lo lee y puede reintentar, cambiar de estrategia o avisarle al usuario.

    También cubre el resultado vacío: una tool que devuelve [] (búsqueda sin resultados) llega como
    ToolMessage sin contenido, y proveedores como Groq rechazan la petición con un 400.
    """
    try:
        result = handler(request)
        if isinstance(result, ToolMessage) and not result.content:
            result.content = "Sin resultados."
        return result
    except Exception as exc:
        name = request.tool_call["name"]
        logger.exception("La tool %s falló", name)
        return ToolMessage(
            content=(
                f"Error: la tool {name} falló ({type(exc).__name__}). "
                "No inventes el resultado: probá con otros argumentos o avisale al usuario."
            ),
            tool_call_id=request.tool_call["id"],
            name=name,
            status="error",
        )


def last_user_turns(messages: List[BaseMessage], turns: int) -> List[BaseMessage]:
    """
    Mensajes desde el N-ésimo HumanMessage contando desde el final. Corta siempre al inicio de un
    turno del usuario, así nunca separa una tool call de su ToolMessage.
    """
    human_positions = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    if len(human_positions) <= turns:
        return messages
    return messages[human_positions[-turns]:]


@wrap_model_call
def trim_history(request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]) -> ModelResponse:
    """
    El checkpointer guarda la conversación completa (incluidos los resultados de las tools), que
    crece en cada turno. Al modelo sólo se le mandan los últimos AGENT_HISTORY_TURNS turnos para
    no exceder el contexto ni los tokens por minuto del proveedor. El estado guardado no se toca.
    """
    trimmed = last_user_turns(request.messages, settings.agent_history_turns)
    return handler(request.override(messages=trimmed))
