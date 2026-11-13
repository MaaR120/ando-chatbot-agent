"""
Ando Tourist Agent powered by LangChain and Tool Calling.
"""

from typing import Any, Dict, List, Optional

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.agent.memory import convert_chat_history_to_messages
from app.agent.prompts import ANDO_AGENT_SYSTEM_PROMPT, session_context
from app.agent.tools import build_agent_tools
from app.core.llm_factory import get_chat_llm


class AndoTouristAgent:
    """
    Agente conversacional turístico de Mendoza.
    Orquesta llamadas a herramientas (búsqueda de POIs, recomendaciones, itinerarios, opiniones)
    y razona para responder al usuario.
    """

    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id
        self.tools = build_agent_tools(user_id)
        self.llm = get_chat_llm(temperature=0.2)

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", ANDO_AGENT_SYSTEM_PROMPT),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )

        agent = create_tool_calling_agent(self.llm, self.tools, prompt)
        self.executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=5,
            return_intermediate_steps=True,
        )

    def run(
        self,
        message: str,
        chat_history: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """
        Ejecuta el ciclo de razonamiento y herramientas del agente para responder la consulta del turista.
        """
        history_messages = convert_chat_history_to_messages(chat_history or [])

        result = self.executor.invoke(
            {
                "input": message,
                "chat_history": history_messages,
                "sesion": session_context(self.user_id),
            }
        )

        raw_output = result.get("output", "")
        raw_steps = result.get("intermediate_steps", [])

        # Extraer bloques de pensamiento nativo (ej. Claude thinking blocks)
        thoughts = []
        if isinstance(raw_output, list):
            for block in raw_output:
                if isinstance(block, dict) and block.get("type") == "thinking":
                    thoughts.append(block.get("thinking", ""))

        steps_data = []
        for action, observation in raw_steps:
            tool_name = getattr(action, "tool", "")
            tool_input = getattr(action, "tool_input", {})
            log = getattr(action, "log", "")
            steps_data.append(
                {
                    "tool": tool_name,
                    "input": tool_input,
                    "thought": log.strip() if log else None,
                    "output": observation,
                }
            )

        thought_summary = "\n\n".join(thoughts) if thoughts else None
        if not thought_summary and steps_data:
            action_thoughts = [s["thought"] for s in steps_data if s["thought"]]
            if action_thoughts:
                thought_summary = "\n".join(action_thoughts)

        # Claude devuelve bloques (thinking + text); .text() une solo los de texto y deja igual un str.
        return {
            "output": AIMessage(content=raw_output).text(),
            "model_used": getattr(self.llm, "model_name", None) or getattr(self.llm, "model", "desconocido"),
            "thought": thought_summary,
            "steps": steps_data,
        }
