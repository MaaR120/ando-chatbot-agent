"""
Pydantic Schemas for Route Optimization (US-MRIA-05).
Ando Recommendation & Routing Service (MRIA).
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class HorarioOptimizationItem(BaseModel):
    dia_semana_desde: int = Field(..., ge=0, le=6, description="0 = Domingo, 1 = Lunes, ..., 6 = Sábado")
    hora_desde: str = Field(..., description="Hora de apertura en formato HH:mm o HH:mm:ss")
    dia_semana_hasta: int = Field(..., ge=0, le=6, description="0 = Domingo, 1 = Lunes, ..., 6 = Sábado")
    hora_hasta: str = Field(..., description="Hora de cierre en formato HH:mm o HH:mm:ss")


class PoiOptimizationItem(BaseModel):
    poi_id: str = Field(..., description="ID único del POI (UUID)")
    nombre: str = Field(..., description="Nombre descriptivo del POI")
    latitud: float = Field(..., ge=-90.0, le=90.0, description="Latitud geográfica")
    longitud: float = Field(..., ge=-180.0, le=180.0, description="Longitud geográfica")
    duracion_estimada: int = Field(default=60, ge=1, le=1440, description="Duración estimada de la visita en minutos")
    horarios: Optional[List[HorarioOptimizationItem]] = Field(default_factory=list, description="Franjas horarias de atención comercial")


class RouteOptimizationRequest(BaseModel):
    pois: List[PoiOptimizationItem] = Field(..., min_length=2, description="Lista de al menos 2 POIs a optimizar")
    fecha: Optional[str] = Field(default=None, description="Fecha de la jornada en formato YYYY-MM-DD")
    hora_inicio_offset: Optional[int] = Field(default=540, ge=0, le=1439, description="Hora de inicio de la jornada en minutos desde medianoche (540 = 09:00)")
    modo_viaje: Optional[str] = Field(default="auto", description="Modo de viaje: auto, moto, bicicleta, pie, micro")


class OptimizationConflictItem(BaseModel):
    poi_id: str = Field(..., description="ID del POI que presenta conflicto de horario")
    nombre: str = Field(..., description="Nombre del POI con conflicto")
    hora_llegada: str = Field(..., description="Hora estimada de llegada calculada (HH:mm)")
    hora_cierre: Optional[str] = Field(default=None, description="Hora de cierre del POI (HH:mm)")
    mensaje: str = Field(..., description="Descripción del conflicto")
    alternativa_horario: Optional[str] = Field(default=None, description="Propuesta de ajuste o alternativa de horario")


class StopOptimizationItem(BaseModel):
    poi_id: str = Field(..., description="ID del POI")
    nombre: str = Field(..., description="Nombre del POI")
    orden_secuencia: int = Field(..., ge=1, description="Orden secuencial optimizado (1-indexed)")
    offset_hora_inicio: int = Field(..., ge=0, description="Minutos desde medianoche para el inicio de la visita")
    hora_estimada_llegada: str = Field(..., description="Hora estimada de llegada / inicio de visita en formato HH:mm")
    duracion_estimada: int = Field(..., ge=1, description="Duración de la visita en minutos")
    tiempo_traslado_siguiente: Optional[int] = Field(default=None, description="Minutos de traslado hacia la siguiente parada")
    distancia_traslado_metros: Optional[int] = Field(default=None, description="Distancia en metros hacia la siguiente parada")
    fuera_de_horario: bool = Field(default=False, description="Indica si la visita ocurre fuera del horario de atención")
    aviso_horario: Optional[str] = Field(default=None, description="Mensaje de advertencia de horario si aplica")
    hora_cierre: Optional[str] = Field(default=None, description="Hora de cierre del POI si aplica")


class RouteOptimizationResponse(BaseModel):
    status: str = Field(..., description="'ok', 'conflicto_horario', o 'error'")
    orden_optimizado: List[str] = Field(..., description="Lista ordenada de poi_id en la secuencia óptima")
    paradas: List[StopOptimizationItem] = Field(..., description="Detalle secuencial de paradas con horarios y traslados")
    distancia_total_metros: int = Field(default=0, description="Distancia total estimada de traslados en metros")
    tiempo_total_minutos: int = Field(default=0, description="Tiempo total de la jornada (visitas + traslados) en minutos")
    conflictos: List[OptimizationConflictItem] = Field(default_factory=list, description="Lista de conflictos de horario detectados")
    used_fallback: bool = Field(default=False, description="Indica si se utilizó resolución alternativa / aproximada")
    message: str = Field(default="", description="Mensaje de resumen de la optimización")
