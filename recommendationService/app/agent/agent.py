"""
Ando Tourist Agent: create_agent de LangChain + tools + checkpointer de LangGraph.
"""

import json
from typing import Any, Dict, Iterator, List, Optional, Tuple

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from app.agent.memory import convert_chat_history_to_messages
from app.agent.middleware import tool_errors_as_messages, trim_history
from app.agent.prompts import build_system_prompt
from app.agent.tools import build_agent_tools
from app.core.config import settings
from app.core.llm_factory import get_chat_llm

# Memoria de corto plazo: un checkpointer sobre Postgres compartido por todas las instancias. Guarda
# el estado completo de cada conversación (mensajes, tool calls y resultados) bajo su thread_id =
# conversation_id, así un turno puede caer en otra instancia o después de un reinicio sin perderlo.
_CHECKPOINTER: Optional[BaseCheckpointSaver] = None


def default_checkpointer() -> BaseCheckpointSaver:
    global _CHECKPOINTER
    if _CHECKPOINTER is None:
        pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=4,
            open=True,
            kwargs={"autocommit": True, "prepare_threshold": None},
        )
        saver = PostgresSaver(pool)
        saver.setup()
        _CHECKPOINTER = saver
    return _CHECKPOINTER


def _reasoning(message: BaseMessage) -> List[str]:
    """
    Bloques de razonamiento en el formato estándar de LangChain (`content_blocks`), que normaliza
    el thinking de Claude y el reasoning de otros proveedores a {"type": "reasoning"}.
    """
    return [b.get("reasoning", "") for b in message.content_blocks if b.get("type") == "reasoning"]


def _join(parts: List[Optional[str]]) -> Optional[str]:
    return "\n\n".join(filter(None, (p.strip() for p in filter(None, parts)))) or None


def _parse_tool_output(content: Any) -> Any:
    """El ToolNode serializa los dict/list de las tools a JSON; se vuelve a parsear para la UI."""
    if isinstance(content, str):
        try:
            return json.loads(content)
        except ValueError:
            return content
    return content


def _current_turn(messages: List[BaseMessage]) -> List[BaseMessage]:
    """Mensajes desde el último HumanMessage: lo que pasó en este turno."""
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return messages[i + 1:]
    return messages


def _steps(turn: List[BaseMessage]) -> List[Dict[str, Any]]:
    """Cada tool call del turno, en orden, con sus argumentos, el razonamiento previo y el resultado."""
    results = {m.tool_call_id: m for m in turn if isinstance(m, ToolMessage)}
    steps: List[Dict[str, Any]] = []
    for message in turn:
        if not isinstance(message, AIMessage) or not message.tool_calls:
            continue
        thought = _join(_reasoning(message) + [message.text])
        for call in message.tool_calls:
            result = results.get(call["id"])
            steps.append(
                {
                    "tool": call["name"],
                    "input": call["args"],
                    "thought": thought,
                    "output": _parse_tool_output(result.content) if result else None,
                }
            )
    return steps


class AndoTouristAgent:
    """
    Agente conversacional turístico de Mendoza.
    Orquesta llamadas a herramientas (búsqueda de POIs, rutas, itinerarios, opiniones, PDF)
    y razona para responder al usuario.
    """

    def __init__(self, user_id: Optional[str] = None, checkpointer: Optional[BaseCheckpointSaver] = None):
        self.user_id = user_id
        self.tools = build_agent_tools(user_id)
        # streaming=True: el modelo entrega el texto y el razonamiento por fragmentos, que stream()
        # reenvía a la UI. invoke() sigue funcionando igual (junta los fragmentos).
        self.llm = get_chat_llm(temperature=0.2, streaming=True)
        self.checkpointer = checkpointer or default_checkpointer()
        # Las tools dependen de la sesión (las personales llevan el user_id del servidor), por eso
        # el grafo se arma por request; el checkpointer es el mismo para todos.
        self.graph = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=build_system_prompt(user_id),
            middleware=[trim_history, tool_errors_as_messages],
            checkpointer=self.checkpointer,
        )

    def _has_state(self, config: Dict[str, Any]) -> bool:
        return self.checkpointer.get_tuple(config) is not None

    def _prepare(
        self, message: str, thread_id: str, chat_history: Optional[List[Any]]
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Entrada y config de un turno sobre el hilo `thread_id`.

        El checkpointer aporta los turnos anteriores. `chat_history` (texto guardado en la BD) sólo
        se usa para sembrar un hilo que el checkpointer no conoce, por ejemplo al reabrir una
        conversación vieja después de reiniciar el servidor.
        """
        config = {
            "configurable": {"thread_id": thread_id},
            # Cada vuelta modelo → tools son 2 pasos del grafo.
            "recursion_limit": 2 * settings.agent_max_iterations + 1,
        }
        new_messages: List[BaseMessage] = []
        if chat_history and not self._has_state(config):
            new_messages += convert_chat_history_to_messages(chat_history)
        new_messages.append(HumanMessage(content=message))
        return {"messages": new_messages}, config

    def _result(self, messages: List[BaseMessage]) -> Dict[str, Any]:
        """Respuesta final, razonamiento y tools del último turno, a partir del estado del hilo."""
        turn = _current_turn(messages)
        final = turn[-1] if turn and isinstance(turn[-1], AIMessage) else AIMessage(content="")
        steps = _steps(turn)
        return {
            "output": final.text,
            "model_used": getattr(self.llm, "model_name", None) or getattr(self.llm, "model", "desconocido"),
            # Razonamiento de la respuesta final; si no hay, el de cada paso.
            "thought": _join(_reasoning(final)) or _join([s["thought"] for s in steps]),
            "steps": steps,
        }

    def run(
        self,
        message: str,
        thread_id: str,
        chat_history: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """Ejecuta un turno completo y devuelve el resultado al final (sin streaming)."""
        inputs, config = self._prepare(message, thread_id, chat_history)
        result = self.graph.invoke(inputs, config=config)
        return self._result(result["messages"])

    def stream(
        self,
        message: str,
        thread_id: str,
        chat_history: Optional[List[Any]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """
        Ejecuta un turno y va emitiendo eventos mientras el agente trabaja:

        - reasoning:   fragmento del razonamiento del modelo.
        - token:       fragmento del texto de la respuesta.
        - tool_call:   el modelo decidió llamar una tool (nombre, argumentos y razonamiento previo).
        - tool_result: la tool terminó (resultado).
        - done:        resultado final, igual al de run().

        LangGraph combina dos modos: "messages" entrega los fragmentos del modelo a medida que se
        generan, y "updates" avisa cada vez que un nodo (model o tools) termina un paso.
        """
        inputs, config = self._prepare(message, thread_id, chat_history)
        for mode, data in self.graph.stream(inputs, config=config, stream_mode=["messages", "updates"]):
            if mode == "messages":
                chunk, metadata = data
                if metadata.get("langgraph_node") != "model" or not isinstance(chunk, AIMessage):
                    continue
                for block in chunk.content_blocks:
                    if block.get("type") == "reasoning" and block.get("reasoning"):
                        yield {"type": "reasoning", "delta": block["reasoning"]}
                    elif block.get("type") == "text" and block.get("text"):
                        yield {"type": "token", "delta": block["text"]}
                continue

            for node, update in data.items():
                for msg in (update or {}).get("messages", []):
                    if node == "model" and isinstance(msg, AIMessage):
                        thought = _join(_reasoning(msg) + [msg.text])
                        for call in msg.tool_calls:
                            yield {
                                "type": "tool_call",
                                "id": call["id"],
                                "tool": call["name"],
                                "input": call["args"],
                                "thought": thought,
                            }
                    elif node == "tools" and isinstance(msg, ToolMessage):
                        yield {
                            "type": "tool_result",
                            "id": msg.tool_call_id,
                            "tool": msg.name,
                            "output": _parse_tool_output(msg.content),
                        }

        state = self.graph.get_state(config)
        yield {"type": "done", **self._result(state.values["messages"])}
