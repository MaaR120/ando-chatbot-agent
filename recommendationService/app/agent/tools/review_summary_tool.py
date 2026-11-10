"""
LangChain Tool for consulting reviews and AI summaries of a POI.
"""
from typing import Optional, Dict, Any
from langchain_core.tools import tool
from sqlalchemy import text
from app.core.database import get_engine
from app.services.review_summary_service import ReviewSummaryService


@tool
def get_poi_reviews_summary_tool(
    poi_name: Optional[str] = None,
    poi_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Obtiene opiniones, comentarios y resumen de reseñas de un atractivo o lugar en Mendoza.
    Parámetros:
    - poi_name: Nombre o parte del nombre del lugar (ej. 'Bodega Catena Zapata', 'Aconcagua').
    - poi_id: UUID del POI si se conoce con precisión.
    """
    engine = get_engine()
    with engine.connect() as conn:
        # Resolver POI ID si solo se pasó el nombre
        target_poi_id = poi_id
        poi_real_name = poi_name

        if not target_poi_id and poi_name:
            row = conn.execute(
                text("SELECT id, nombre FROM public.pois WHERE nombre ILIKE :name LIMIT 1"),
                {"name": f"%{poi_name}%"},
            ).first()
            if row:
                target_poi_id = str(row.id)
                poi_real_name = row.nombre

        if not target_poi_id:
            return {"error": f"No se encontró ningún punto de interés con el nombre '{poi_name}'."}

        # Traer últimas reviews
        reviews_query = """
            SELECT r.comentario, v.puntuacion, r."fechaCreacion"
            FROM public.reviews r
            LEFT JOIN public.valoraciones v ON r.id = v."reviewId"
            WHERE r."poiId" = :poi_id
            ORDER BY r."fechaCreacion" DESC
            LIMIT 5
        """
        rows = conn.execute(text(reviews_query), {"poi_id": target_poi_id}).mappings().fetchall()
        reviews = [dict(r) for r in rows]

        return {
            "poi_id": target_poi_id,
            "poi_nombre": poi_real_name,
            "cantidad_opiniones_analizadas": len(reviews),
            "opiniones_recientes": reviews,
        }

