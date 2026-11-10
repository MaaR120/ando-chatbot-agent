"""
Pydantic schemas for US-MRIA-04 History Recommendation.
"""
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class HistoryRecommendationRequest(BaseModel):
    user_id: str = Field(..., description="UUID del usuario turista")
    limit: int = Field(default=10, ge=1, le=50, description="Cantidad máxima de recomendaciones")
    include_visited: bool = Field(default=False, description="Indica si se deben incluir POIs ya visitados en itinerarios finalizados")
    custom_weights: Optional[Dict[str, float]] = Field(default=None, description="Pesos personalizados opcionales para testing/configurabilidad")


class ExplanationSubscores(BaseModel):
    positive_rating_score: float = Field(..., description="Puntaje de afinidad por valoraciones positivas (>=4 estrellas) [0, 1]")
    category_frequency_score: float = Field(..., description="Puntaje por frecuencia de categorías en itinerarios [0, 1]")
    favorite_affinity_score: float = Field(..., description="Puntaje por POIs favoritos del usuario [0, 1]")
    recency_score: float = Field(..., description="Puntaje de recencia temporal con decaimiento [0, 1]")
    price_compatibility_score: Optional[float] = Field(default=None, description="Puntaje de compatibilidad de precio [0, 1] o None si no hay datos")
    final_score: float = Field(..., description="Puntaje final ponderado normalizado [0, 1]")
    active_weights: Dict[str, float] = Field(..., description="Pesos efectivos normalizados utilizados en el cálculo")


class PoiRecommendationItem(BaseModel):
    poi_id: str = Field(..., description="UUID del POI")
    nombre: str = Field(..., description="Nombre del POI")
    score: float = Field(..., description="Score final ponderado [0, 1]")
    reason: str = Field(..., description="Justificación explicable determinística de la recomendación")
    subscores: ExplanationSubscores = Field(..., description="Desglose numérico de todos los componentes del score")
    ya_visitado: bool = Field(default=False, description="Indica si el POI ya fue visitado en algún itinerario finalizado")
    categorias: List[str] = Field(default_factory=list, description="Nombres o IDs de categorías del POI")
    precio_min: Optional[float] = Field(default=None, description="Precio mínimo del POI")
    precio_max: Optional[float] = Field(default=None, description="Precio máximo del POI")


class HistoryMetadata(BaseModel):
    has_sufficient_history: bool = Field(..., description="Indica si el usuario cumple con la precondición (>=1 itinerario finalizado o >=5 valoraciones)")
    finished_itineraries_count: int = Field(default=0, description="Cantidad de itinerarios finalizados del usuario")
    total_ratings_count: int = Field(default=0, description="Cantidad total de valoraciones registradas por el usuario")
    positive_ratings_count: int = Field(default=0, description="Cantidad de valoraciones positivas (>=4 estrellas)")
    favorites_count: int = Field(default=0, description="Cantidad de POIs guardados como favoritos")
    visited_pois_count: int = Field(default=0, description="Cantidad de POIs únicos visitados en itinerarios finalizados")
    used_fallback: bool = Field(default=False, description="Indica si se aplicó fallback por historial insuficiente")
    fallback_strategy: Optional[str] = Field(default=None, description="Estrategia de fallback sugerida ('preferences' / 'popularity')")


class HistoryRecommendationResponse(BaseModel):
    user_id: str = Field(..., description="UUID del usuario consultado")
    has_sufficient_history: bool = Field(..., description="Indica si el usuario cumple la precondición de historial")
    total: int = Field(..., description="Cantidad de recomendaciones retornadas")
    metadata: HistoryMetadata = Field(..., description="Metadatos detallados del historial del usuario")
    recommendations: List[PoiRecommendationItem] = Field(default_factory=list, description="Listado de POIs recomendados ordenados por score")
