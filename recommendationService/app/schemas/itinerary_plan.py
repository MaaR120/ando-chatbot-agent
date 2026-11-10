"""
Pydantic Schemas para la planificación de itinerarios con LLM (US-GDI-02 / US-GDI-04).
"""
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class PlanCandidatePoi(BaseModel):
    poi_id: str = Field(..., description="ID del POI (UUID)")
    nombre: str = Field(..., description="Nombre del POI")
    categoria: Optional[str] = Field(default=None, description="Rubro principal del POI")
    zona: Optional[str] = Field(default=None, description="Departamento o zona donde se encuentra")
    latitud: float = Field(..., description="Latitud geográfica")
    longitud: float = Field(..., description="Longitud geográfica")
    duracion_minutos: int = Field(default=90, ge=1, le=1440, description="Duración estimada de la visita")
    puntuacion: Optional[float] = Field(default=None, description="Puntuación promedio (0 a 5)")
    precio_min: Optional[float] = Field(default=None, description="Precio mínimo por persona en ARS")
    descripcion: Optional[str] = Field(default=None, max_length=300, description="Descripción breve")
    dias_abierto: Optional[List[int]] = Field(
        default=None,
        description="Números de día del viaje (1 = primer día) en los que el POI está abierto. None = sin restricción.",
    )
    horario: Optional[str] = Field(default=None, description="Franja horaria de atención, ej. '10:00-18:00'")


class PlanDayInfo(BaseModel):
    dia: int = Field(..., ge=1, description="Número de día del viaje (1 = primer día)")
    fecha: str = Field(..., description="Fecha del día en formato YYYY-MM-DD")
    dia_semana: str = Field(..., description="Nombre del día de la semana")


class ItineraryPlanRequest(BaseModel):
    modo: Literal["seleccionar", "organizar"] = Field(
        default="seleccionar",
        description=(
            "'seleccionar': el modelo elige qué lugares incluir según las preferencias (US-GDI-02). "
            "'organizar': el modelo debe ubicar todos los lugares que entren en el viaje (US-GDI-04)."
        ),
    )
    dias: List[PlanDayInfo] = Field(..., min_length=1, max_length=31)
    candidatos: List[PlanCandidatePoi] = Field(..., min_length=1, max_length=120)
    minutos_por_dia: int = Field(default=480, ge=60, le=900, description="Jornada activa por día")
    cantidad_personas: Optional[int] = Field(default=None, ge=1)
    presupuesto_diario: Optional[float] = Field(default=None, gt=0)
    tipo_viaje: Optional[str] = Field(default=None, description="Solitario, Pareja, Familia o Amigos")
    intereses: List[str] = Field(default_factory=list, description="Nombres de las categorías de interés")
    descripcion_libre: Optional[str] = Field(default=None, max_length=500)
    modo_transporte: Optional[str] = Field(default=None)


class PlannedDay(BaseModel):
    dia: int = Field(..., ge=1, description="Número de día del viaje")
    poi_ids: List[str] = Field(default_factory=list, description="POIs asignados a ese día")
    motivo: Optional[str] = Field(default=None, description="Breve explicación del armado del día")


class ItineraryPlanResponse(BaseModel):
    dias: List[PlannedDay] = Field(default_factory=list)
    sobrantes: List[str] = Field(default_factory=list, description="POIs que no se pudieron ubicar (modo organizar)")
    resumen: Optional[str] = Field(default=None, description="Descripción general del viaje propuesto")
    tokens_used: int = Field(default=0)
    model_used: str = Field(default="")
