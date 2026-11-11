"""
Configuration module for Recommendation Service.
US-MRIA-04: History-based POI Recommendation.
"""

import os
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Cargar .env de B-Ando (raíz backend) y local de recommendationService
_bando_env = Path(__file__).resolve().parents[3] / ".env"
_rec_env = Path(__file__).resolve().parents[2] / ".env"
_app_env = Path(__file__).resolve().parents[1] / ".env"

for env_path in [_bando_env, _rec_env, _app_env]:
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
load_dotenv(override=False)


class HistoryWeightsConfig(BaseModel):
    positive_rating: float = Field(
        default=0.30,
        ge=0.0,
        le=1.0,
        description="Peso de valoraciones positivas (>=4 estrellas)",
    )
    category_frequency: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Peso de frecuencia de categorías en itinerarios finalizados",
    )
    favorite_affinity: float = Field(
        default=0.20, ge=0.0, le=1.0, description="Peso de afinidad por POIs favoritos"
    )
    recency: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="Peso de recencia temporal con decaimiento",
    )
    price_compatibility: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description="Peso de compatibilidad de precio con POIs valorados positivamente",
    )

    def to_dict(self) -> Dict[str, float]:
        return {
            "positive_rating": self.positive_rating,
            "category_frequency": self.category_frequency,
            "favorite_affinity": self.favorite_affinity,
            "recency": self.recency,
            "price_compatibility": self.price_compatibility,
        }


class Settings(BaseModel):
    app_name: str = "Ando Recommendation Service"
    port: int = int(os.getenv("PORT", "8000"))
    environment: str = os.getenv("NODE_ENV", os.getenv("ENVIRONMENT", "development"))
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://postgres:password123@localhost:5432/ando_db"
    )

    # Parámetros de precondición US-MRIA-04
    min_ratings_for_history: int = int(os.getenv("MIN_RATINGS_FOR_HISTORY", "5"))
    min_finished_itineraries_for_history: int = int(
        os.getenv("MIN_FINISHED_ITINERARIES_FOR_HISTORY", "1")
    )

    # Parámetros de recencia y decaimiento
    half_life_days: float = float(os.getenv("RECENCY_HALF_LIFE_DAYS", "180.0"))

    # Pesos centralizados de scoring
    history_weights: HistoryWeightsConfig = Field(default_factory=HistoryWeightsConfig)

    # Configuración de LLM e Inteligencia Artificial (US-MRIA-10 / US-ACIA-01 / US-ACIA-02)
    llm_provider: str = os.getenv(
        "LLM_PROVIDER",
        "groq" if os.getenv("GROQ_API_KEY") or os.getenv("GROQ-API-KEY") else "gemini",
    )
    llm_model: str = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
    # Base de la API compatible con OpenAI de Groq (configurable para pruebas o proxies)
    groq_api_base: str = os.getenv(
        "GROQ_API_BASE", "https://api.groq.com/openai/v1"
    ).rstrip("/")
    groq_chat_model: str = os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-120b")
    groq_extract_model: str = os.getenv("GROQ_EXTRACT_MODEL", "openai/gpt-oss-20b")
    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY", None)
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY", None)
    groq_api_key: Optional[str] = os.getenv(
        "GROQ_API_KEY", os.getenv("GROQ-API-KEY", None)
    )
    anthropic_api_key: Optional[str] = os.getenv("ANTHROPIC_API_KEY", None)
    moderation_confidence_threshold: float = float(
        os.getenv("MODERATION_CONFIDENCE_THRESHOLD", "0.70")
    )

    def get_sqlalchemy_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        # El driver instalado es psycopg2 (requirements.txt). Se indica explícitamente porque
        # SQLAlchemy 2.1 toma psycopg 3 por defecto para "postgresql://".
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url


settings = Settings()
