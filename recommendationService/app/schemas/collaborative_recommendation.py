"""
Pydantic schemas for US-MRIA-09 Collaborative Filtering Recommendation.
Ando Recommendation & Routing Service (MRIA).
"""
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class CollaborativeRecommendationRequest(BaseModel):
    user_id: str = Field(..., description="UUID del usuario turista")
    limit: int = Field(default=10, ge=1, le=50, description="Cantidad máxima de recomendaciones")
    k_neighbors: int = Field(default=10, ge=1, le=100, description="Cantidad de usuarios similares más cercanos a considerar (K)")
    include_visited: bool = Field(default=False, description="Indica si se deben incluir POIs ya visitados por el usuario")


class CollaborativeSubscores(BaseModel):
    neighbor_similarity_avg: float = Field(..., description="Similitud promedio con los usuarios afines que interactuaron con el POI [0, 1]")
    interaction_strength: float = Field(..., description="Intensidad de interacciones de los vecinos (ratings altos, favoritos, visitas) [0, 1]")
    final_score: float = Field(..., description="Score final ponderado normalizado [0, 1]")


class CollaborativePoiItem(BaseModel):
    poi_id: str = Field(..., description="UUID del POI")
    nombre: str = Field(..., description="Nombre del POI")
    score: float = Field(..., description="Score de afinidad colaborativa [0, 1]")
    reason: str = Field(..., description="Justificación explicable de por qué otros usuarios similares visitaron este POI")
    subscores: CollaborativeSubscores = Field(..., description="Desglose de cálculo de similitud y fuerza de interacción")
    ya_visitado: bool = Field(default=False, description="Indica si el usuario actual ya visitó este POI")
    categorias: List[str] = Field(default_factory=list, description="Categorías asociadas al POI")
    precio_min: Optional[float] = Field(default=None, description="Precio mínimo")
    precio_max: Optional[float] = Field(default=None, description="Precio máximo")
    similar_users_count: int = Field(default=0, description="Cantidad de usuarios afines que valoraron o visitaron este lugar")


class CollaborativeMetadata(BaseModel):
    has_sufficient_data: bool = Field(..., description="Indica si existen datos globales suficientes para el filtrado colaborativo")
    total_users_analyzed: int = Field(default=0, description="Total de usuarios en la base analizados")
    neighbors_found_count: int = Field(default=0, description="Cantidad de vecinos similares identificados")
    global_ratings_count: int = Field(default=0, description="Cantidad total de valoraciones registradas en el sistema")
    used_fallback: bool = Field(default=False, description="Indica si se sugiere fallback por escasez de datos")
    fallback_strategy: Optional[str] = Field(default=None, description="Estrategia alternativa sugerida ('history' / 'preferences')")


class CollaborativeRecommendationResponse(BaseModel):
    user_id: str = Field(..., description="UUID del usuario consultado")
    has_sufficient_data: bool = Field(..., description="Indica si el modelo contó con datos suficientes")
    total: int = Field(..., description="Cantidad de recomendaciones retornadas")
    metadata: CollaborativeMetadata = Field(..., description="Metadatos del filtrado colaborativo")
    recommendations: List[CollaborativePoiItem] = Field(default_factory=list, description="POIs recomendados ordenados por score")
