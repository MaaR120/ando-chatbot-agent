"""
Pydantic Schemas for AI Assistant Chat (US-ACIA-01 / US-ACIA-02).
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ChatMessageItem(BaseModel):
    rol: str = Field(..., description="Rol del emisor: 'usuario', 'asistente' o 'sistema'")
    contenido: str = Field(..., description="Texto del mensaje")


class AssistantChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500, description="Mensaje del usuario")
    user_id: Optional[str] = Field(default=None, description="Identificador del usuario")
    history: List[ChatMessageItem] = Field(default_factory=list, description="Historial reciente de la conversación")
    poi_context: Optional[str] = Field(default=None, description="Micro-contexto compacto con POIs reales de la BD")
    itinerary_context: Optional[str] = Field(default=None, description="Micro-contexto con datos del itinerario consultado (US-ACIA-04)")
    user_preferences: List[str] = Field(default_factory=list, description="Categorías de preferencia del usuario")
    language: Optional[str] = Field(default="es", description="Código de idioma de respuesta ('es', 'en', 'pt')")


    role: Optional[str] = Field(default=None, description="Rol autenticado del usuario")
    support_documentation: Optional[str] = Field(default=None, description="Documentación interna vigente para consultas de uso de la plataforma")
    conversation_summary: Optional[str] = Field(default=None, description="Resumen compacto de turnos anteriores de la conversación")


class AssistantChatResponse(BaseModel):
    response: str = Field(..., description="Respuesta generada en lenguaje natural con enlaces a POIs")
    tokens_used: int = Field(default=0, description="Tokens consumidos en la generación")
    model_used: str = Field(default="fallback", description="Modelo LLM o estrategia utilizada")


class AssistantExtractRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500, description="Mensaje del usuario a analizar")
    available_categories: List[str] = Field(default_factory=list, description="Lista de nombres de categorías válidas en Mendoza")
    available_departments: List[str] = Field(default_factory=list, description="Lista de departamentos válidos en Mendoza")
    active_task: Optional[str] = Field(default=None, description="Tarea activa actual: 'creacion_itinerario', 'modificacion_itinerario', etc.")
    current_context: Optional[Dict[str, Any]] = Field(default=None, description="Estado o parámetros acumulados de la tarea activa")
    recent_messages: List[ChatMessageItem] = Field(default_factory=list, description="Últimos mensajes breves de la conversación para contexto de seguimiento")


class AssistantExtractResponse(BaseModel):
    is_recommendation: bool = Field(default=False, description="True si el usuario busca recomendaciones de lugares, actividades o servicios")
    intent: Optional[str] = Field(default=None, description="Intención detectada: 'recommendation', 'itinerary_create', 'itinerary_query', 'itinerary_modify', 'task_continue', 'task_cancel', 'task_subquery', 'general_chat'")
    search_keyword: Optional[str] = Field(default=None, description="Término o tema nuclear de búsqueda de lugares/actividades (ej: 'café', 'bodega boutique', 'parrilla', 'cerveza artesanal')")
    search_synonyms: List[str] = Field(default_factory=list, description="Lista de 2 a 5 sinónimos o conceptos turísticos afines al search_keyword")
    categories: List[str] = Field(default_factory=list, description="Categorías de interés detectadas")
    max_price: Optional[float] = Field(default=None, description="Precio máximo o presupuesto estimado en ARS")
    preferencia_economica: bool = Field(default=False, description="True si el usuario expresó preferencia cualitativa por opciones económicas o accesibles")
    department: Optional[str] = Field(default=None, description="Departamento geográfico detectado")
    zone: Optional[str] = Field(default=None, description="Zona o localidad específica detectada")
    duration_minutes: Optional[int] = Field(default=None, description="Duración estimada de la actividad en minutos")
    start_date: Optional[str] = Field(default=None, description="Fecha de inicio detectada en formato YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="Fecha de fin detectada en formato YYYY-MM-DD")
    people_count: Optional[int] = Field(default=None, description="Cantidad de personas detectada")
    itinerary_target: Optional[str] = Field(default=None, description="Nombre o número de itinerario referenciado")
    itinerary_name: Optional[str] = Field(default=None, description="Nombre o título deseado para el itinerario/viaje si el usuario lo menciona")
    travel_type: Optional[str] = Field(default=None, description="Tipo de viaje: 'Solitario', 'Pareja', 'Familia', 'Amigos'")
    travel_mode: Optional[str] = Field(default=None, description="Modo de viaje: 'auto', 'pie', 'bicicleta', 'moto', 'micro'")
    tokens_used: int = Field(default=0, description="Tokens consumidos en la extracción")
    model_used: str = Field(default="fallback", description="Modelo utilizado para la extracción")


# Categorías temáticas del reporte de uso del asistente (US-RYI-04)
QUERY_TOPIC_CATEGORIES: List[str] = [
    "información turística",
    "ayuda con itinerario",
    "recomendaciones",
    "soporte de plataforma",
    "otros",
]


class AssistantClassifyRequest(BaseModel):
    queries: List[str] = Field(
        default_factory=list,
        max_length=200,
        description="Primeros caracteres de cada mensaje de usuario a clasificar (se truncan a 50)",
    )


class AssistantClassifyResponse(BaseModel):
    categories: List[str] = Field(default_factory=list, description="Categoría temática de cada consulta, en el mismo orden")
    tokens_used: int = Field(default=0, description="Tokens consumidos en la clasificación")
    model_used: str = Field(default="fallback", description="Modelo LLM o estrategia utilizada")
