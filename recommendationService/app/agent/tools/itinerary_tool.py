"""
LangChain Tool for consulting User Itineraries and Travel Plans.
"""

from typing import Any, Dict, Optional

from langchain_core.tools import tool
from sqlalchemy import text

from app.agent.tools.ids import is_uuid
from app.core.database import get_engine


def build_itinerary_tool(user_id: str):
    @tool
    def get_user_itinerary_tool(
        itinerary_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Consulta los itinerarios y viajes guardados por el usuario actual en Ando.
        Parámetros:
        - itinerary_id: (Opcional) UUID específico del itinerario a detallar.
        """
        if itinerary_id and not is_uuid(itinerary_id):
            return {"error": "itinerary_id no es un UUID válido."}

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
                        ei.nombre as estado
                    FROM public.itinerarios i
                    JOIN public.usuarios_itinerarios ui ON ui."itinerarioId" = i.id
                    LEFT JOIN public.estados_itinerario ei ON i."estadoId" = ei.id
                    WHERE i.id = :itinerary_id
                        AND ui."usuarioId" = :user_id
                        AND i.fecha_baja IS NULL
                """
                itinerary = (
                    conn.execute(
                        text(query), {"itinerary_id": itinerary_id, "user_id": user_id}
                    )
                    .mappings()
                    .first()
                )
                if not itinerary:
                    return {"message": "No se encontró el itinerario especificado."}

                # Obtener las paradas del itinerario
                routes_query = """
                    SELECT
                        rd."diaRelativo",
                        rd."fechaAbsoluta",
                        p.nombre as poi_nombre,
                        rp."ordenSecuencia",
                        rp."horaEstimadaLlegada"
                    FROM public.rutas_diarias rd
                    JOIN public.rutas_pois rp ON rp."rutaId" = rd.id
                    JOIN public.pois p ON rp."poiId" = p.id
                    WHERE rd."itinerarioId" = :itinerary_id
                    ORDER BY rd."diaRelativo", rp."ordenSecuencia"
                """
                stops = (
                    conn.execute(text(routes_query), {"itinerary_id": itinerary_id})
                    .mappings()
                    .fetchall()
                )

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
                    AND i.fecha_baja IS NULL
                ORDER BY ui."fechaInicio" DESC
                LIMIT 5
            """
            itineraries = (
                conn.execute(text(list_query), {"user_id": user_id}).mappings().fetchall()
            )
            return {"itinerarios": [dict(row) for row in itineraries]}

    return get_user_itinerary_tool
