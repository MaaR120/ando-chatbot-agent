"""
Pydantic Schemas for the LangChain Agent.
"""
from typing import List, Optional, Any
from pydantic import BaseModel, Field
from app.schemas.assistant import ChatMessageItem


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, description="Mensaje o consulta del turista")
    user_id: Optional[str] = Field(default=None, description="UUID del usuario autenticado si aplica")
    history: List[ChatMessageItem] = Field(default_factory=list, description="Historial de mensajes previos")


class AgentChatResponse(BaseModel):
    response: str = Field(..., description="Respuesta conversacional generada por el agente")
    model_used: str = Field(default="groq-llama-3.3-70b", description="Nombre del modelo ejecutado")

