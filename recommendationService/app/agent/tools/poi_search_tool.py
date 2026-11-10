"""
LangChain Tool for searching POIs (Puntos de Interés) in Mendoza's Database.
"""
from typing import Optional, List, Dict, Any
from langchain_core.tools import tool
from sqlalchemy import text
from app.core.database import get_engine


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
    - category: Nombre de la categoría (ej. 'Bodegas y Viñedos', 'Gastronomía', 'Naturaleza', 'Alojamiento', 'Turismo Aventura').
    - department: Nombre del departamento de Mendoza (ej. 'Luján de Cuyo', 'Maipú', 'San Rafael', 'Capital', 'Godoy Cruz', 'Tunuyán', 'Malargüe').
    - max_price: Presupuesto máximo estimado en pesos argentinos (ARS).
    - limit: Cantidad máxima de resultados a retornar (por defecto 5).
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
        LEFT JOIN public.zonas z ON p."zonaId" = z.id
        LEFT JOIN public.categorias_poi cp ON p.id = cp."poiId"
        LEFT JOIN public.categorias c ON cp."categoriaId" = c.id
        WHERE 1=1
    """
    params: Dict[str, Any] = {"limit": limit}

    if query:
        sql += " AND (p.nombre ILIKE :query OR p.descripcion ILIKE :query)"
        params["query"] = f"%{query}%"

    if department:
        sql += " AND d.nombre ILIKE :department"
        params["department"] = f"%{department}%"

    if category:
        sql += " AND EXISTS (SELECT 1 FROM public.categorias_poi cp2 JOIN public.categorias c2 ON cp2.\"categoriaId\" = c2.id WHERE cp2.\"poiId\" = p.id AND c2.nombre ILIKE :category)"
        params["category"] = f"%{category}%"

    if max_price is not None and max_price > 0:
        sql += " AND (p.\"precioMin\" IS NULL OR p.\"precioMin\" <= :max_price)"
        params["max_price"] = max_price

    sql += """
        GROUP BY p.id, p.nombre, p.descripcion, p."precioMin", p."precioMax", p."puntuacionPromedio", p."cantidadReviews", p.direccion, d.nombre, z.nombre
        ORDER BY p."puntuacionPromedio" DESC, p."cantidadReviews" DESC
        LIMIT :limit
    """

    results = []
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
        for row in rows:
            results.append({
                "id": str(row.id),
                "nombre": row.nombre,
                "descripcion": (row.descripcion[:200] + "...") if row.descripcion and len(row.descripcion) > 200 else row.descripcion,
                "departamento": row.departamento,
                "zona": row.zona or "General",
                "direccion": row.direccion,
                "categorias": row.categorias,
                "puntuacion": row.puntuacionPromedio,
                "precio_min": row.precioMin,
                "precio_max": row.precioMax,
            })

    return results

