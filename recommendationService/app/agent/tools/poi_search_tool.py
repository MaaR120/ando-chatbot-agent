"""
LangChain Tool for searching POIs (Puntos de Interés) in Mendoza's Database.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.tools import tool
from sqlalchemy import text

from app.core.config import settings
from app.core.database import get_engine

MAX_LIMIT = settings.agent_max_limit

DIAS = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"]

HORARIOS_SQL = """
    SELECT "poiId", "diaSemanaDesde", "diaSemanaHasta", "horaDesde", "horaHasta"
    FROM public.horarios
    WHERE "poiId" = ANY(CAST(:ids AS uuid[]))
    ORDER BY "diaSemanaDesde", "horaDesde"
"""


def truncate(text_: Optional[str]) -> Optional[str]:
    """Recorta la descripción a AGENT_DESCRIPTION_MAX_CHARS (0 = completa)."""
    max_chars = settings.agent_description_max_chars
    if text_ and max_chars and len(text_) > max_chars:
        return text_[:max_chars].rstrip() + "..."
    return text_


def format_horarios(rows) -> List[str]:
    """Una franja por elemento, por ejemplo 'Lun-Vie 09:00-18:00' (0 = domingo)."""
    out = []
    for r in rows:
        desde, hasta = DIAS[r["diaSemanaDesde"] % 7], DIAS[r["diaSemanaHasta"] % 7]
        dias = desde if desde == hasta else f"{desde}-{hasta}"
        out.append(f"{dias} {str(r['horaDesde'])[:5]}-{str(r['horaHasta'])[:5]}")
    return out


# Genera una condición ILIKE por palabra, con parámetros q0, q1, ..y escapa %,
# _ y \.
def keyword_filter(query: str) -> Tuple[str, Dict[str, str]]:
    """Cada palabra de la consulta debe aparecer en el nombre o en la descripción del POI."""
    words = [re.sub(r"([\\%_])", r"\\\1", w) for w in query.split()]
    sql = "".join(
        f" AND (p.nombre ILIKE :q{i} ESCAPE '\\' OR p.descripcion ILIKE :q{i} ESCAPE '\\')"
        for i in range(len(words))
    )
    return sql, {f"q{i}": f"%{w}%" for i, w in enumerate(words)}


@tool
def search_pois_tool(
    query: Optional[str] = None,
    category: Optional[str] = None,
    department: Optional[str] = None,
    max_price: Optional[float] = None,
    limit: int = settings.agent_default_limit,
) -> List[Dict[str, Any]]:
    """
    Busca atractivos, bodegas, restaurantes, actividades y puntos de interés (POIs) reales en Mendoza.
    Parámetros:
    - query: Término de búsqueda libre o palabra clave (ej. 'vino', 'asado', 'cabalgata', 'mirador').
    - category: Nombre de la categoría (ej. Aventura, Bodega, Gastronomía, Historia, Infantil, Montañismo, Museo, Parques y Plazas, Relax y Vida Nocturna).
    - department: Nombre del departamento de Mendoza (ej. 'Luján de Cuyo', 'Maipú', 'Godoy Cruz').
    - max_price: Presupuesto máximo estimado en pesos argentinos (ARS).
    - limit: Cantidad máxima de resultados a retornar. Usa valores chicos (entre 5 y 10): cada resultado ocupa contexto. Si no lo pasas se usa el valor por defecto del servidor; si pasas más que el máximo del servidor, se recorta.
    """
    engine = get_engine()
    sql = """
        SELECT
            p.id,
            p.nombre,
            p.descripcion,
            p."precioMin",
            p."precioMax",
            p."puntuacionPromedio",
            p."cantidadReviews",
            p."duracionEstimada",
            d.nombre AS departamento,
            z.nombre AS zona,
            COALESCE(string_agg(DISTINCT c.nombre, ', '), '') AS categorias
        FROM public.pois p
        JOIN public.departamentos d ON p."departamentoId" = d.id
        JOIN public.estados_poi ep ON ep.id = p."estadoId"
        LEFT JOIN public.zonas z ON p."zonaId" = z.id
        LEFT JOIN public.categorias_poi cp ON p.id = cp."poiId"
        LEFT JOIN public.categorias c ON cp."categoriaId" = c.id
        WHERE 1=1
            AND ep.nombre = 'aprobado'
    """
    params: Dict[str, Any] = {"limit": max(1, min(limit, MAX_LIMIT))}

    if query:
        keyword_sql, keyword_params = keyword_filter(query)
        sql += keyword_sql
        params.update(keyword_params)

    if department:
        sql += " AND d.nombre ILIKE :department"
        params["department"] = f"%{department}%"

    if category:
        sql += ' AND EXISTS (SELECT 1 FROM public.categorias_poi cp2 JOIN public.categorias c2 ON cp2."categoriaId" = c2.id WHERE cp2."poiId" = p.id AND c2.nombre ILIKE :category)'
        params["category"] = f"%{category}%"

    if max_price is not None and max_price > 0:
        sql += ' AND (p."precioMin" IS NULL OR p."precioMin" <= :max_price)'
        params["max_price"] = max_price

    sql += """
        GROUP BY p.id, p.nombre, p.descripcion, p."precioMin", p."precioMax", p."puntuacionPromedio", p."cantidadReviews", p."duracionEstimada", d.nombre, z.nombre
        ORDER BY p."puntuacionPromedio" DESC NULLS LAST, p."cantidadReviews" DESC NULLS LAST
        LIMIT :limit
    """

    results = []
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
        horarios: Dict[str, List[Any]] = {}
        if rows:
            ids = [str(r.id) for r in rows]
            for h in conn.execute(text(HORARIOS_SQL), {"ids": ids}).mappings():
                horarios.setdefault(str(h["poiId"]), []).append(h)
        for row in rows:
            results.append(
                {
                    "id": str(row.id),
                    "nombre": row.nombre,
                    "descripcion": truncate(row.descripcion),
                    "departamento": row.departamento,
                    "zona": row.zona or "General",
                    "categorias": row.categorias,
                    "puntuacion": row.puntuacionPromedio,
                    "precio_min": row.precioMin,
                    "precio_max": row.precioMax,
                    "duracion_estimada_min": row.duracionEstimada,
                    "horarios": format_horarios(horarios.get(str(row.id), [])),
                }
            )

    return results
