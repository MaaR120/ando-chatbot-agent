"""
Tests for the agent endpoints: error handling and the Server-Sent Events stream.
"""
import json
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


USER = "8addc001-3489-4811-b84f-4c7be7bfce02"


def sse_events(body: str):
    return [json.loads(block[len("data: "):]) for block in body.strip().split("\n\n") if block]


class TestAgentRouteErrors(unittest.TestCase):
    @patch("app.api.routes_agent.AndoTouristAgent", side_effect=RuntimeError('relation "pois" SELECT secret'))
    def test_internal_error_is_logged_and_not_leaked(self, _agent):
        with self.assertLogs("app.api.routes_agent", level="ERROR") as logs:
            response = TestClient(app).post("/agent/chat", json={"message": "hola"})

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("SELECT", response.text)
        self.assertIn("SELECT secret", "\n".join(logs.output))


@patch("app.api.routes_agent.ChatHistoryService")
class TestAgentStreamRoute(unittest.TestCase):
    def test_events_are_sent_as_sse_and_the_turn_is_saved(self, history_service):
        history_service.return_value.get_or_create_conversation.return_value = "conv-1"
        history_service.return_value.get_conversation_messages.return_value = []
        agent = MagicMock()
        agent.stream.return_value = iter([
            {"type": "reasoning", "delta": "Pienso"},
            {"type": "tool_call", "id": "c1", "tool": "buscar", "input": {"q": "vino"}, "thought": "Pienso"},
            {"type": "tool_result", "id": "c1", "tool": "buscar", "output": ["Bodega"]},
            {"type": "token", "delta": "Hola"},
            {"type": "done", "output": "Hola", "thought": "Pienso", "steps": [], "model_used": "m"},
        ])

        with patch("app.api.routes_agent.AndoTouristAgent", return_value=agent):
            response = TestClient(app).post("/agent/chat/stream", json={"message": "vino", "user_id": USER})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        events = sse_events(response.text)
        self.assertEqual(
            [e["type"] for e in events],
            ["start", "reasoning", "tool_call", "tool_result", "token", "done"],
        )
        self.assertEqual(events[0]["conversation_id"], "conv-1")
        self.assertEqual(events[-1]["conversation_id"], "conv-1")
        self.assertEqual(agent.stream.call_args.kwargs["thread_id"], "conv-1")
        self.assertEqual(history_service.return_value.add_message.call_count, 2)

    def test_errors_become_an_error_event_without_leaking_details(self, history_service):
        history_service.return_value.get_or_create_conversation.return_value = "conv-1"
        history_service.return_value.get_conversation_messages.return_value = []
        agent = MagicMock()
        agent.stream.side_effect = RuntimeError("SELECT secret")

        with patch("app.api.routes_agent.AndoTouristAgent", return_value=agent), self.assertLogs(
            "app.api.routes_agent", level="ERROR"
        ):
            response = TestClient(app).post("/agent/chat/stream", json={"message": "vino", "user_id": USER})

        events = sse_events(response.text)
        self.assertEqual(events[-1]["type"], "error")
        self.assertNotIn("SELECT", response.text)


class TestAnonymousSession(unittest.TestCase):
    @patch("app.api.routes_agent.ChatHistoryService")
    def test_without_user_the_agent_has_no_personal_tools_and_nothing_is_saved(self, history_service):
        agent = MagicMock()
        agent.stream.return_value = iter([{"type": "done", "output": "ok", "thought": None, "steps": []}])

        with patch("app.api.routes_agent.AndoTouristAgent", return_value=agent) as agent_class:
            response = TestClient(app).post(
                "/agent/chat/stream", json={"message": "hola", "conversation_id": "hilo-anonimo"}
            )

        agent_class.assert_called_once_with(user_id=None)
        history_service.assert_not_called()
        self.assertEqual(agent.stream.call_args.kwargs["thread_id"], "hilo-anonimo")
        self.assertEqual(sse_events(response.text)[-1]["conversation_id"], "hilo-anonimo")


class TestDemoUsers(unittest.TestCase):
    @patch("app.api.routes_agent.list_tourists", return_value=[
        {"id": USER, "nombre": "Martina", "apellido": "Luconi", "ciudad_origen": None, "valoraciones": 8, "itinerarios": 16}
    ])
    def test_lists_tourist_accounts(self, _users):
        response = TestClient(app).get("/agent/users")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["nombre"], "Martina")


if __name__ == "__main__":
    unittest.main()
