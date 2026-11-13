"""
LLM Factory for LangChain Agents and Chains.
Initializes the Chat Model of the provider selected by LLM_PROVIDER (groq / openai / anthropic).
"""

from typing import Callable, Dict, Optional

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import settings


def _groq(model: str, temperature: float, streaming: bool) -> BaseChatModel:
    from langchain_groq import ChatGroq

    return ChatGroq(
        model_name=model,
        groq_api_key=settings.groq_api_key,
        temperature=temperature,
        streaming=streaming,
    )


def _openai(model: str, temperature: float, streaming: bool) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model_name=model,
        openai_api_key=settings.openai_api_key,
        temperature=temperature,
        streaming=streaming,
    )


def _anthropic(model: str, temperature: float, streaming: bool) -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    # Sin temperature: los modelos Claude 5.x lo rechazan (400 "temperature is deprecated").
    # max_tokens: con el default (1024) el thinking agota el presupuesto y la respuesta final queda sin texto.
    return ChatAnthropic(
        model=model,
        api_key=settings.anthropic_api_key,
        streaming=streaming,
        max_tokens=16000,
    )


_PROVIDERS: Dict[str, Callable[[str, float, bool], BaseChatModel]] = {
    "groq": _groq,
    "openai": _openai,
    "anthropic": _anthropic,
}


def get_chat_llm(
    temperature: float = 0.2,
    model_name: Optional[str] = None,
    streaming: bool = False,
) -> BaseChatModel:
    """Devuelve el ChatModel del proveedor configurado en LLM_PROVIDER, con el modelo de LLM_MODEL."""
    build = _PROVIDERS.get(settings.llm_provider)
    if build is None:
        raise ValueError(
            f"LLM_PROVIDER '{settings.llm_provider}' no está soportado por el agente. "
            f"Valores válidos: {', '.join(_PROVIDERS)}."
        )
    return build(model_name or settings.llm_model, temperature, streaming)
