"""
Collaborative Recommendation Service (US-MRIA-09).
Orchestrates data retrieval from PostgreSQL and executes the CollaborativeEngine.
"""
from typing import Optional, Dict, Any, List, Set, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.schemas.collaborative_recommendation import (
    CollaborativeRecommendationRequest,
    CollaborativeRecommendationResponse,
)
from app.services.collaborative_engine import CollaborativeEngine


class CollaborativeRecommendationService:
    def __init__(self, db: Optional[Session] = None, min_global_ratings: int = 5):
        self.db = db
        self.min_global_ratings = min_global_ratings
        self.engine = CollaborativeEngine(min_global_ratings=min_global_ratings)

    def get_collaborative_recommendations(
        self,
        request: CollaborativeRecommendationRequest,
        db: Optional[Session] = None,
    ) -> CollaborativeRecommendationResponse:
        session = db or self.db
        if session is None:
            raise ValueError("Se requiere una sesión de base de datos válida.")

        user_id = request.user_id

        # 1. Obtener listado de todos los IDs de usuario y categorías
        all_user_ids = self._fetch_all_user_ids(session)
        if user_id not in all_user_ids:
            all_user_ids.append(user_id)

        all_category_ids = self._fetch_all_category_ids(session)

        # 2. Obtener POIs aprobados
        approved_pois = self._fetch_approved_pois(session)

        # 3. Obtener preferencias de categorías de todos los usuarios
        user_preferences = self._fetch_all_user_preferences(session)

        # 4. Obtener todas las valoraciones registradas
        user_ratings = self._fetch_all_user_ratings(session)

        # 5. Obtener todos los favoritos registrados
        user_favorites = self._fetch_all_user_favorites(session)

        # 6. Obtener POIs visitados en itinerarios finalizados
        user_visited = self._fetch_all_user_visited_pois(session)

        # 7. Ejecutar el cálculo matemático en el CollaborativeEngine
        return self.engine.calculate_collaborative_recommendations(
            target_user_id=user_id,
            all_user_ids=all_user_ids,
            all_category_ids=all_category_ids,
            approved_pois=approved_pois,
            user_preferences=user_preferences,
            user_ratings=user_ratings,
            user_favorites=user_favorites,
            user_visited_pois=user_visited,
            k_neighbors=request.k_neighbors,
            limit=request.limit,
            include_visited=request.include_visited,
        )

    def _fetch_all_user_ids(self, session: Session) -> List[str]:
        sql = text("SELECT id FROM usuarios WHERE fecha_baja IS NULL")
        rows = session.execute(sql).mappings().all()
        return [str(r["id"]) for r in rows if r.get("id")]

    def _fetch_all_category_ids(self, session: Session) -> List[str]:
        sql = text("SELECT id FROM categorias")
        rows = session.execute(sql).mappings().all()
        return [str(r["id"]) for r in rows if r.get("id")]

    def _fetch_approved_pois(self, session: Session) -> Dict[str, Dict[str, Any]]:
        sql = text("""
            SELECT 
                p.id,
                p.nombre,
                p."precioMin" AS precio_min,
                p."precioMax" AS precio_max,
                p."puntuacionPromedio" AS puntuacion_promedio,
                p."cantidadReviews" AS cantidad_reviews,
                ARRAY_AGG(cp."categoriaId") FILTER (WHERE cp."categoriaId" IS NOT NULL) AS category_ids,
                ARRAY_AGG(c.nombre) FILTER (WHERE c.nombre IS NOT NULL) AS category_names
            FROM pois p
            INNER JOIN estados_poi ep ON ep.id = p."estadoId"
            LEFT JOIN categorias_poi cp ON cp."poiId" = p.id
            LEFT JOIN categorias c ON c.id = cp."categoriaId"
            WHERE (LOWER(ep.nombre) = 'aprobado' OR ep.nombre = 'APROBADO')
            GROUP BY p.id, p.nombre, p."precioMin", p."precioMax", p."puntuacionPromedio", p."cantidadReviews"
        """)
        rows = session.execute(sql).mappings().all()
        result = {}
        for r in rows:
            pid = str(r["id"])
            result[pid] = {
                "id": pid,
                "poi_id": pid,
                "nombre": str(r["nombre"]),
                "precio_min": float(r["precio_min"]) if r["precio_min"] is not None else None,
                "precio_max": float(r["precio_max"]) if r["precio_max"] is not None else None,
                "puntuacion_promedio": float(r["puntuacion_promedio"]) if r["puntuacion_promedio"] is not None else 0.0,
                "cantidad_reviews": int(r["cantidad_reviews"]) if r["cantidad_reviews"] is not None else 0,
                "category_ids": [str(c) for c in (r["category_ids"] or []) if c],
                "categorias": [str(c) for c in (r["category_names"] or []) if c],
            }
        return result

    def _fetch_all_user_preferences(self, session: Session) -> Dict[str, Set[str]]:
        sql = text("SELECT usuario_id, categoria_id FROM usuario_preferencia")
        rows = session.execute(sql).mappings().all()
        prefs: Dict[str, Set[str]] = {}
        for r in rows:
            uid = str(r["usuario_id"])
            cid = str(r["categoria_id"])
            if uid not in prefs:
                prefs[uid] = set()
            prefs[uid].add(cid)
        return prefs

    def _fetch_all_user_ratings(self, session: Session) -> Dict[Tuple[str, str], float]:
        sql = text('SELECT "usuarioId", "poiId", puntuacion FROM valoraciones WHERE puntuacion IS NOT NULL')
        rows = session.execute(sql).mappings().all()
        ratings: Dict[Tuple[str, str], float] = {}
        for r in rows:
            uid = str(r["usuarioId"])
            pid = str(r["poiId"])
            val = float(r["puntuacion"])
            ratings[(uid, pid)] = val
        return ratings

    def _fetch_all_user_favorites(self, session: Session) -> Dict[str, Set[str]]:
        sql = text('SELECT "usuarioId", "poiId" FROM favoritos_poi')
        rows = session.execute(sql).mappings().all()
        favs: Dict[str, Set[str]] = {}
        for r in rows:
            uid = str(r["usuarioId"])
            pid = str(r["poiId"])
            if uid not in favs:
                favs[uid] = set()
            favs[uid].add(pid)
        return favs

    def _fetch_all_user_visited_pois(self, session: Session) -> Dict[str, Set[str]]:
        sql = text("""
            SELECT ui."usuarioId" AS usuario_id, ip."poiId" AS poi_id
            FROM usuarios_itinerarios ui
            INNER JOIN itinerarios i ON i.id = ui."itinerarioId"
            INNER JOIN estados_itinerario ei ON ei.id = i."estadoId"
            INNER JOIN itinerario_poi ip ON ip."itinerarioId" = i.id
            WHERE (LOWER(ei.nombre) = 'finalizado' OR ei.nombre = 'FINALIZADO')
              AND i.fecha_baja IS NULL
        """)
        rows = session.execute(sql).mappings().all()
        visited: Dict[str, Set[str]] = {}
        for r in rows:
            uid = str(r["usuario_id"])
            pid = str(r["poi_id"])
            if uid not in visited:
                visited[uid] = set()
            visited[uid].add(pid)
        return visited
