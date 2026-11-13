"""
Pydantic Schemas for the LangChain Agent.
"""
from typing import Any, List, Optional
from pydantic import BaseModel, Field
from app.schemas.assistant import ChatMessageItem


class ToolCallStep(BaseModel):
    tool: str = Field(..., description="Nombre de la herramienta ejecutada")
    input: Any = Field(default=None, description="Parámetros enviados a la herramienta")
    thought: Optional[str] = Field(default=None, description="Razonamiento o log del agente previo a la llamada")
    output: Optional[Any] = Field(default=None, description="Resultado devuelto por la herramienta")


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, description="Mensaje o consulta del turista")
    user_id: Optional[str] = Field(default=None, description="UUID del usuario autenticado si aplica")
    conversation_id: Optional[str] = Field(default=None, description="UUID de la conversación existente para continuar el hilo")
    history: List[ChatMessageItem] = Field(default_factory=list, description="Historial de mensajes previos")


class AgentChatResponse(BaseModel):
    response: str = Field(..., description="Respuesta conversacional generada por el agente")
    model_used: str = Field(default="groq-llama-3.3-70b", description="Nombre del modelo ejecutado")
    conversation_id: Optional[str] = Field(default=None, description="UUID de la conversación en base de datos")
    thought: Optional[str] = Field(default=None, description="Razonamiento interno o pensamiento de la IA")
    steps: List[ToolCallStep] = Field(default_factory=list, description="Herramientas invocadas con sus argumentos y respuestas")


class ConversationItem(BaseModel):
    id: str
    usuario_id: str
    fecha_inicio: str
    titulo: str
    cantidad_mensajes: int
    activa: bool


class ConversationMessageItem(BaseModel):
    id: str
    rol: str
    contenido: str
    fecha_creacion: str
