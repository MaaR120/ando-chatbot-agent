"""
Database connection and session management using SQLAlchemy.
US-MRIA-04: Connects to PostgreSQL to read user history and POI metadata.
"""
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

_engine = None
_SessionFactory = None


def get_engine():
    global _engine
    if _engine is None:
        db_url = settings.get_sqlalchemy_database_url()
        _engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def get_session_factory():
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
        )
    return _SessionFactory


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency to yield a database session."""
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
