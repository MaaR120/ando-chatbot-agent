"""
Tests for the LLM factory provider selection.
"""
import unittest
from unittest.mock import patch

from langchain_anthropic import ChatAnthropic
from langchain_groq import ChatGroq

from app.core.config import settings
from app.core.llm_factory import get_chat_llm


class TestLlmFactory(unittest.TestCase):
    @patch.multiple(settings, llm_provider="anthropic", llm_model="claude-haiku-5-5", anthropic_api_key="test-key")
    def test_anthropic_builds_claude_without_temperature(self):
        llm = get_chat_llm(temperature=0.7)

        self.assertIsInstance(llm, ChatAnthropic)
        self.assertEqual(llm.model, "claude-haiku-5-5")
        self.assertIsNone(llm.temperature)
        # Con 1024 el thinking agotaba el presupuesto y la respuesta final salía vacía.
        self.assertGreater(llm.max_tokens, 1024)

    @patch.multiple(settings, llm_provider="groq", llm_model="llama-3.3-70b-versatile", groq_api_key="test-key")
    def test_provider_selects_groq_even_with_other_keys(self):
        llm = get_chat_llm(model_name="openai/gpt-oss-120b")

        self.assertIsInstance(llm, ChatGroq)
        self.assertEqual(llm.model_name, "openai/gpt-oss-120b")

    @patch.multiple(settings, llm_provider="gemini")
    def test_unknown_provider_raises(self):
        with self.assertRaisesRegex(ValueError, "gemini"):
            get_chat_llm()


if __name__ == "__main__":
    unittest.main()
