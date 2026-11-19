"""
LangChain Tool para ordenar las paradas de un día de viaje.
Envuelve el optimizador de rutas con OR-Tools (determinista, sin LLM).
"""

import uuid
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool
from sqlalchemy import text

from app.agent.tools.ids import is_uuid
from app.core.database import get_engine
from app.schemas.route_optimization import (
    HorarioOptimizationItem,
    PoiOptimizationItem,
    RouteOptimizationRequest,
)
from app.services.route_optimization_service import RouteOptimizationService

MAX_POIS = 12
DEFAULT_DURATION_MINUTES = 60
TRAVEL_MODES = {"auto", "moto", "bicicleta", "pie", "micro"}

POIS_SQL = """
    SELECT p.id, p.nombre, p.latitud, p.longitud, p."duracionEstimada"
    FROM public.pois p
    JOIN public.estados_poi ep ON ep.id = p."estadoId"
    WHERE p.id = ANY(CAST(:ids AS uuid[])) AND ep.nombre = 'aprobado'
"""

HORARIOS_SQL = """
    SELECT "poiId", "horaDesde", "horaHasta", "diaSemanaDesde", "diaSemanaHasta"
    FROM public.horarios
    WHERE "poiId" = ANY(CAST(:ids AS uuid[]))
"""


def _load_pois(poi_ids: List[str]) -> List[PoiOptimizationItem]:
    """Lee de la BD coordenadas, duración y horarios; los POIs sin coordenadas se omiten."""
    with get_engine().connect() as conn:
        rows = conn.execute(text(POIS_SQL), {"ids": poi_ids}).mappings().fetchall()
        horarios_rows = conn.execute(text(HORARIOS_SQL), {"ids": poi_ids}).mappings().fetchall()

    horarios: Dict[str, List[HorarioOptimizationItem]] = {}
    for h in horarios_rows:
        horarios.setdefault(str(h["poiId"]), []).append(
            HorarioOptimizationItem(
                dia_semana_desde=h["diaSemanaDesde"],
                hora_desde=str(h["horaDesde"]),
                dia_semana_hasta=h["diaSemanaHasta"],
                hora_hasta=str(h["horaHasta"]),
            )
        )

    by_id = {str(r["id"]): r for r in rows if r["latitud"] is not None and r["longitud"] is not None}
    # Se respeta el orden en que llegaron los ids.
    return [
        PoiOptimizationItem(
            poi_id=pid,
            nombre=by_id[pid]["nombre"],
            latitud=by_id[pid]["latitud"],
            longitud=by_id[pid]["longitud"],
            duracion_estimada=by_id[pid]["duracionEstimada"] or DEFAULT_DURATION_MINUTES,
            horarios=horarios.get(pid, []),
        )
        for pid in poi_ids
        if pid in by_id
    ]


@tool
def optimize_route_tool(
    poi_ids: List[str],
    fecha: Optional[str] = None,
    hora_inicio: str = "09:00",
    modo_viaje: str = "auto",
) -> Dict[str, Any]:
    """
    Ordena los lugares de UN día de viaje (conviene con 3 o más lugares) para minimizar traslados y calcula la hora estimada de llegada a cada uno, avisando si alguno queda fuera de su horario de atención.
    Parámetros:
    - poi_ids: Ids (UUID) de 2 a 12 lugares que devolvió search_pois_tool u otra tool.
    - fecha: (Opcional) Fecha del día en formato YYYY-MM-DD; permite validar los horarios de atención de ese día de la semana.
    - hora_inicio: Hora de inicio del día en formato HH:mm (por defecto 09:00).
    - modo_viaje: auto, moto, bicicleta, pie o micro (por defecto auto).
    """
    ids = list(dict.fromkeys(poi_ids or []))
    if not 2 <= len(ids) <= MAX_POIS:
        return {"error": f"Pasa entre 2 y {MAX_POIS} lugares distintos."}
    if not all(is_uuid(i) for i in ids):
        return {"error": "Todos los poi_ids deben ser UUID de lugares que devolvió una tool."}
    if modo_viaje not in TRAVEL_MODES:
        return {"error": f"modo_viaje debe ser uno de: {', '.join(sorted(TRAVEL_MODES))}."}

    start = RouteOptimizationService.parse_time_to_minutes(hora_inicio)
    if start is None or not 0 <= start < 1440:
        return {"error": "hora_inicio debe tener formato HH:mm."}

    ids = [str(uuid.UUID(i)) for i in ids]
    pois = _load_pois(ids)
    if len(pois) < 2:
        return {"error": "Menos de 2 de esos lugares existen, están aprobados y tienen coordenadas."}

    try:
        result = RouteOptimizationService().optimize_route(
            RouteOptimizationRequest(
                pois=pois, fecha=fecha, hora_inicio_offset=start, modo_viaje=modo_viaje
            )
        )
    except ValueError as e:
        return {"error": str(e)}

    omitidos = len(ids) - len(pois)
    return {
        "estado": result.status,
        "mensaje": result.message,
        "paradas": [
            {
                "orden": s.orden_secuencia,
                "id": s.poi_id,
                "nombre": s.nombre,
                "llegada": s.hora_estimada_llegada,
                "duracion_min": s.duracion_estimada,
                "traslado_siguiente_min": s.tiempo_traslado_siguiente,
                "distancia_siguiente_m": s.distancia_traslado_metros,
                "aviso_horario": s.aviso_horario,
            }
            for s in result.paradas
        ],
        "distancia_total_m": result.distancia_total_metros,
        "tiempo_total_min": result.tiempo_total_minutos,
        **({"lugares_omitidos": omitidos} if omitidos else {}),
    }
