"""
Validación de identificadores que el LLM pasa a las tools.
"""

import uuid


def is_uuid(value: str) -> bool:
    """Un id inválido llega a Postgres como DataError; las tools lo rechazan antes con un mensaje."""
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False
