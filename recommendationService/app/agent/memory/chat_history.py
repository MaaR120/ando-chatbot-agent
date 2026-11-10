"""
Chat History and Memory helpers for LangChain Agent.
"""
from typing import List, Union
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from app.schemas.assistant import ChatMessageItem


def convert_chat_history_to_messages(
    history: List[Union[ChatMessageItem, dict]],
    max_messages: int = 10,
) -> List[BaseMessage]:
    """
    Convierte el historial de chat provisto en la petición a la lista de BaseMessage
    que entiende LangChain, limitando a los últimos `max_messages` para controlar tokens.
    """
    messages: List[BaseMessage] = []
    recent_history = history[-max_messages:] if len(history) > max_messages else history

    for item in recent_history:
        rol = item.rol if isinstance(item, ChatMessageItem) else item.get("rol", "")
        contenido = item.contenido if isinstance(item, ChatMessageItem) else item.get("contenido", "")

        if rol in ("usuario", "user"):
            messages.append(HumanMessage(content=contenido))
        elif rol in ("asistente", "assistant"):
            messages.append(AIMessage(content=contenido))
        elif rol in ("sistema", "system"):
            messages.append(SystemMessage(content=contenido))

    return messages

