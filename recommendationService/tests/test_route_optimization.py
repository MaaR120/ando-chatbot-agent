"""
Unit & Integration tests for Route Optimization with Google OR-Tools (US-MRIA-05).
Ando Recommendation & Routing Service (MRIA).
"""
import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.route_optimization import (
    HorarioOptimizationItem,
    PoiOptimizationItem,
    RouteOptimizationRequest,
)
from app.services.route_optimization_service import RouteOptimizationService


class TestRouteOptimizationService(unittest.TestCase):
    def setUp(self):
        self.service = RouteOptimizationService()
        self.client = TestClient(app)

    def test_haversine_distance(self):
        """Verifica el cálculo de distancias Haversine."""
        # Plaza Independencia a Bodega Catena Zapata (~30 km)
        dist = self.service.haversine_distance_meters(-32.8895, -68.8458, -33.1558, -68.9189)
        self.assertTrue(25000 < dist < 35000)

        # Mismo punto
        dist_same = self.service.haversine_distance_meters(-32.8895, -68.8458, -32.8895, -68.8458)
        self.assertEqual(dist_same, 0)

    def test_calculate_transfer_minutes(self):
        """Verifica el cálculo de minutos de traslado según modo de viaje."""
        # 3000 metros en auto (500 m/min) -> 6 minutos
        mins_auto = self.service.calculate_transfer_minutes(3000, "auto")
        self.assertEqual(mins_auto, 6)

        # 3000 metros a pie (83.33 m/min) -> 37 minutos
        mins_pie = self.service.calculate_transfer_minutes(3000, "pie")
        self.assertEqual(mins_pie, 37)


    def test_optimize_2_pois_success(self):
        """Criterio 4: Optimización con exactamente 2 POIs."""
        pois = [
            PoiOptimizationItem(
                poi_id="poi-1",
                nombre="Plaza Independencia",
                latitud=-32.8895,
                longitud=-68.8458,
                duracion_estimada=60,
                horarios=[
                    HorarioOptimizationItem(
                        dia_semana_desde=0,
                        hora_desde="08:00",
                        dia_semana_hasta=6,
                        hora_hasta="20:00",
                    )
                ],
            ),
            PoiOptimizationItem(
                poi_id="poi-2",
                nombre="Parque General San Martín",
                latitud=-32.8870,
                longitud=-68.8700,
                duracion_estimada=90,
                horarios=[
                    HorarioOptimizationItem(
                        dia_semana_desde=0,
                        hora_desde="08:00",
                        dia_semana_hasta=6,
                        hora_hasta="22:00",
                    )
                ],
            ),
        ]
        request = RouteOptimizationRequest(
            pois=pois,
            fecha="2026-09-10",
            hora_inicio_offset=540,  # 09:00
            modo_viaje="auto",
        )
        response = self.service.optimize_route(request)

        self.assertEqual(response.status, "ok")
        self.assertEqual(len(response.orden_optimizado), 2)
        self.assertEqual(len(response.paradas), 2)
        self.assertEqual(len(response.conflictos), 0)
        self.assertGreater(response.distancia_total_metros, 0)
        self.assertGreater(response.tiempo_total_minutos, 150)
        # La primera parada inicia a las 09:00
        self.assertEqual(response.paradas[0].hora_estimada_llegada, "09:00")
        self.assertIsNotNone(response.paradas[0].tiempo_traslado_siguiente)
        self.assertIsNone(response.paradas[1].tiempo_traslado_siguiente)

    def test_optimize_3_pois_with_ortools(self):
        """Criterio 1: Optimización de 3 o más POIs con OR-Tools minimizando traslados."""
        pois = [
            # POI Lejano al sur
            PoiOptimizationItem(
                poi_id="poi-lujan",
                nombre="Bodega en Luján de Cuyo",
                latitud=-33.0000,
                longitud=-68.8800,
                duracion_estimada=90,
            ),
            # POI en Centro
            PoiOptimizationItem(
                poi_id="poi-centro",
                nombre="Museo en Ciudad de Mendoza",
                latitud=-32.8900,
                longitud=-68.8400,
                duracion_estimada=60,
            ),
            # POI cercano al centro
            PoiOptimizationItem(
                poi_id="poi-godoycruz",
                nombre="Parque en Godoy Cruz",
                latitud=-32.9200,
                longitud=-68.8500,
                duracion_estimada=45,
            ),
        ]
        request = RouteOptimizationRequest(
            pois=pois,
            fecha="2026-09-10",
            hora_inicio_offset=600,  # 10:00
            modo_viaje="auto",
        )
        response = self.service.optimize_route(request)

        self.assertEqual(response.status, "ok")
        self.assertEqual(len(response.orden_optimizado), 3)
        self.assertEqual(len(response.paradas), 3)
        self.assertEqual(response.paradas[0].orden_secuencia, 1)
        self.assertEqual(response.paradas[1].orden_secuencia, 2)
        self.assertEqual(response.paradas[2].orden_secuencia, 3)

    def test_poi_closed_schedule_conflict(self):
        """Criterio 2: Detección de POI cerrado en el horario calculado."""
        pois = [
            PoiOptimizationItem(
                poi_id="poi-tarde",
                nombre="Atracción Matutina Larga",
                latitud=-32.8895,
                longitud=-68.8458,
                duracion_estimada=300,  # 5 horas
                horarios=[
                    HorarioOptimizationItem(
                        dia_semana_desde=0,
                        hora_desde="08:00",
                        dia_semana_hasta=6,
                        hora_hasta="18:00",
                    )
                ],
            ),
            PoiOptimizationItem(
                poi_id="poi-temprano",
                nombre="Lugar que cierra a las 11:00",
                latitud=-32.8950,
                longitud=-68.8500,
                duracion_estimada=60,
                horarios=[
                    HorarioOptimizationItem(
                        dia_semana_desde=0,
                        hora_desde="09:00",
                        dia_semana_hasta=6,
                        hora_hasta="11:00",  # Cierra muy temprano
                    )
                ],
            ),
        ]
        # Iniciar a las 10:00
        request = RouteOptimizationRequest(
            pois=pois,
            fecha="2026-09-10",
            hora_inicio_offset=600,  # 10:00
            modo_viaje="auto",
        )
        response = self.service.optimize_route(request)

        # Si el orden es [poi-tarde, poi-temprano], la llegada al 2do es > 15:00 (cerrado)
        # O si se invierte [poi-temprano, poi-tarde], ambos pueden ser atendidos.
        # Probemos con un POI que cierra antes de la hora de inicio:
        poi_imposible = PoiOptimizationItem(
            poi_id="poi-imposible",
            nombre="Cerrado temprano",
            latitud=-32.8900,
            longitud=-68.8400,
            duracion_estimada=60,
            horarios=[
                HorarioOptimizationItem(
                    dia_semana_desde=0,
                    hora_desde="07:00",
                    dia_semana_hasta=6,
                    hora_hasta="08:30",  # Cierra a las 08:30 y el viaje empieza a las 14:00
                )
            ],
        )
        request2 = RouteOptimizationRequest(
            pois=[pois[0], poi_imposible],
            fecha="2026-09-10",
            hora_inicio_offset=840,  # 14:00
            modo_viaje="auto",
        )
        response2 = self.service.optimize_route(request2)

        self.assertEqual(response2.status, "conflicto_horario")
        self.assertGreater(len(response2.conflictos), 0)
        conflicto = next((c for c in response2.conflictos if c.poi_id == "poi-imposible"), None)
        self.assertIsNotNone(conflicto)
        self.assertIn("08:30", conflicto.hora_cierre)
        self.assertIsNotNone(conflicto.alternativa_horario)

    def test_http_endpoint_success(self):
        """Verifica la respuesta HTTP del endpoint POST /optimization/route."""
        payload = {
            "pois": [
                {
                    "poi_id": "poi-a",
                    "nombre": "Punto A",
                    "latitud": -32.8895,
                    "longitud": -68.8458,
                    "duracion_estimada": 45,
                },
                {
                    "poi_id": "poi-b",
                    "nombre": "Punto B",
                    "latitud": -32.8950,
                    "longitud": -68.8500,
                    "duracion_estimada": 60,
                },
            ],
            "fecha": "2026-09-15",
            "hora_inicio_offset": 540,
            "modo_viaje": "auto",
        }
        res = self.client.post("/optimization/route", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("status", data)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(len(data["orden_optimizado"]), 2)
        self.assertEqual(len(data["paradas"]), 2)

    def test_http_endpoint_validation_error(self):
        """Verifica que enviar menos de 2 POIs retorne error 422 de validación Pydantic."""
        payload = {
            "pois": [
                {
                    "poi_id": "poi-single",
                    "nombre": "Solo uno",
                    "latitud": -32.8895,
                    "longitud": -68.8458,
                }
            ]
        }
        res = self.client.post("/optimization/route", json=payload)
        self.assertEqual(res.status_code, 422)


if __name__ == "__main__":
    unittest.main()
