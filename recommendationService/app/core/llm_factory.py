"""
LLM Factory for LangChain Agents and Chains.
Initializes Chat Models (Groq / OpenAI) with fallback and standard configuration.
"""
from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel
from app.core.config import settings


def get_chat_llm(
    temperature: float = 0.2,
    model_name: Optional[str] = None,
    streaming: bool = False,
) -> BaseChatModel:
    """
    Factory function to initialize and return a LangChain ChatModel instance.
    Prioritizes Groq (configured with LLaMA 3.3) and falls back to OpenAI if configured.
    """
    groq_api_key = settings.groq_api_key

    if groq_api_key:
        from langchain_groq import ChatGroq

        target_model = model_name or settings.llm_model or "llama-3.3-70b-versatile"
        return ChatGroq(
            model_name=target_model,
            groq_api_key=groq_api_key,
            temperature=temperature,
            streaming=streaming,
        )

    if settings.openai_api_key:
        from langchain_openai import ChatOpenAI

        target_model = model_name or "gpt-4o-mini"
        return ChatOpenAI(
            model_name=target_model,
            openai_api_key=settings.openai_api_key,
            temperature=temperature,
            streaming=streaming,
        )

    raise ValueError(
        "No se encontró una clave de API válida para inicializar el LLM. "
        "Asegúrate de configurar GROQ_API_KEY o OPENAI_API_KEY en tu archivo .env."
    )

