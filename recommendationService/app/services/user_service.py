"""
Cuentas de turistas para el selector de sesión de la demo.

El chat no tiene login real: la UI elige un usuario de esta lista (o ninguno) y manda su id. Las
tools personales usan ese id fijado por el servidor, nunca uno elegido por el modelo.
"""

from typing import Any, Dict, List

from sqlalchemy import text

from app.core.database import get_engine

TOURISTS_SQL = """
    SELECT
        u.id,
        u.nombre,
        u.apellido,
        u.ciudad_origen,
        (SELECT COUNT(*) FROM valoraciones v WHERE v."usuarioId" = u.id) AS valoraciones,
        (SELECT COUNT(*) FROM usuarios_itinerarios ui WHERE ui."usuarioId" = u.id) AS itinerarios
    FROM public.usuarios u
    WHERE u.fecha_baja IS NULL
      AND EXISTS (
          SELECT 1 FROM public.usuario_rol ur JOIN public.roles r ON r.id = ur.rol_id
          WHERE ur.usuario_id = u.id AND r.nombre = 'Turista'
      )
    ORDER BY valoraciones DESC, itinerarios DESC, u.nombre
    LIMIT :limit
"""


def list_tourists(limit: int = 10) -> List[Dict[str, Any]]:
    """Turistas activos, primero los que tienen más historial (valoraciones e itinerarios)."""
    with get_engine().connect() as conn:
        rows = conn.execute(text(TOURISTS_SQL), {"limit": limit}).mappings().fetchall()
    return [
        {
            "id": str(r["id"]),
            "nombre": r["nombre"],
            "apellido": r["apellido"],
            "ciudad_origen": r["ciudad_origen"],
            "valoraciones": r["valoraciones"],
            "itinerarios": r["itinerarios"],
        }
        for r in rows
    ]
