"""
Deterministic Scoring Engine for US-MRIA-04 History Recommendation.
Pure algorithmic implementation without direct database dependency.
"""
import math
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set, Tuple


class HistoryScoringEngine:
    """
    Motor determinístico de scoring ponderado basado en el historial del turista.
    Implementa:
    1. Afinidad por valoraciones positivas (puntuacion >= 4).
    2. Frecuencia de categorías en itinerarios finalizados.
    3. Afinidad por POIs favoritos.
    4. Recencia temporal con decaimiento exponencial.
    5. Compatibilidad de rango de precio con POIs valorados positivamente.
    6. Re-normalización dinámica de pesos.
    7. Exclusión determinística de POIs ya visitados.
    8. Explicabilidad transparente.
    """

    DEFAULT_WEIGHTS = {
        "positive_rating": 0.30,
        "category_frequency": 0.25,
        "favorite_affinity": 0.20,
        "recency": 0.15,
        "price_compatibility": 0.10,
    }

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        half_life_days: float = 180.0,
        min_ratings_for_history: int = 5,
        min_finished_itineraries_for_history: int = 1,
    ):
        self.weights = {**self.DEFAULT_WEIGHTS, **(weights or {})}
        self.half_life_days = max(1.0, float(half_life_days))
        self.decay_lambda = math.log(2) / self.half_life_days
        self.min_ratings_for_history = min_ratings_for_history
        self.min_finished_itineraries_for_history = min_finished_itineraries_for_history

    def check_sufficient_history(
        self,
        finished_itineraries_count: int,
        total_ratings_count: int,
    ) -> bool:
        """
        Precondición US-MRIA-04:
        El usuario tiene historial suficiente si tiene al menos 1 itinerario finalizado
        O al menos 5 valoraciones registradas en total.
        """
        return (
            finished_itineraries_count >= self.min_finished_itineraries_for_history
            or total_ratings_count >= self.min_ratings_for_history
        )

    def calculate_temporal_decay(self, interaction_date: Optional[datetime], now: Optional[datetime] = None) -> float:
        """
        Calcula el factor de decaimiento exponencial en función de los días transcurridos.
        Decay(dt) = e^(-lambda * dt) en el intervalo (0.0, 1.0].
        """
        if not interaction_date:
            return 0.0

        if now is None:
            now = datetime.now(timezone.utc)

        # Normalizar fechas a naive o aware para restar
        if interaction_date.tzinfo is not None and now.tzinfo is None:
            interaction_date = interaction_date.replace(tzinfo=None)
        elif interaction_date.tzinfo is None and now.tzinfo is not None:
            interaction_date = interaction_date.replace(tzinfo=timezone.utc)

        delta_days = max(0.0, (now - interaction_date).total_seconds() / 86400.0)
        return float(math.exp(-self.decay_lambda * delta_days))

    def build_user_history_profile(
        self,
        positive_ratings: List[Dict[str, Any]],
        finished_itineraries: List[Dict[str, Any]],
        favorite_pois: List[Dict[str, Any]],
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Construye el perfil de afinidades históricas por categoría y rango de precio del usuario.
        """
        # 1. Afinidad por valoraciones positivas (puntuacion >= 4)
        category_ratings: Dict[str, List[float]] = {}
        category_latest_date: Dict[str, datetime] = {}
        positive_prices: List[float] = []

        for r in positive_ratings:
            score_val = float(r.get("puntuacion", 0))
            if score_val < 4.0:
                # Regla 1: Ignorar ratings 1, 2, 3 para afinidad positiva
                continue

            normalized_score = score_val / 5.0  # 4->0.8, 5->1.0
            cat_ids = r.get("category_ids", [])
            for cat_id in cat_ids:
                if cat_id:
                    category_ratings.setdefault(str(cat_id), []).append(normalized_score)

            # Extraer precio de referencia si existe
            p_min = r.get("precio_min")
            p_max = r.get("precio_max")
            if p_min is not None and p_max is not None:
                positive_prices.append((float(p_min) + float(p_max)) / 2.0)
            elif p_min is not None:
                positive_prices.append(float(p_min))
            elif p_max is not None:
                positive_prices.append(float(p_max))

            r_date = r.get("created_at") or r.get("fecha_creacion")
            if isinstance(r_date, datetime):
                for cat_id in cat_ids:
                    cid = str(cat_id)
                    if cid not in category_latest_date or r_date > category_latest_date[cid]:
                        category_latest_date[cid] = r_date

        rating_affinity: Dict[str, float] = {}
        for cat_id, scores in category_ratings.items():
            rating_affinity[cat_id] = sum(scores) / len(scores)

        # 2. Frecuencia de categorías en itinerarios finalizados
        category_itin_freq: Dict[str, int] = {}
        visited_poi_ids: Set[str] = set()

        for itin in finished_itineraries:
            for poi_id in itin.get("poi_ids", []):
                if poi_id:
                    visited_poi_ids.add(str(poi_id))

            for cat_id in itin.get("category_ids", []):
                if cat_id:
                    cid = str(cat_id)
                    category_itin_freq[cid] = category_itin_freq.get(cid, 0) + 1

            itin_date = itin.get("date") or itin.get("fecha_fin") or itin.get("fecha_inicio")
            if isinstance(itin_date, datetime):
                for cat_id in itin.get("category_ids", []):
                    cid = str(cat_id)
                    if cid not in category_latest_date or itin_date > category_latest_date[cid]:
                        category_latest_date[cid] = itin_date

        max_itin_freq = max(category_itin_freq.values()) if category_itin_freq else 1
        frequency_affinity: Dict[str, float] = {
            cat_id: count / max_itin_freq for cat_id, count in category_itin_freq.items()
        }

        # 3. Afinidad por POIs favoritos
        category_fav_count: Dict[str, int] = {}
        for fav in favorite_pois:
            poi_id = fav.get("poi_id")
            if poi_id:
                # Opcional: registrar favoritos como conocidos si se desea
                pass
            for cat_id in fav.get("category_ids", []):
                if cat_id:
                    cid = str(cat_id)
                    category_fav_count[cid] = category_fav_count.get(cid, 0) + 1

            fav_date = fav.get("created_at") or fav.get("fecha_creacion")
            if isinstance(fav_date, datetime):
                for cat_id in fav.get("category_ids", []):
                    cid = str(cat_id)
                    if cid not in category_latest_date or fav_date > category_latest_date[cid]:
                        category_latest_date[cid] = fav_date

        max_fav_count = max(category_fav_count.values()) if category_fav_count else 1
        favorite_affinity: Dict[str, float] = {
            cat_id: count / max_fav_count for cat_id, count in category_fav_count.items()
        }

        # 4. Recencia por categoría
        recency_affinity: Dict[str, float] = {
            cat_id: self.calculate_temporal_decay(dt, now=now)
            for cat_id, dt in category_latest_date.items()
        }

        # 5. Rango de precio histórico derivado de valoraciones positivas
        price_profile = None
        if positive_prices:
            min_p = min(positive_prices)
            max_p = max(positive_prices)
            avg_p = sum(positive_prices) / len(positive_prices)
            price_profile = {
                "min_price": min_p,
                "max_price": max_p,
                "avg_price": avg_p,
            }

        return {
            "rating_affinity": rating_affinity,
            "frequency_affinity": frequency_affinity,
            "favorite_affinity": favorite_affinity,
            "recency_affinity": recency_affinity,
            "visited_poi_ids": visited_poi_ids,
            "price_profile": price_profile,
            "has_positive_ratings": len(rating_affinity) > 0,
            "has_itin_frequencies": len(frequency_affinity) > 0,
            "has_favorites": len(favorite_affinity) > 0,
        }

    def score_candidate_poi(
        self,
        poi: Dict[str, Any],
        user_profile: Dict[str, Any],
        category_name_map: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Calcula el score determinístico normalizado [0.0, 1.0] para un POI candidato.
        """
        poi_id = str(poi.get("poi_id") or poi.get("id"))
        cat_ids = [str(c) for c in poi.get("category_ids", []) if c]
        p_min = poi.get("precio_min")
        p_max = poi.get("precio_max")

        # 1. Positive Rating Score
        rating_aff = user_profile.get("rating_affinity", {})
        rating_scores = [rating_aff.get(cid, 0.0) for cid in cat_ids]
        s_rating = max(rating_scores) if rating_scores else 0.0

        # 2. Category Frequency Score
        freq_aff = user_profile.get("frequency_affinity", {})
        freq_scores = [freq_aff.get(cid, 0.0) for cid in cat_ids]
        s_freq = max(freq_scores) if freq_scores else 0.0

        # 3. Favorite Affinity Score
        fav_aff = user_profile.get("favorite_affinity", {})
        fav_scores = [fav_aff.get(cid, 0.0) for cid in cat_ids]
        s_fav = max(fav_scores) if fav_scores else 0.0

        # 4. Recency Score
        rec_aff = user_profile.get("recency_affinity", {})
        rec_scores = [rec_aff.get(cid, 0.0) for cid in cat_ids]
        s_recency = max(rec_scores) if rec_scores else 0.0

        # 5. Price Compatibility Score
        price_profile = user_profile.get("price_profile")
        s_price: Optional[float] = None
        has_price_data = False

        if price_profile and (p_min is not None or p_max is not None):
            has_price_data = True
            if p_min is not None and p_max is not None:
                poi_mid_price = (float(p_min) + float(p_max)) / 2.0
            elif p_min is not None:
                poi_mid_price = float(p_min)
            else:
                poi_mid_price = float(p_max)

            min_ref = price_profile["min_price"]
            max_ref = price_profile["max_price"]
            avg_ref = price_profile["avg_price"]

            # Rango con margen de tolerancia del 20%
            if (min_ref * 0.8) <= poi_mid_price <= (max_ref * 1.2):
                s_price = 1.0
            else:
                denom = max(avg_ref, poi_mid_price, 1.0)
                diff = abs(poi_mid_price - avg_ref)
                s_price = max(0.0, 1.0 - (diff / denom))

        # Re-normalización dinámica de pesos
        active_signals: Dict[str, float] = {
            "positive_rating": s_rating,
            "category_frequency": s_freq,
            "favorite_affinity": s_fav,
            "recency": s_recency,
        }
        if has_price_data and s_price is not None:
            active_signals["price_compatibility"] = s_price

        # Identificar qué señales tienen peso asignado
        active_weight_sum = sum(self.weights[k] for k in active_signals.keys() if k in self.weights)
        if active_weight_sum <= 0:
            active_weight_sum = 1.0

        normalized_weights: Dict[str, float] = {}
        for k in active_signals.keys():
            w_base = self.weights.get(k, 0.0)
            normalized_weights[k] = round(w_base / active_weight_sum, 4)

        # Ajuste de redondeo para que sumen exactamente 1.0
        weight_diff = 1.0 - sum(normalized_weights.values())
        if normalized_weights:
            first_key = next(iter(normalized_weights))
            normalized_weights[first_key] = round(normalized_weights[first_key] + weight_diff, 4)

        # Score Final
        final_score = sum(
            normalized_weights[k] * active_signals[k] for k in active_signals.keys()
        )
        final_score = max(0.0, min(1.0, round(final_score, 4)))

        # Generar justificación determinística explicable
        reason = self._generate_explanation_reason(
            s_rating=s_rating,
            s_freq=s_freq,
            s_fav=s_fav,
            s_recency=s_recency,
            s_price=s_price,
            cat_ids=cat_ids,
            category_name_map=category_name_map or {},
        )

        visited_ids = user_profile.get("visited_poi_ids", set())
        is_visited = poi_id in visited_ids

        return {
            "poi_id": poi_id,
            "nombre": poi.get("nombre", ""),
            "score": final_score,
            "reason": reason,
            "ya_visitado": is_visited,
            "precio_min": p_min,
            "precio_max": p_max,
            "subscores": {
                "positive_rating_score": round(s_rating, 4),
                "category_frequency_score": round(s_freq, 4),
                "favorite_affinity_score": round(s_fav, 4),
                "recency_score": round(s_recency, 4),
                "price_compatibility_score": round(s_price, 4) if s_price is not None else None,
                "final_score": final_score,
                "active_weights": normalized_weights,
            },
        }

    def _generate_explanation_reason(
        self,
        s_rating: float,
        s_freq: float,
        s_fav: float,
        s_recency: float,
        s_price: Optional[float],
        cat_ids: List[str],
        category_name_map: Dict[str, str],
    ) -> str:
        """
        Genera una explicación breve y determinística en español basada en las señales de mayor contribución.
        """
        category_names = [category_name_map.get(cid, cid) for cid in cat_ids if cid]
        cat_str = f" de {', '.join(category_names[:2])}" if category_names else ""

        reasons = []
        if s_rating >= 0.8:
            reasons.append(f"tus valoraciones de 4★ y 5★{cat_str}")
        elif s_rating >= 0.5:
            reasons.append(f"tus valoraciones positivas anteriores{cat_str}")

        if s_freq >= 0.6:
            reasons.append("tus visitas frecuentes en itinerarios anteriores")
        elif s_fav >= 0.6:
            reasons.append("tus POIs guardados en favoritos")

        if s_price is not None and s_price >= 0.9:
            reasons.append("tu rango habitual de gasto")

        if s_recency >= 0.7:
            reasons.append("tus actividades recientes")

        if not reasons:
            if cat_str:
                return f"Recomendado por afinidad histórica con categorías{cat_str}."
            return "Recomendado en base a tus preferencias y viajes anteriores."

        return f"Basado en {' y '.join(reasons[:2])}."

    def rank_candidates(
        self,
        candidate_pois: List[Dict[str, Any]],
        user_profile: Dict[str, Any],
        limit: int = 10,
        include_visited: bool = False,
        category_name_map: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Calcula el score de todos los POIs candidatos, filtra visitados si corresponde y ordena por score descendente.
        """
        scored_pois = []
        visited_ids = user_profile.get("visited_poi_ids", set())

        for poi in candidate_pois:
            poi_id = str(poi.get("poi_id") or poi.get("id"))
            is_visited = poi_id in visited_ids

            # Regla de exclusión de visitados
            if is_visited and not include_visited:
                continue

            cat_map = category_name_map or {}
            scored = self.score_candidate_poi(poi, user_profile, cat_map)
            scored["categorias"] = [
                cat_map.get(str(c), str(c))
                for c in poi.get("category_ids", [])
                if c
            ]
            scored_pois.append(scored)

        # Ordenamiento determinístico: score DESC -> rating DESC -> nombre ASC
        scored_pois.sort(
            key=lambda x: (
                -x["score"],
                -float(x["subscores"]["positive_rating_score"]),
                x["nombre"].lower(),
            )
        )

        return scored_pois[:limit]
