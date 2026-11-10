"""
Collaborative Filtering Engine using Scikit-Learn (Cosine Similarity).
US-MRIA-09: User-Based Collaborative Recommendation Engine.
"""
from typing import Dict, List, Set, Tuple, Any, Optional
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from app.schemas.collaborative_recommendation import (
    CollaborativePoiItem,
    CollaborativeSubscores,
    CollaborativeMetadata,
    CollaborativeRecommendationResponse,
)


class CollaborativeEngine:
    """
    Motor matemático de filtrado colaborativo determinístico y explicable.
    Calcula similitud de cosenos sobre vectores de usuarios construidos a partir de:
    - Preferencias de categorías
    - Valoraciones de POIs (ratings 1-5)
    - Favoritos guardados
    - POIs completados en itinerarios
    """

    def __init__(self, min_global_ratings: int = 5):
        self.min_global_ratings = min_global_ratings

    def calculate_collaborative_recommendations(
        self,
        target_user_id: str,
        all_user_ids: List[str],
        all_category_ids: List[str],
        approved_pois: Dict[str, Dict[str, Any]],
        user_preferences: Dict[str, Set[str]],
        user_ratings: Dict[Tuple[str, str], float],
        user_favorites: Dict[str, Set[str]],
        user_visited_pois: Dict[str, Set[str]],
        k_neighbors: int = 10,
        limit: int = 10,
        include_visited: bool = False,
    ) -> CollaborativeRecommendationResponse:
        total_global_ratings = len(user_ratings)
        total_users = len(all_user_ids)

        # 1. Validación de precondición global (mínimo de datos)
        if total_global_ratings < self.min_global_ratings or total_users < 2:
            return CollaborativeRecommendationResponse(
                user_id=target_user_id,
                has_sufficient_data=False,
                total=0,
                metadata=CollaborativeMetadata(
                    has_sufficient_data=False,
                    total_users_analyzed=total_users,
                    neighbors_found_count=0,
                    global_ratings_count=total_global_ratings,
                    used_fallback=True,
                    fallback_strategy="history",
                ),
                recommendations=[],
            )

        if target_user_id not in all_user_ids:
            all_user_ids = list(all_user_ids) + [target_user_id]
            total_users = len(all_user_ids)

        user_index = {uid: idx for idx, uid in enumerate(all_user_ids)}
        target_idx = user_index[target_user_id]

        poi_ids_list = list(approved_pois.keys())
        poi_index = {pid: idx for idx, pid in enumerate(poi_ids_list)}
        cat_index = {cid: idx for idx, cid in enumerate(all_category_ids)}

        num_users = len(all_user_ids)
        num_pois = len(poi_ids_list)
        num_cats = len(all_category_ids)

        # 2. Construcción de Matrices de Usuario
        # Matriz 1: POI Interaction Matrix (dim: Users x POIs)
        # Ratings normalizados a [0.2, 1.0], Favoritos = 0.8, Itinerarios finalizados = 0.6
        interaction_matrix = np.zeros((num_users, num_pois), dtype=np.float32)
        for (uid, pid), r in user_ratings.items():
            if uid in user_index and pid in poi_index:
                # Normalizar rating 1..5 -> 0.2..1.0
                interaction_matrix[user_index[uid], poi_index[pid]] = max(0.2, min(1.0, float(r) / 5.0))

        for uid, fav_set in user_favorites.items():
            if uid in user_index:
                for pid in fav_set:
                    if pid in poi_index:
                        idx_u = user_index[uid]
                        idx_p = poi_index[pid]
                        interaction_matrix[idx_u, idx_p] = max(interaction_matrix[idx_u, idx_p], 0.8)

        for uid, vis_set in user_visited_pois.items():
            if uid in user_index:
                for pid in vis_set:
                    if pid in poi_index:
                        idx_u = user_index[uid]
                        idx_p = poi_index[pid]
                        interaction_matrix[idx_u, idx_p] = max(interaction_matrix[idx_u, idx_p], 0.6)

        # Matriz 2: Category Preference Matrix (dim: Users x Categories)
        cat_matrix = np.zeros((num_users, max(1, num_cats)), dtype=np.float32)
        if num_cats > 0:
            for uid, c_set in user_preferences.items():
                if uid in user_index:
                    for cid in c_set:
                        if cid in cat_index:
                            cat_matrix[user_index[uid], cat_index[cid]] = 1.0

        # Vector de usuario híbrido combinado: [Interacciones (peso 0.65), Categorías (peso 0.35)]
        feature_vector = np.hstack([interaction_matrix * 0.65, cat_matrix * 0.35])

        # Verificar si el target user tiene algún dato en su vector
        target_norm = np.linalg.norm(feature_vector[target_idx])
        if target_norm == 0.0:
            # El usuario no tiene preferencias ni interacciones registradas
            return CollaborativeRecommendationResponse(
                user_id=target_user_id,
                has_sufficient_data=False,
                total=0,
                metadata=CollaborativeMetadata(
                    has_sufficient_data=False,
                    total_users_analyzed=total_users,
                    neighbors_found_count=0,
                    global_ratings_count=total_global_ratings,
                    used_fallback=True,
                    fallback_strategy="preferences",
                ),
                recommendations=[],
            )

        # 3. Cálculo de Cosine Similarity con Scikit-Learn
        similarities = cosine_similarity(feature_vector[target_idx : target_idx + 1], feature_vector)[0]

        # 4. Extracción de los Top K Vecinos Más Similares
        # Ordenar descendente por similitud excluyendo al propio usuario
        candidate_neighbors: List[Tuple[int, float]] = []
        for other_idx, sim in enumerate(similarities):
            if other_idx != target_idx and sim > 0.01:
                candidate_neighbors.append((other_idx, float(sim)))

        candidate_neighbors.sort(key=lambda x: x[1], reverse=True)
        top_k = candidate_neighbors[:k_neighbors]

        if not top_k:
            return CollaborativeRecommendationResponse(
                user_id=target_user_id,
                has_sufficient_data=True,
                total=0,
                metadata=CollaborativeMetadata(
                    has_sufficient_data=True,
                    total_users_analyzed=total_users,
                    neighbors_found_count=0,
                    global_ratings_count=total_global_ratings,
                    used_fallback=True,
                    fallback_strategy="history",
                ),
                recommendations=[],
            )

        # 5. Generación de Scores de POIs Candidatos
        target_visited = user_visited_pois.get(target_user_id, set())
        target_rated = {pid for (uid, pid) in user_ratings.keys() if uid == target_user_id}

        poi_scores: Dict[str, Dict[str, Any]] = {}

        for n_idx, sim in top_k:
            neighbor_uid = all_user_ids[n_idx]
            # Revisar todas las interacciones de este vecino
            for pid, p_idx in poi_index.items():
                interaction_val = interaction_matrix[n_idx, p_idx]
                if interaction_val > 0.3:  # Tuvo interacción positiva relevante
                    is_already_visited = (pid in target_visited) or (pid in target_rated)
                    if not include_visited and is_already_visited:
                        continue

                    if pid not in poi_scores:
                        poi_scores[pid] = {
                            "sim_weights": [],
                            "interactions": [],
                            "neighbor_count": 0,
                            "is_visited": is_already_visited,
                        }

                    poi_scores[pid]["sim_weights"].append(sim)
                    poi_scores[pid]["interactions"].append(interaction_val)
                    poi_scores[pid]["neighbor_count"] += 1

        # 6. Ponderación y Construcción del Listado Final
        results: List[CollaborativePoiItem] = []

        for pid, data in poi_scores.items():
            poi_meta = approved_pois.get(pid, {})
            sim_list = data["sim_weights"]
            interact_list = data["interactions"]
            count = data["neighbor_count"]

            sim_avg = float(np.mean(sim_list))
            interact_avg = float(np.mean(interact_list))
            # Score combinado: similitud media (50%) + fuerza interacción (30%) + bonus de consenso/frecuencia (20%)
            consensus_bonus = min(1.0, count / max(1.0, min(5.0, len(top_k))))
            final_score = round(float(0.50 * sim_avg + 0.30 * interact_avg + 0.20 * consensus_bonus), 4)

            # Explicación clara y determinística
            if count == 1:
                reason = "Recomendado porque un turista con gustos muy similares a los tuyos visitó y valoró positivamente este lugar."
            else:
                reason = f"Recomendado porque {count} turistas con gustos e intereses similares a los tuyos visitaron y valoraron este lugar."

            results.append(
                CollaborativePoiItem(
                    poi_id=pid,
                    nombre=poi_meta.get("nombre", "POI Turístico"),
                    score=final_score,
                    reason=reason,
                    subscores=CollaborativeSubscores(
                        neighbor_similarity_avg=round(sim_avg, 4),
                        interaction_strength=round(interact_avg, 4),
                        final_score=final_score,
                    ),
                    ya_visitado=data["is_visited"],
                    categorias=poi_meta.get("categorias", []),
                    precio_min=poi_meta.get("precio_min"),
                    precio_max=poi_meta.get("precio_max"),
                    similar_users_count=count,
                )
            )

        # Ordenar descendentemente por score final
        results.sort(key=lambda x: x.score, reverse=True)
        final_recommendations = results[:limit]

        return CollaborativeRecommendationResponse(
            user_id=target_user_id,
            has_sufficient_data=True,
            total=len(final_recommendations),
            metadata=CollaborativeMetadata(
                has_sufficient_data=True,
                total_users_analyzed=total_users,
                neighbors_found_count=len(top_k),
                global_ratings_count=total_global_ratings,
                used_fallback=False,
                fallback_strategy=None,
            ),
            recommendations=final_recommendations,
        )
