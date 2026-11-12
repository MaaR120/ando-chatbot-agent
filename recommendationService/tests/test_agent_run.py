"""
Tests for the agent output normalization across LLM providers.
"""
import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
