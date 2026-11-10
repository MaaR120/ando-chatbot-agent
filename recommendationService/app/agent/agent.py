"""
Ando Tourist Agent powered by LangChain and Tool Calling.
"""
from typing import List, Dict, Any, Optional
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from app.core.llm_factory import get_chat_llm
from app.agent.tools import ALL_AGENT_TOOLS
from app.agent.prompts import ANDO_AGENT_SYSTEM_PROMPT
from app.agent.memory import convert_chat_history_to_messages


class AndoTouristAgent:
    """
    Agente conversacional turístico de Mendoza.
    Orquesta llamadas a herramientas (búsqueda de POIs, recomendaciones, itinerarios, opiniones)
    y razona para responder al usuario.
    """

    def __init__(self, tools: Optional[List[Any]] = None):
        self.tools = tools or ALL_AGENT_TOOLS
        self.llm = get_chat_llm(temperature=0.2)

        prompt = ChatPromptTemplate.from_messages([
            ("system", ANDO_AGENT_SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        agent = create_tool_calling_agent(self.llm, self.tools, prompt)
        self.executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=5,
        )

    def run(
        self,
        message: str,
        chat_history: Optional[List[Any]] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ejecuta el ciclo de razonamiento y herramientas del agente para responder la consulta del turista.
        """
        history_messages = convert_chat_history_to_messages(chat_history or [])

        # Se puede añadir contexto del usuario al prompt si se dispone de él
        augmented_input = message
        if user_id:
            augmented_input += f"\n[Contexto interno: El ID del usuario actual es {user_id}]"

        result = self.executor.invoke({
            "input": augmented_input,
            "chat_history": history_messages,
        })

        return {
            "output": result.get("output", ""),
            "model_used": getattr(self.llm, "model_name", "groq-llama3"),
        }

