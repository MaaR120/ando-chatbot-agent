"""
Tests del agente (create_agent + checkpointer) con un modelo falso: sin red ni base de datos.
"""
import unittest
from typing import Any, List
from unittest.mock import patch

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.agent import AndoTouristAgent
from app.agent.middleware import last_user_turns


class FakeToolModel(BaseChatModel):
    """Devuelve las respuestas en orden y guarda los mensajes que recibió en cada llamada."""

    responses: List[AIMessage]
    calls: List[List[BaseMessage]] = []
    model_name: str = "fake-model"

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FakeToolModel":
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.calls.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=self.responses.pop(0))])


@tool
def buscar(query: str) -> dict:
    """Busca lugares."""
    return {"lugares": [query.upper()]}


@tool
def rota(query: str) -> dict:
    """Siempre falla."""
    raise RuntimeError("se cayó la base")


# ChatAnthropic marca sus mensajes así; con eso LangChain normaliza "thinking" a bloques "reasoning".
CLAUDE = {"model_provider": "anthropic"}


def tool_call(name: str, args: dict, call_id: str = "call_1", content: Any = "") -> AIMessage:
    return AIMessage(
        content=content, tool_calls=[{"name": name, "args": args, "id": call_id}], response_metadata=CLAUDE
    )


class AgentTestCase(unittest.TestCase):
    def make_agent(self, responses: List[AIMessage], checkpointer=None) -> AndoTouristAgent:
        self.model = FakeToolModel(responses=responses, calls=[])
        with patch("app.agent.agent.get_chat_llm", return_value=self.model), patch(
            "app.agent.agent.build_agent_tools", return_value=[buscar, rota]
        ):
            return AndoTouristAgent(checkpointer=checkpointer or InMemorySaver())


class TestAgentRun(AgentTestCase):
    def test_steps_in_order_with_args_reasoning_and_parsed_output(self):
        thinking = [
            {"type": "thinking", "thinking": "Necesito buscar bodegas.", "signature": "sig"},
            {"type": "text", "text": "Busco."},
        ]
        agent = self.make_agent([
            tool_call("buscar", {"query": "bodega"}, content=thinking),
            AIMessage(content="Encontré **BODEGA**."),
        ])

        result = agent.run("bodegas en Maipú", thread_id="t1")

        self.assertEqual(result["output"], "Encontré **BODEGA**.")
        self.assertEqual(result["model_used"], "fake-model")
        self.assertEqual(
            result["steps"],
            [{
                "tool": "buscar",
                "input": {"query": "bodega"},
                "thought": "Necesito buscar bodegas.\n\nBusco.",
                "output": {"lugares": ["BODEGA"]},
            }],
        )
        self.assertEqual(result["thought"], "Necesito buscar bodegas.\n\nBusco.")

    def test_final_thinking_is_separated_from_the_answer(self):
        final = AIMessage(content=[
            {"type": "thinking", "thinking": "Respondo directo.", "signature": "s"},
            {"type": "text", "text": "Hola"},
        ], response_metadata=CLAUDE)
        result = self.make_agent([final]).run("hola", thread_id="t1")

        self.assertEqual(result["output"], "Hola")
        self.assertEqual(result["thought"], "Respondo directo.")
        self.assertEqual(result["steps"], [])

    def test_tool_exception_does_not_break_the_flow(self):
        agent = self.make_agent([
            tool_call("rota", {"query": "x"}),
            AIMessage(content="No pude consultar la base, probá en un rato."),
        ])

        result = agent.run("algo", thread_id="t1")

        self.assertEqual(result["output"], "No pude consultar la base, probá en un rato.")
        self.assertIn("Error: la tool rota falló", result["steps"][0]["output"])
        error_seen_by_model = self.model.calls[1][-1]
        self.assertIsInstance(error_seen_by_model, ToolMessage)
        self.assertEqual(error_seen_by_model.status, "error")


    def test_empty_tool_result_reaches_the_model_as_text(self):
        @tool
        def vacia(query: str) -> list:
            """Búsqueda sin resultados."""
            return []

        self.model = FakeToolModel(responses=[tool_call("vacia", {"query": "x"}), AIMessage(content="No hay.")], calls=[])
        with patch("app.agent.agent.get_chat_llm", return_value=self.model), patch(
            "app.agent.agent.build_agent_tools", return_value=[vacia]
        ):
            result = AndoTouristAgent(checkpointer=InMemorySaver()).run("algo", thread_id="t1")

        self.assertEqual(self.model.calls[1][-1].content, "Sin resultados.")
        self.assertEqual(result["steps"][0]["output"], "Sin resultados.")


class TestAgentStream(AgentTestCase):
    def test_events_arrive_in_order_while_the_agent_works(self):
        thinking = [{"type": "thinking", "thinking": "Busco bodegas.", "signature": "s"}]
        agent = self.make_agent([
            tool_call("buscar", {"query": "bodega"}, content=thinking),
            AIMessage(content="Listo.", response_metadata=CLAUDE),
        ])

        events = list(agent.stream("bodegas", thread_id="t1"))
        types = [e["type"] for e in events]

        self.assertEqual(types[0], "reasoning")
        self.assertLess(types.index("tool_call"), types.index("tool_result"))
        self.assertLess(types.index("tool_result"), types.index("token"))
        self.assertEqual(types[-1], "done")

        call = next(e for e in events if e["type"] == "tool_call")
        self.assertEqual((call["tool"], call["input"], call["thought"]), ("buscar", {"query": "bodega"}, "Busco bodegas."))
        result = next(e for e in events if e["type"] == "tool_result")
        self.assertEqual((result["id"], result["output"]), (call["id"], {"lugares": ["BODEGA"]}))
        self.assertEqual(events[-1]["output"], "Listo.")
        self.assertEqual(events[-1]["steps"][0]["tool"], "buscar")

    def test_stream_also_uses_the_checkpointer(self):
        saver = InMemorySaver()
        list(self.make_agent([AIMessage(content="Maipú.")], saver).stream("plan", thread_id="t1"))

        agent = self.make_agent([AIMessage(content="ok")], saver)
        done = list(agent.stream("pasalo a PDF", thread_id="t1"))[-1]

        self.assertIn("Maipú.", [m.text for m in self.model.calls[0]])
        self.assertEqual(done["output"], "ok")


class TestAgentMemory(AgentTestCase):
    def test_second_turn_sees_first_turn_through_the_checkpointer(self):
        saver = InMemorySaver()
        self.make_agent([AIMessage(content="Te propongo Maipú.")], saver).run("armame un plan", thread_id="t1")

        agent = self.make_agent([AIMessage(content="Listo, en PDF.")], saver)
        result = agent.run("pasalo a PDF", thread_id="t1")

        seen = [m.text for m in self.model.calls[0]]
        self.assertIn("armame un plan", seen)
        self.assertIn("Te propongo Maipú.", seen)
        self.assertEqual(result["output"], "Listo, en PDF.")
        self.assertEqual(result["steps"], [])

    def test_threads_are_isolated(self):
        saver = InMemorySaver()
        self.make_agent([AIMessage(content="ok")], saver).run("secreto del hilo A", thread_id="A")

        agent = self.make_agent([AIMessage(content="ok")], saver)
        agent.run("hola", thread_id="B")

        self.assertNotIn("secreto del hilo A", [m.text for m in self.model.calls[0]])

    def test_db_history_seeds_only_an_unknown_thread(self):
        saver = InMemorySaver()
        history = [{"rol": "usuario", "contenido": "viejo"}, {"rol": "asistente", "contenido": "respuesta vieja"}]

        self.make_agent([AIMessage(content="1")], saver).run("nuevo", thread_id="t1", chat_history=history)
        seen = [m.text for m in self.model.calls[0][1:]]  # [0] es el system prompt
        self.assertEqual(seen, ["viejo", "respuesta vieja", "nuevo"])

        self.make_agent([AIMessage(content="2")], saver).run("otro", thread_id="t1", chat_history=history)
        seen = [m.text for m in self.model.calls[0]]
        self.assertEqual(seen.count("viejo"), 1)


class TestTrimHistory(unittest.TestCase):
    def test_keeps_whole_turns_from_the_nth_last_user_message(self):
        messages = [
            HumanMessage("1"), AIMessage("r1"),
            HumanMessage("2"), tool_call("buscar", {"query": "x"}), ToolMessage("res", tool_call_id="call_1"), AIMessage("r2"),
            HumanMessage("3"),
        ]
        self.assertEqual([m.text for m in last_user_turns(messages, 2)], ["2", "", "res", "r2", "3"])
        self.assertEqual(last_user_turns(messages, 5), messages)


if __name__ == "__main__":
    unittest.main()
