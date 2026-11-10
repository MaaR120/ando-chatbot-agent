"""
LangChain Tool for consulting User Itineraries and Travel Plans.
"""
from typing import Optional, List, Dict, Any
from langchain_core.tools import tool
from sqlalchemy import text
from app.core.database import get_engine


@tool
def get_user_itinerary_tool(
    user_id: str,
    itinerary_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Consulta los itinerarios y viajes guardados por un usuario en Ando.
    Parámetros:
    - user_id: UUID del usuario.
    - itinerary_id: (Opcional) UUID específico del itinerario a detallar.
    """
    engine = get_engine()
    with engine.connect() as conn:
        if itinerary_id:
            query = """
                SELECT 
                    i.id,
                    i.nombre,
                    i.descripcion,
                    i."fechaInicio",
                    i."fechaFin",
                    i."cantidadDias",
                    ei.nombre as estado
                FROM public.itinerarios i
                LEFT JOIN public.estados_itinerario ei ON i."estadoId" = ei.id
                WHERE i.id = :itinerary_id
            """
            itinerary = conn.execute(text(query), {"itinerary_id": itinerary_id}).mappings().first()
            if not itinerary:
                return {"message": "No se encontró el itinerario especificado."}

            # Obtener las paradas del itinerario
            routes_query = """
                SELECT 
                    rd."numeroDia",
                    rd.fecha,
                    p.nombre as poi_nombre,
                    rp.orden,
                    rp."horaEstimadaLlegada"
                FROM public.rutas_diarias rd
                JOIN public.rutas_pois rp ON rd.id = rp."rutaId"
                JOIN public.pois p ON rp."poiId" = p.id
                WHERE rd."itinerarioId" = :itinerary_id
                ORDER BY rd."numeroDia", rp.orden
            """
            stops = conn.execute(text(routes_query), {"itinerary_id": itinerary_id}).mappings().fetchall()

            return {
                "itinerario": dict(itinerary),
                "paradas": [dict(s) for s in stops],
            }

        # Si no se pasó itinerary_id, listar los itinerarios del usuario
        list_query = """
            SELECT 
                i.id,
                i.nombre,
                i."fechaInicio",
                i."fechaFin",
                ei.nombre as estado
            FROM public.itinerarios i
            JOIN public.usuarios_itinerarios ui ON i.id = ui."itinerarioId"
            LEFT JOIN public.estados_itinerario ei ON i."estadoId" = ei.id
            WHERE ui."usuarioId" = :user_id
            ORDER BY i."fechaCreacion" DESC
            LIMIT 5
        """
        itineraries = conn.execute(text(list_query), {"user_id": user_id}).mappings().fetchall()
        return {
            "itinerarios": [dict(row) for row in itineraries]
        }

