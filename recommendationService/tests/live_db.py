"""
Integration tests run the agent tools against the ando-agent-db container (init.sql seed).
"""
import unittest

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.core.database import get_engine

USER_WITH_HISTORY = "8addc001-3489-4811-b84f-4c7be7bfce02"
ITINERARY_OF_USER = "c52a9ce2-2988-4a5c-ab21-2950c1b18f9e"


def database_available() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


requires_db = unittest.skipUnless(database_available(), "requires the ando-agent-db Postgres container")
