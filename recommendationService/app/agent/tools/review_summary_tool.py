"""
LangChain Tool for consulting the latest reviews and the rating of a POI.
"""

from typing import Any, Dict, Optional

from langchain_core.tools import tool
from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.agent.tools.ids import is_uuid
from app.core.database import get_engine

POI_QUERY = """
    SELECT p.id, p.nombre, p."puntuacionPromedio", p."cantidadReviews"
    FROM public.pois p
    JOIN public.estados_poi ep ON ep.id = p."estadoId"
    WHERE ep.nombre = 'aprobado' AND {condition}
    ORDER BY (lower(p.nombre) = lower(:poi)) DESC, p."cantidadReviews" DESC NULLS LAST
    LIMIT 1
"""

REVIEWS_QUERY = """
    SELECT r.comentario, v.puntuacion, r."fechaCreacion"
    FROM public.reviews r
    LEFT JOIN public.valoraciones v ON r.id = v."reviewId"
    WHERE r."poiId" = :poi_id
    ORDER BY r."fechaCreacion" DESC
    LIMIT 5
"""


def find_poi(conn: Connection, poi: str) -> Optional[RowMapping]:
    """Busca un POI aprobado por UUID o por nombre; el nombre exacto gana a las coincidencias parciales."""
    condition = "p.id = CAST(:poi AS uuid)" if is_uuid(poi) else "p.nombre ILIKE :name"
    params = {"poi": poi, "name": f"%{poi}%"}
    return conn.execute(text(POI_QUERY.format(condition=condition)), params).mappings().first()


@tool
def get_poi_reviews_summary_tool(poi: str) -> Dict[str, Any]:
    """
    Obtiene las opiniones recientes y la puntuación promedio de un atractivo o lugar en Mendoza.
    Parámetros:
    - poi: UUID del lugar si lo tienes de un resultado anterior; si no, su nombre o parte del nombre (ej. 'Casa Vigil').
    """
    with get_engine().connect() as conn:
        found = find_poi(conn, poi)
        if not found:
            return {"error": f"No se encontró ningún lugar para '{poi}'."}
        reviews = conn.execute(text(REVIEWS_QUERY), {"poi_id": found["id"]}).mappings().fetchall()

    return {
        "poi_id": str(found["id"]),
        "poi_nombre": found["nombre"],
        "puntuacion_promedio": found["puntuacionPromedio"],
        "cantidad_reviews": found["cantidadReviews"],
        "opiniones_recientes": [dict(r) for r in reviews],
    }
