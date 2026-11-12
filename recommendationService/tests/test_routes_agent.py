"""
Tests for the agent endpoint error handling.
"""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class TestAgentRouteErrors(unittest.TestCase):
    @patch("app.api.routes_agent.AndoTouristAgent", side_effect=RuntimeError('relation "pois" SELECT secret'))
    def test_internal_error_is_logged_and_not_leaked(self, _agent):
        with self.assertLogs("app.api.routes_agent", level="ERROR") as logs:
            response = TestClient(app).post("/agent/chat", json={"message": "hola"})

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("SELECT", response.text)
        self.assertIn("SELECT secret", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
