"""
LangChain Tool for searching POIs (Puntos de Interés) in Mendoza's Database.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.tools import tool
from sqlalchemy import text

from app.core.database import get_engine

MAX_LIMIT = 20


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
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Busca atractivos, bodegas, restaurantes, actividades y puntos de interés (POIs) reales en Mendoza.
    Parámetros:
    - query: Término de búsqueda libre o palabra clave (ej. 'vino', 'asado', 'cabalgata', 'mirador').
    - category: Nombre de la categoría (ej. Aventura, Bodega, Gastronomía, Historia, Infantil, Montañismo, Museo, Parques y Plazas, Relax y Vida Nocturna).
    - department: Nombre del departamento de Mendoza (ej. 'Luján de Cuyo', 'Maipú', 'Godoy Cruz').
    - max_price: Presupuesto máximo estimado en pesos argentinos (ARS).
    - limit: Cantidad máxima de resultados a retornar (por defecto 5, máximo 20).
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
            p.direccion,
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
        GROUP BY p.id, p.nombre, p.descripcion, p."precioMin", p."precioMax", p."puntuacionPromedio", p."cantidadReviews", p.direccion, d.nombre, z.nombre
        ORDER BY p."puntuacionPromedio" DESC NULLS LAST, p."cantidadReviews" DESC NULLS LAST
        LIMIT :limit
    """

    results = []
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
        for row in rows:
            results.append(
                {
                    "id": str(row.id),
                    "nombre": row.nombre,
                    "descripcion": (row.descripcion[:200] + "...")
                    if row.descripcion and len(row.descripcion) > 200
                    else row.descripcion,
                    "departamento": row.departamento,
                    "zona": row.zona or "General",
                    "direccion": row.direccion,
                    "categorias": row.categorias,
                    "puntuacion": row.puntuacionPromedio,
                    "precio_min": row.precioMin,
                    "precio_max": row.precioMax,
                }
            )

    return results
