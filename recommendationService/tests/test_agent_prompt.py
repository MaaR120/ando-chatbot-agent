"""
Tests for the agent system prompt template.
"""
import unittest

from langchain_core.prompts import ChatPromptTemplate

from app.agent.prompts import ANDO_AGENT_SYSTEM_PROMPT, session_context


class TestAgentPrompt(unittest.TestCase):
    def render(self, user_id):
        template = ChatPromptTemplate.from_messages([("system", ANDO_AGENT_SYSTEM_PROMPT)])
        return template.format_messages(sesion=session_context(user_id))[0].content

    def test_only_variable_is_the_session(self):
        template = ChatPromptTemplate.from_messages([("system", ANDO_AGENT_SYSTEM_PROMPT)])
        self.assertEqual(set(template.input_variables), {"sesion"})

    def test_no_placeholder_survives_rendering(self):
        self.assertNotIn("{", self.render("8addc001-3489-4811-b84f-4c7be7bfce02"))

    def test_user_id_never_reaches_the_prompt(self):
        user_id = "8addc001-3489-4811-b84f-4c7be7bfce02"
        rendered = self.render(user_id)
        self.assertNotIn(user_id, rendered)
        self.assertIn("El usuario inició sesión.", rendered)

    def test_anonymous_session(self):
        self.assertIn("El usuario no inició sesión.", self.render(None))


if __name__ == "__main__":
    unittest.main()
