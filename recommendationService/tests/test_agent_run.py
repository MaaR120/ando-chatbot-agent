"""
Tests for the agent output normalization across LLM providers.
"""
import unittest
from unittest.mock import patch

from langchain.agents.output_parsers.tools import ToolAgentAction
from langchain_core.messages import AIMessageChunk

from app.agent.agent import AndoTouristAgent
from app.core.config import settings


@patch.multiple(settings, llm_provider="anthropic", llm_model="claude-haiku-5-5", anthropic_api_key="test-key")
class TestAgentRunOutput(unittest.TestCase):
    def _run_with_output(self, output):
        agent = AndoTouristAgent()
        # AgentExecutor es un modelo pydantic: el método se reemplaza en la clase, no en la instancia.
        with patch.object(type(agent.executor), "invoke", return_value={"output": output}):
            return agent.run("¿Y qué opinan de ese?")

    def test_claude_content_blocks_become_text(self):
        blocks = [
            {"type": "thinking", "thinking": "razonamiento interno", "signature": "x"},
            {"type": "text", "text": "El Parque tiene "},
            {"type": "text", "text": "buenas reseñas."},
        ]

        result = self._run_with_output(blocks)

        self.assertEqual(result["output"], "El Parque tiene buenas reseñas.")
        self.assertEqual(result["model_used"], "claude-haiku-5-5")

    def test_plain_string_output_is_kept(self):
        self.assertEqual(self._run_with_output("Hola")["output"], "Hola")

    def _run_with_step(self, content):
        tool_input = {"poi": "Catena Zapata"}
        action = ToolAgentAction(
            tool="get_poi_reviews_summary_tool",
            tool_input=tool_input,
            log=f"Invoking: `get_poi_reviews_summary_tool` with `{tool_input}`\nresponded: {content}",
            message_log=[AIMessageChunk(content=content)],
            tool_call_id="toolu_1",
        )
        agent = AndoTouristAgent()
        result = {"output": "Listo.", "intermediate_steps": [(action, "reseñas")]}
        with patch.object(type(agent.executor), "invoke", return_value=result):
            return agent.run("¿Qué opinan de Catena Zapata?")

    def test_step_thought_drops_signature_and_tool_use_blocks(self):
        content = [
            {"type": "thinking", "thinking": "", "signature": "CAQShwYKEAgTGAI4"},
            {"type": "tool_use", "id": "toolu_1", "name": "get_poi_reviews_summary_tool", "input": {}},
        ]

        result = self._run_with_step(content)

        self.assertIsNone(result["steps"][0]["thought"])
        self.assertIsNone(result["thought"])

    def test_step_thought_keeps_thinking_and_text(self):
        content = [
            {"type": "thinking", "thinking": "Necesito las reseñas.", "signature": "sig"},
            {"type": "text", "text": "Busco opiniones de Catena Zapata."},
            {"type": "tool_use", "id": "toolu_1", "name": "get_poi_reviews_summary_tool", "input": {}},
        ]

        result = self._run_with_step(content)

        expected = "Necesito las reseñas.\n\nBusco opiniones de Catena Zapata."
        self.assertEqual(result["steps"][0]["thought"], expected)
        self.assertEqual(result["thought"], expected)


if __name__ == "__main__":
    unittest.main()
