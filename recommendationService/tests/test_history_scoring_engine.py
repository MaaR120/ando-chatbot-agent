"""
Unit tests for HistoryScoringEngine (US-MRIA-04).
"""
import unittest
from datetime import datetime, timezone, timedelta
from app.services.history_scoring_engine import HistoryScoringEngine


class TestHistoryScoringEngine(unittest.TestCase):
    def setUp(self):
        self.engine = HistoryScoringEngine(
            weights={
                "positive_rating": 0.30,
                "category_frequency": 0.25,
                "favorite_affinity": 0.20,
                "recency": 0.15,
                "price_compatibility": 0.10,
            },
            half_life_days=180.0,
            min_ratings_for_history=5,
            min_finished_itineraries_for_history=1,
        )
        self.now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

    def test_precondition_sufficient_history(self):
        """Prueba los 4 casos de la precondición de historial suficiente."""
        # 1. 0 valoraciones + 0 itinerarios -> False
        self.assertFalse(self.engine.check_sufficient_history(0, 0))

        # 2. 4 valoraciones + 0 itinerarios -> False
        self.assertFalse(self.engine.check_sufficient_history(0, 4))

        # 3. 5 valoraciones + 0 itinerarios -> True
        self.assertTrue(self.engine.check_sufficient_history(0, 5))

        # 4. 0 valoraciones + 1 itinerario -> True
        self.assertTrue(self.engine.check_sufficient_history(1, 0))

        # 5. 10 valoraciones + 2 itinerarios -> True
        self.assertTrue(self.engine.check_sufficient_history(2, 10))

    def test_positive_ratings_only_affect_affinity(self):
        """
        Verifica que solo valoraciones >= 4 aumenten la afinidad.
        Puntuaciones 1, 2, 3 no deben generar afinidad positiva.
        """
        positive_ratings = [
            {"poi_id": "poi-bodega-1", "puntuacion": 5, "category_ids": ["cat-bodegas"]},
            {"poi_id": "poi-bodega-2", "puntuacion": 4, "category_ids": ["cat-bodegas"]},
            {"poi_id": "poi-museo-1", "puntuacion": 2, "category_ids": ["cat-museos"]},  # <= 3
            {"poi_id": "poi-aventura-1", "puntuacion": 3, "category_ids": ["cat-aventura"]},  # <= 3
        ]

        profile = self.engine.build_user_history_profile(
            positive_ratings=positive_ratings,
            finished_itineraries=[],
            favorite_pois=[],
            now=self.now,
        )

        rating_aff = profile["rating_affinity"]
        # Bodegas debe tener afinidad positiva media: (5/5 + 4/5)/2 = (1.0 + 0.8)/2 = 0.9
        self.assertIn("cat-bodegas", rating_aff)
        self.assertAlmostEqual(rating_aff["cat-bodegas"], 0.9)

        # Museos y Aventura NO deben tener afinidad positiva
        self.assertNotIn("cat-museos", rating_aff)
        self.assertNotIn("cat-aventura", rating_aff)

    def test_category_frequency_in_itineraries(self):
        """Verifica que a mayor frecuencia de categoría en itinerarios, mayor puntaje."""
        finished_itineraries = [
            {"id": "itin-1", "poi_ids": ["p1", "p2"], "category_ids": ["cat-bodegas", "cat-montana"]},
            {"id": "itin-2", "poi_ids": ["p3"], "category_ids": ["cat-bodegas"]},
            {"id": "itin-3", "poi_ids": ["p4"], "category_ids": ["cat-bodegas"]},
        ]

        profile = self.engine.build_user_history_profile(
            positive_ratings=[],
            finished_itineraries=finished_itineraries,
            favorite_pois=[],
            now=self.now,
        )

        freq_aff = profile["frequency_affinity"]
        # Bodegas aparece 3 veces (max) -> 1.0
        self.assertAlmostEqual(freq_aff["cat-bodegas"], 1.0)
        # Montana aparece 1 vez -> 1/3 ~ 0.3333
        self.assertAlmostEqual(freq_aff["cat-montana"], 1.0 / 3.0)

    def test_favorite_affinity(self):
        """Verifica que los favoritos aumenten la afinidad hacia sus categorías."""
        favorite_pois = [
            {"poi_id": "f1", "category_ids": ["cat-gastronomia", "cat-vino"]},
            {"poi_id": "f2", "category_ids": ["cat-gastronomia"]},
        ]

        profile = self.engine.build_user_history_profile(
            positive_ratings=[],
            finished_itineraries=[],
            favorite_pois=favorite_pois,
            now=self.now,
        )

        fav_aff = profile["favorite_affinity"]
        self.assertAlmostEqual(fav_aff["cat-gastronomia"], 1.0)
        self.assertAlmostEqual(fav_aff["cat-vino"], 0.5)

    def test_temporal_recency_decay(self):
        """Verifica que interacciones recientes tengan mayor peso que interacciones antiguas."""
        recent_date = self.now - timedelta(days=5)
        old_date = self.now - timedelta(days=360)

        positive_ratings = [
            {"poi_id": "p-rec", "puntuacion": 5, "category_ids": ["cat-reciente"], "created_at": recent_date},
            {"poi_id": "p-old", "puntuacion": 5, "category_ids": ["cat-antigua"], "created_at": old_date},
        ]

        profile = self.engine.build_user_history_profile(
            positive_ratings=positive_ratings,
            finished_itineraries=[],
            favorite_pois=[],
            now=self.now,
        )

        rec_aff = profile["recency_affinity"]
        self.assertGreater(rec_aff["cat-reciente"], rec_aff["cat-antigua"])
        # A 5 días, e^(-(ln2/180)*5) ~ 0.98
        self.assertGreater(rec_aff["cat-reciente"], 0.95)
        # A 360 días (2 vidas medias de 180), e^(-(ln2/180)*360) = 1/4 = 0.25
        self.assertAlmostEqual(rec_aff["cat-antigua"], 0.25, places=2)

    def test_price_compatibility(self):
        """Verifica compatibilidad de precio basada en POIs valorados positivamente (>=4)."""
        positive_ratings = [
            {"poi_id": "p1", "puntuacion": 5, "category_ids": ["cat-bodegas"], "precio_min": 10000, "precio_max": 20000},
            {"poi_id": "p2", "puntuacion": 4, "category_ids": ["cat-bodegas"], "precio_min": 15000, "precio_max": 25000},
        ]

        profile = self.engine.build_user_history_profile(
            positive_ratings=positive_ratings,
            finished_itineraries=[],
            favorite_pois=[],
            now=self.now,
        )

        # Precio promedio usuario ~ 17500, rango 15000 - 20000
        # POI candidato en rango (ej: 16000) -> compatibilidad 1.0
        candidate_in_range = {"poi_id": "c1", "nombre": "Bodega Ideal", "category_ids": ["cat-bodegas"], "precio_min": 14000, "precio_max": 18000}
        score_in_range = self.engine.score_candidate_poi(candidate_in_range, profile)
        self.assertAlmostEqual(score_in_range["subscores"]["price_compatibility_score"], 1.0)

        # POI candidato fuera de rango (ej: 80000) -> compatibilidad reducida
        candidate_expensive = {"poi_id": "c2", "nombre": "Bodega Ultra Luxe", "category_ids": ["cat-bodegas"], "precio_min": 75000, "precio_max": 85000}
        score_expensive = self.engine.score_candidate_poi(candidate_expensive, profile)
        self.assertLess(score_expensive["subscores"]["price_compatibility_score"], 0.5)

        # POI candidato sin precio -> no penaliza y redistribuye peso dinámicamente
        candidate_no_price = {"poi_id": "c3", "nombre": "Bodega Sin Precio", "category_ids": ["cat-bodegas"]}
        score_no_price = self.engine.score_candidate_poi(candidate_no_price, profile)
        self.assertIsNone(score_no_price["subscores"]["price_compatibility_score"])
        self.assertNotIn("price_compatibility", score_no_price["subscores"]["active_weights"])
        # Suma de active weights sigue siendo 1.0
        self.assertAlmostEqual(sum(score_no_price["subscores"]["active_weights"].values()), 1.0, places=3)

    def test_exclusion_of_visited_pois(self):
        """Verifica que POIs visitados en itinerarios finalizados sean excluidos por defecto."""
        finished_itineraries = [
            {"id": "itin-1", "poi_ids": ["poi-visitado-1", "poi-visitado-2"], "category_ids": ["cat-bodegas"]},
        ]

        profile = self.engine.build_user_history_profile(
            positive_ratings=[{"poi_id": "p1", "puntuacion": 5, "category_ids": ["cat-bodegas"]}],
            finished_itineraries=finished_itineraries,
            favorite_pois=[],
            now=self.now,
        )

        candidates = [
            {"poi_id": "poi-visitado-1", "nombre": "Visitado 1", "category_ids": ["cat-bodegas"]},
            {"poi_id": "poi-nuevo-1", "nombre": "Nuevo 1", "category_ids": ["cat-bodegas"]},
        ]

        # Por defecto include_visited=False -> solo nuevo 1
        ranked = self.engine.rank_candidates(candidates, profile, include_visited=False)
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["poi_id"], "poi-nuevo-1")

        # Con include_visited=True -> ambos presentes
        ranked_all = self.engine.rank_candidates(candidates, profile, include_visited=True)
        self.assertEqual(len(ranked_all), 2)
        visitado_item = next(p for p in ranked_all if p["poi_id"] == "poi-visitado-1")
        self.assertTrue(visitado_item["ya_visitado"])

    def test_dynamic_weight_renormalization_and_bounds(self):
        """Verifica que todos los scores estén en [0, 1] y los pesos sumen 1.0 siempre."""
        finished_itineraries = [
            {"id": "itin-1", "poi_ids": ["p1"], "category_ids": ["cat-aventura"]},
        ]

        # Usuario sin valoraciones ni favoritos (solo itinerario)
        profile = self.engine.build_user_history_profile(
            positive_ratings=[],
            finished_itineraries=finished_itineraries,
            favorite_pois=[],
            now=self.now,
        )

        candidate = {"poi_id": "c1", "nombre": "Rafting Mendoza", "category_ids": ["cat-aventura"]}
        result = self.engine.score_candidate_poi(candidate, profile)

        # Score entre 0.0 y 1.0
        self.assertGreaterEqual(result["score"], 0.0)
        self.assertLessEqual(result["score"], 1.0)

        # Suma de active_weights = 1.0
        weights_sum = sum(result["subscores"]["active_weights"].values())
        self.assertAlmostEqual(weights_sum, 1.0, places=3)

    def test_ranking_sort_order(self):
        """Verifica que el ranking se ordene estrictamente de mayor a menor score."""
        positive_ratings = [
            {"poi_id": "p1", "puntuacion": 5, "category_ids": ["cat-bodegas"]},
            {"poi_id": "p2", "puntuacion": 4, "category_ids": ["cat-montana"]},
        ]
        finished_itineraries = [
            {"id": "itin-1", "poi_ids": ["p1"], "category_ids": ["cat-bodegas", "cat-montana"]},
            {"id": "itin-2", "poi_ids": ["p1"], "category_ids": ["cat-bodegas"]},
        ]

        profile = self.engine.build_user_history_profile(
            positive_ratings=positive_ratings,
            finished_itineraries=finished_itineraries,
            favorite_pois=[],
            now=self.now,
        )

        candidates = [
            {"poi_id": "c-low", "nombre": "Museo Incompatible", "category_ids": ["cat-otro"]},
            {"poi_id": "c-high", "nombre": "Bodega Top", "category_ids": ["cat-bodegas"]},
            {"poi_id": "c-mid", "nombre": "Montaña Aventura", "category_ids": ["cat-montana"]},
        ]

        ranked = self.engine.rank_candidates(candidates, profile, limit=10)
        self.assertEqual(ranked[0]["poi_id"], "c-high")
        self.assertEqual(ranked[1]["poi_id"], "c-mid")
        self.assertEqual(ranked[2]["poi_id"], "c-low")
        self.assertGreater(ranked[0]["score"], ranked[1]["score"])
        self.assertGreater(ranked[1]["score"], ranked[2]["score"])

    def test_poi_without_categories_does_not_crash(self):
        """Verifica que un POI sin categorías maneje la señal limpiamente sin fallar."""
        profile = self.engine.build_user_history_profile(
            positive_ratings=[{"poi_id": "p1", "puntuacion": 5, "category_ids": ["cat-1"]}],
            finished_itineraries=[],
            favorite_pois=[],
            now=self.now,
        )

        candidate = {"poi_id": "c-no-cat", "nombre": "POI Huérfano", "category_ids": []}
        result = self.engine.score_candidate_poi(candidate, profile)

        self.assertEqual(result["score"], 0.0)
        self.assertIn("poi_id", result)


if __name__ == "__main__":
    unittest.main()
