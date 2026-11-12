"""
History Recommendation Service.
Orchestrates data retrieval from PostgreSQL and executes the HistoryScoringEngine.
"""
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.config import settings
from app.schemas.recommendation_history import (
    HistoryRecommendationRequest,
    HistoryRecommendationResponse,
    PoiRecommendationItem,
    ExplanationSubscores,
    HistoryMetadata,
)
from app.services.history_scoring_engine import HistoryScoringEngine


class HistoryRecommendationService:
    def __init__(self, db: Optional[Session] = None):
        self.db = db

    def get_history_recommendations(
        self,
        request: HistoryRecommendationRequest,
        db: Optional[Session] = None,
    ) -> HistoryRecommendationResponse:
        session = db or self.db
        if session is None:
            raise ValueError("Se requiere una sesión de base de datos válida.")

        user_id = request.user_id
        engine = HistoryScoringEngine(
            weights=request.custom_weights or settings.history_weights.to_dict(),
            half_life_days=settings.half_life_days,
            min_ratings_for_history=settings.min_ratings_for_history,
            min_finished_itineraries_for_history=settings.min_finished_itineraries_for_history,
        )

        # 1. Obtener conteo y datos de valoraciones del usuario
        ratings_data = self._fetch_user_ratings(session, user_id)
        total_ratings_count = ratings_data["total_count"]
        positive_ratings = ratings_data["positive_ratings"]

        # 2. Obtener itinerarios finalizados del usuario
        itineraries_data = self._fetch_user_finished_itineraries(session, user_id)
        finished_itineraries = itineraries_data["itineraries"]
        finished_itineraries_count = len(finished_itineraries)

        # 3. Obtener favoritos del usuario
        favorites_data = self._fetch_user_favorites(session, user_id)
        favorite_pois = favorites_data["favorites"]

        # 4. Verificar Precondición de Historial Suficiente
        has_sufficient_history = engine.check_sufficient_history(
            finished_itineraries_count=finished_itineraries_count,
            total_ratings_count=total_ratings_count,
        )

        visited_poi_ids_count = len({pid for itin in finished_itineraries for pid in itin.get("poi_ids", [])})

        metadata = HistoryMetadata(
            has_sufficient_history=has_sufficient_history,
            finished_itineraries_count=finished_itineraries_count,
            total_ratings_count=total_ratings_count,
            positive_ratings_count=len(positive_ratings),
            favorites_count=len(favorite_pois),
            visited_pois_count=visited_poi_ids_count,
            used_fallback=not has_sufficient_history,
            fallback_strategy="preferences" if not has_sufficient_history else None,
        )

        if not has_sufficient_history:
            return HistoryRecommendationResponse(
                user_id=user_id,
                has_sufficient_history=False,
                total=0,
                metadata=metadata,
                recommendations=[],
            )

        # 5. Obtener mapa de nombres de categorías y POIs candidatos aprobados
        category_name_map = self._fetch_category_names(session)
        candidate_pois = self._fetch_approved_candidate_pois(session)

        # 6. Construir perfil y calcular scoring
        user_profile = engine.build_user_history_profile(
            positive_ratings=positive_ratings,
            finished_itineraries=finished_itineraries,
            favorite_pois=favorite_pois,
        )

        ranked_results = engine.rank_candidates(
            candidate_pois=candidate_pois,
            user_profile=user_profile,
            limit=request.limit,
            include_visited=request.include_visited,
            category_name_map=category_name_map,
        )

        # 7. Formatear items de respuesta. El engine solo puntúa; el departamento sale del candidato.
        departamento_por_poi = {c["poi_id"]: c["departamento"] for c in candidate_pois}
        recommendations = [
            PoiRecommendationItem(
                poi_id=r["poi_id"],
                nombre=r["nombre"],
                score=r["score"],
                reason=r["reason"],
                ya_visitado=r["ya_visitado"],
                departamento=departamento_por_poi[r["poi_id"]],
                categorias=r.get("categorias", []),
                precio_min=r.get("precio_min"),
                precio_max=r.get("precio_max"),
                subscores=ExplanationSubscores(**r["subscores"]),
            )
            for r in ranked_results
        ]

        return HistoryRecommendationResponse(
            user_id=user_id,
            has_sufficient_history=True,
            total=len(recommendations),
            metadata=metadata,
            recommendations=recommendations,
        )

    def _fetch_user_ratings(self, session: Session, user_id: str) -> Dict[str, Any]:
        """Consulta todas las valoraciones del usuario y extrae categorías y precios de las positivas (>=4)."""
        sql_ratings = text("""
            SELECT 
                v.id,
                v."poiId" AS poi_id,
                v.puntuacion,
                v."fechaCreacion" AS fecha_creacion,
                p."precioMin" AS precio_min,
                p."precioMax" AS precio_max,
                ARRAY_AGG(cp."categoriaId") FILTER (WHERE cp."categoriaId" IS NOT NULL) AS category_ids
            FROM valoraciones v
            LEFT JOIN pois p ON p.id = v."poiId"
            LEFT JOIN categorias_poi cp ON cp."poiId" = v."poiId"
            WHERE v."usuarioId" = :user_id
            GROUP BY v.id, v."poiId", v.puntuacion, v."fechaCreacion", p."precioMin", p."precioMax"
        """)
        rows = session.execute(sql_ratings, {"user_id": user_id}).mappings().all()

        total_count = len(rows)
        positive_ratings = []
        for row in rows:
            if row["puntuacion"] is not None and int(row["puntuacion"]) >= 4:
                positive_ratings.append({
                    "poi_id": str(row["poi_id"]) if row["poi_id"] else None,
                    "puntuacion": int(row["puntuacion"]),
                    "created_at": row["fecha_creacion"],
                    "precio_min": float(row["precio_min"]) if row["precio_min"] is not None else None,
                    "precio_max": float(row["precio_max"]) if row["precio_max"] is not None else None,
                    "category_ids": [str(c) for c in (row["category_ids"] or []) if c],
                })

        return {"total_count": total_count, "positive_ratings": positive_ratings}

    def _fetch_user_finished_itineraries(self, session: Session, user_id: str) -> Dict[str, Any]:
        """Consulta itinerarios finalizados del usuario y extrae sus POIs y categorías."""
        sql_itineraries = text("""
            SELECT 
                i.id AS itinerario_id,
                i."fechaInicio" AS fecha_inicio,
                i."fechaFin" AS fecha_fin,
                ARRAY_AGG(DISTINCT ip."poiId") FILTER (WHERE ip."poiId" IS NOT NULL) AS poi_ids,
                ARRAY_AGG(DISTINCT cp."categoriaId") FILTER (WHERE cp."categoriaId" IS NOT NULL) AS category_ids
            FROM itinerarios i
            INNER JOIN estados_itinerario ei ON ei.id = i."estadoId"
            INNER JOIN usuarios_itinerarios ui ON ui."itinerarioId" = i.id
            LEFT JOIN itinerario_poi ip ON ip."itinerarioId" = i.id
            LEFT JOIN categorias_poi cp ON cp."poiId" = ip."poiId"
            WHERE ui."usuarioId" = :user_id
              AND (LOWER(ei.nombre) = 'finalizado' OR ei.nombre = 'FINALIZADO')
              AND i.fecha_baja IS NULL
            GROUP BY i.id, i."fechaInicio", i."fechaFin"
        """)
        rows = session.execute(sql_itineraries, {"user_id": user_id}).mappings().all()

        itineraries = []
        for row in rows:
            itineraries.append({
                "id": str(row["itinerario_id"]),
                "date": row["fecha_fin"] or row["fecha_inicio"],
                "poi_ids": [str(p) for p in (row["poi_ids"] or []) if p],
                "category_ids": [str(c) for c in (row["category_ids"] or []) if c],
            })

        return {"itineraries": itineraries}

    def _fetch_user_favorites(self, session: Session, user_id: str) -> Dict[str, Any]:
        """Consulta POIs favoritos del usuario y sus categorías asociadas."""
        sql_favs = text("""
            SELECT 
                fp."poiId" AS poi_id,
                ARRAY_AGG(cp."categoriaId") FILTER (WHERE cp."categoriaId" IS NOT NULL) AS category_ids
            FROM favoritos_poi fp
            LEFT JOIN categorias_poi cp ON cp."poiId" = fp."poiId"
            WHERE fp."usuarioId" = :user_id
            GROUP BY fp.id, fp."poiId"
        """)
        rows = session.execute(sql_favs, {"user_id": user_id}).mappings().all()

        favorites = []
        for row in rows:
            favorites.append({
                "poi_id": str(row["poi_id"]) if row["poi_id"] else None,
                "category_ids": [str(c) for c in (row["category_ids"] or []) if c],
            })

        return {"favorites": favorites}

    def _fetch_category_names(self, session: Session) -> Dict[str, str]:
        """Obtiene un mapa {categoria_id: nombre} para explicabilidad determinística."""
        sql_cats = text("SELECT id, nombre FROM categorias")
        rows = session.execute(sql_cats).mappings().all()
        return {str(r["id"]): str(r["nombre"]) for r in rows if r.get("id") and r.get("nombre")}

    def _fetch_approved_candidate_pois(self, session: Session) -> List[Dict[str, Any]]:
        """Consulta todos los POIs aprobados con sus categorías y rangos de precio."""
        sql_pois = text("""
            SELECT 
                p.id,
                p.nombre,
                p."precioMin" AS precio_min,
                p."precioMax" AS precio_max,
                p."puntuacionPromedio" AS puntuacion_promedio,
                p."cantidadReviews" AS cantidad_reviews,
                d.nombre AS departamento,
                ARRAY_AGG(cp."categoriaId") FILTER (WHERE cp."categoriaId" IS NOT NULL) AS category_ids
            FROM pois p
            INNER JOIN estados_poi ep ON ep.id = p."estadoId"
            INNER JOIN departamentos d ON d.id = p."departamentoId"
            LEFT JOIN categorias_poi cp ON cp."poiId" = p.id
            WHERE (LOWER(ep.nombre) = 'aprobado' OR ep.nombre = 'APROBADO')
            GROUP BY p.id, p.nombre, p."precioMin", p."precioMax", p."puntuacionPromedio", p."cantidadReviews", d.nombre
        """)
        rows = session.execute(sql_pois).mappings().all()

        candidates = []
        for row in rows:
            candidates.append({
                "id": str(row["id"]),
                "poi_id": str(row["id"]),
                "nombre": str(row["nombre"]),
                "precio_min": float(row["precio_min"]) if row["precio_min"] is not None else None,
                "precio_max": float(row["precio_max"]) if row["precio_max"] is not None else None,
                "puntuacion_promedio": float(row["puntuacion_promedio"]) if row["puntuacion_promedio"] is not None else 0.0,
                "cantidad_reviews": int(row["cantidad_reviews"]) if row["cantidad_reviews"] is not None else 0,
                "departamento": str(row["departamento"]),
                "category_ids": [str(c) for c in (row["category_ids"] or []) if c],
            })

        return candidates
