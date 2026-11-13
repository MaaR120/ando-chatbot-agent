"""
Integration tests for Chat History Service with PostgreSQL.
"""
import unittest
import uuid
from tests.live_db import requires_db, USER_WITH_HISTORY
from app.services.chat_history_service import ChatHistoryService


@requires_db
class TestChatHistoryService(unittest.TestCase):
    def setUp(self):
        self.service = ChatHistoryService(user_id=USER_WITH_HISTORY)
        self.created_conv_ids = []

    def tearDown(self):
        for conv_id in self.created_conv_ids:
            try:
                self.service.delete_conversation(conv_id)
            except Exception:
                pass

    def test_create_and_list_conversation(self):
        conv_id = self.service.get_or_create_conversation(title="Prueba de viaje")
        self.created_conv_ids.append(conv_id)

        self.service.add_message(
            conversation_id=conv_id,
            role="usuario",
            content="Hola, ¿qué bodegas hay en Maipú?",
            update_title_if_first=True,
        )
        self.service.add_message(
            conversation_id=conv_id,
            role="asistente",
            content="Te recomiendo Bodega Trapiche y Familia Zuccardi.",
        )

        messages = self.service.get_conversation_messages(conv_id)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["rol"], "usuario")
        self.assertIn("bodegas", messages[0]["contenido"])
        self.assertEqual(messages[1]["rol"], "asistente")

        conversations = self.service.list_conversations(limit=10)
        found = [c for c in conversations if c["id"] == conv_id]
        self.assertTrue(len(found) == 1)
        self.assertEqual(found[0]["cantidad_mensajes"], 2)

    def test_delete_conversation(self):
        conv_id = self.service.get_or_create_conversation(title="Conversación para borrar")
        self.service.add_message(conv_id, "usuario", "Mensaje de prueba")

        deleted = self.service.delete_conversation(conv_id)
        self.assertTrue(deleted)

        messages = self.service.get_conversation_messages(conv_id)
        self.assertEqual(len(messages), 0)


if __name__ == "__main__":
    unittest.main()

