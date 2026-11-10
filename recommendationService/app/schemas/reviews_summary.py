"""
Pydantic Schemas for AI Review Summary (US-RYV-06).
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class ReviewItemPayload(BaseModel):
    id: Optional[str] = Field(default=None, description="Identificador de la reseña")
    comentario: Optional[str] = Field(default=None, description="Texto de la reseña del turista")
    puntuacion: float = Field(default=5.0, ge=1.0, le=5.0, description="Calificación en estrellas (1 a 5)")
    fecha_creacion: Optional[str] = Field(default=None, description="Fecha de creación ISO")


class ReviewSummaryRequest(BaseModel):
    poi_id: str = Field(..., description="UUID del POI")
    poi_nombre: str = Field(..., description="Nombre del POI")
    categorias: List[str] = Field(default_factory=list, description="Categorías asociadas al POI")
    reviews: List[ReviewItemPayload] = Field(..., min_length=1, description="Lista de reseñas a sintetizar")


class ReviewSummaryResponse(BaseModel):
    poi_id: str = Field(..., description="UUID del POI")
    resumen: str = Field(..., description="Síntesis concisa en lenguaje natural de las opiniones")
    puntos_positivos: List[str] = Field(default_factory=list, description="Fortalezas y aspectos destacados recurrentes")
    puntos_negativos: List[str] = Field(default_factory=list, description="Observaciones o aspectos a mejorar señalados por turistas")
    temas_recurrentes: List[str] = Field(default_factory=list, description="Temas clave o tópicos más comentados")
    total_resenas: int = Field(..., description="Cantidad total de reseñas analizadas")
    puntuacion_promedio: float = Field(..., description="Promedio de estrellas calculado")
    tokens_used: int = Field(default=0, description="Tokens consumidos por el modelo")
    model_used: str = Field(default="fallback", description="Modelo LLM o motor utilizado")
