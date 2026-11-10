"""
Route Optimization Service using Google OR-Tools (US-MRIA-05).
Ando Recommendation & Routing Service (MRIA).
"""
import math
from datetime import date
from typing import Dict, List, Optional, Tuple

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from app.schemas.route_optimization import (
    HorarioOptimizationItem,
    OptimizationConflictItem,
    PoiOptimizationItem,
    RouteOptimizationRequest,
    RouteOptimizationResponse,
    StopOptimizationItem,
)


class RouteOptimizationService:
    """
    Servicio de optimización determinística de rutas utilizando Google OR-Tools (TSPTW).
    Minimiza tiempos y distancias de traslado respetando duraciones de visita y horarios comerciales.
    """

    EARTH_RADIUS_METERS = 6371000

    @staticmethod
    def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
        """Calcula la distancia geográfica en metros entre dos coordenadas usando la fórmula de Haversine."""
        if lat1 == lat2 and lon1 == lon2:
            return 0

        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

        return int(round(RouteOptimizationService.EARTH_RADIUS_METERS * c))

    @staticmethod
    def calculate_transfer_minutes(distance_meters: int, travel_mode: str = "auto") -> int:
        """
        Calcula el tiempo estimado de traslado en minutos según la distancia y el modo de viaje.
        Velocidades promedio estimadas en contexto urbano/rutas de Mendoza:
        - auto / moto: ~30 km/h (500 m/min)
        - bicicleta: ~15 km/h (250 m/min)
        - pie: ~5 km/h (83.33 m/min)
        - micro: ~20 km/h (333.33 m/min)
        """
        if distance_meters <= 0:
            return 0

        mode = (travel_mode or "auto").lower()
        if mode in ("moto", "auto"):
            speed_m_per_min = 500.0  # 30 km/h
        elif mode == "bicicleta":
            speed_m_per_min = 250.0  # 15 km/h
        elif mode == "pie":
            speed_m_per_min = 83.33  # 5 km/h
        elif mode == "micro":
            speed_m_per_min = 333.33  # 20 km/h
        else:
            speed_m_per_min = 500.0

        raw_minutes = math.ceil(distance_meters / speed_m_per_min)
        # Mínimo 1 minuto si hay distancia, acotado a máximo 240 minutos
        return min(240, max(1, raw_minutes))

    @staticmethod
    def parse_time_to_minutes(time_str: str) -> Optional[int]:
        """Convierte una cadena HH:mm o HH:mm:ss a minutos desde medianoche."""
        if not time_str or not isinstance(time_str, str):
            return None
        parts = time_str.strip().split(":")
        if len(parts) >= 2:
            try:
                hours = int(parts[0])
                minutes = int(parts[1])
                return hours * 60 + minutes
            except ValueError:
                return None
        return None

    @staticmethod
    def minutes_to_hhmm(minutes: int) -> str:
        """Convierte minutos desde medianoche a formato HH:mm."""
        normalized = minutes % 1440
        h = normalized // 60
        m = normalized % 60
        return f"{h:02d}:{m:02d}"

    @staticmethod
    def get_day_of_week(fecha_str: Optional[str]) -> Optional[int]:
        """
        Obtiene el día de la semana para la fecha dada.
        Retorna: 0 = Domingo, 1 = Lunes, ..., 6 = Sábado (convención Ando / JavaScript Date.getDay()).
        """
        if not fecha_str:
            return None
        try:
            d = date.fromisoformat(fecha_str[:10])
            # date.weekday(): 0=Lunes ... 6=Domingo -> convertir a 0=Domingo ... 6=Sábado
            return (d.weekday() + 1) % 7
        except Exception:
            return None

    def get_poi_time_windows(
        self, poi: PoiOptimizationItem, day_of_week: Optional[int]
    ) -> List[Tuple[int, int, str]]:
        """
        Retorna las ventanas horarias [apertura, cierre, hora_cierre_str] aplicables al POI para el día de la semana.
        Si no hay horarios definidos o no coincide el día, retorna ventana abierta [0, 1440, '23:59'].
        """
        if not poi.horarios or day_of_week is None:
            return [(0, 1440, "23:59")]

        windows = []
        for h in poi.horarios:
            if not h.hora_desde or not h.hora_hasta:
                continue

            # Verificar si el día de la semana coincide
            coincide = False
            if h.dia_semana_desde <= h.dia_semana_hasta:
                coincide = h.dia_semana_desde <= day_of_week <= h.dia_semana_hasta
            else:
                # Cruza el fin de semana (ej: Viernes a Martes)
                coincide = day_of_week >= h.dia_semana_desde or day_of_week <= h.dia_semana_hasta

            if coincide:
                apertura = self.parse_time_to_minutes(h.hora_desde)
                cierre = self.parse_time_to_minutes(h.hora_hasta)
                if apertura is not None and cierre is not None:
                    hora_cierre_str = h.hora_hasta[:5]
                    # Si cierre < apertura, cruza medianoche (ej: 20:00 a 02:00 -> 1200 a 1440+120)
                    if cierre < apertura:
                        cierre += 1440
                    windows.append((apertura, cierre, hora_cierre_str))

        if not windows:
            # Si tiene horarios pero ninguno abre hoy
            return [(0, 1440, "Cerrado hoy")]

        windows.sort(key=lambda w: w[0])
        return windows

    def evaluate_poi_schedule(
        self,
        poi: PoiOptimizationItem,
        day_of_week: Optional[int],
        arrival_minutes: int,
    ) -> Tuple[bool, Optional[str], Optional[str], int]:
        """
        Evalúa si la llegada al POI cumple con los horarios de atención.
        Retorna (fuera_de_horario, hora_cierre, aviso_horario, offset_inicio_visita).
        Si el turista llega antes de que abra, espera hasta la apertura.
        """
        windows = self.get_poi_time_windows(poi, day_of_week)

        # Si no hay restricciones horarias
        if len(windows) == 1 and windows[0][0] == 0 and windows[0][1] == 1440 and windows[0][2] == "23:59":
            return False, None, None, arrival_minutes

        if windows and windows[0][2] == "Cerrado hoy":
            return (
                True,
                "Cerrado",
                "Atención: El lugar se encuentra cerrado en el día seleccionado.",
                arrival_minutes,
            )

        # Buscar si encaja en alguna franja o antes de ella
        for apertura, cierre, hora_cierre_str in windows:
            # Si llega antes de apertura -> espera hasta apertura
            if arrival_minutes < apertura:
                return False, hora_cierre_str, None, apertura

            # Si llega dentro del horario de atención
            if apertura <= arrival_minutes < cierre:
                return False, hora_cierre_str, None, arrival_minutes

        # Si llega después de la última franja de cierre
        ultima_hora_cierre = windows[-1][2]
        return (
            True,
            ultima_hora_cierre,
            f"Atención: Con este orden llegarás fuera del horario de atención del POI (Cierra {ultima_hora_cierre} hs).",
            arrival_minutes,
        )

    def optimize_route(self, request: RouteOptimizationRequest) -> RouteOptimizationResponse:
        """
        Ejecuta la optimización de la ruta según la cantidad de POIs y restricciones de horario.
        """
        pois = request.pois
        n = len(pois)
        if n < 2:
            raise ValueError("Se requieren al menos 2 POIs para optimizar la ruta.")

        day_of_week = self.get_day_of_week(request.fecha)
        start_time_offset = request.hora_inicio_offset if request.hora_inicio_offset is not None else 540
        travel_mode = request.modo_viaje or "auto"

        # Construir matriz de distancias y tiempos de traslado entre todos los POIs
        dist_matrix = [[0] * n for _ in range(n)]
        time_matrix = [[0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i != j:
                    d = self.haversine_distance_meters(
                        pois[i].latitud, pois[i].longitud, pois[j].latitud, pois[j].longitud
                    )
                    t = self.calculate_transfer_minutes(d, travel_mode)
                    dist_matrix[i][j] = d
                    time_matrix[i][j] = t

        # Caso 1: Exactamente 2 POIs (Criterio 4)
        if n == 2:
            optimal_indices = self._solve_2_pois(pois, dist_matrix, time_matrix, day_of_week, start_time_offset)
        # Caso 2: N >= 3 POIs con Google OR-Tools (Criterio 1)
        else:
            optimal_indices = self._solve_ortools_tsp(
                pois, dist_matrix, time_matrix, day_of_week, start_time_offset
            )

        # Construir secuencia de paradas y simular cronograma detallado
        return self._build_optimization_response(
            pois=pois,
            optimal_indices=optimal_indices,
            dist_matrix=dist_matrix,
            time_matrix=time_matrix,
            day_of_week=day_of_week,
            start_time_offset=start_time_offset,
        )

    def _solve_2_pois(
        self,
        pois: List[PoiOptimizationItem],
        dist_matrix: List[List[int]],
        time_matrix: List[List[int]],
        day_of_week: Optional[int],
        start_time_offset: int,
    ) -> List[int]:
        """
        Evalúa determinísticamente las 2 secuencias posibles [0, 1] y [1, 0] para 2 POIs.
        Elige la secuencia factible con menor tiempo total o menor penalidad de horario.
        """
        permutations = [[0, 1], [1, 0]]
        best_perm = permutations[0]
        best_score = float("inf")

        for perm in permutations:
            idx1, idx2 = perm[0], perm[1]
            dur1 = pois[idx1].duracion_estimada or 60
            dur2 = pois[idx2].duracion_estimada or 60
            traslado = time_matrix[idx1][idx2]

            # Parada 1
            fuera1, _, _, inicio1 = self.evaluate_poi_schedule(pois[idx1], day_of_week, start_time_offset)
            salida1 = inicio1 + dur1

            # Parada 2
            llegada2 = salida1 + traslado
            fuera2, _, _, inicio2 = self.evaluate_poi_schedule(pois[idx2], day_of_week, llegada2)
            salida2 = inicio2 + dur2

            # Penalización alta por parada fuera de horario
            conflict_penalty = (10000 if fuera1 else 0) + (10000 if fuera2 else 0)
            total_time = (salida2 - start_time_offset) + conflict_penalty

            if total_time < best_score:
                best_score = total_time
                best_perm = perm

        return best_perm

    def _solve_ortools_tsp(
        self,
        pois: List[PoiOptimizationItem],
        dist_matrix: List[List[int]],
        time_matrix: List[List[int]],
        day_of_week: Optional[int],
        start_time_offset: int,
    ) -> List[int]:
        """
        Resuelve el Open-TSPTW para N >= 3 paradas utilizando Google OR-Tools.
        Utiliza un nodo virtual depot (índice 0) con costo 0 para encontrar la mejor secuencia abierta.
        """
        n = len(pois)
        # Nodos: 0 = Depot virtual, 1..N = POIs (índice i corresponde a pois[i - 1])
        num_nodes = n + 1

        # Matriz de tiempos (num_nodes x num_nodes)
        solver_time_matrix = [[0] * num_nodes for _ in range(num_nodes)]
        for i in range(1, num_nodes):
            for j in range(1, num_nodes):
                if i != j:
                    solver_time_matrix[i][j] = time_matrix[i - 1][j - 1]

        # Service times (duraciones en cada nodo)
        service_times = [0] * num_nodes
        for i in range(1, num_nodes):
            service_times[i] = pois[i - 1].duracion_estimada or 60

        # Ventanas horarias para cada nodo
        time_windows = [(0, 1440)] * num_nodes
        time_windows[0] = (start_time_offset, start_time_offset)
        for i in range(1, num_nodes):
            windows = self.get_poi_time_windows(pois[i - 1], day_of_week)
            if windows:
                # Tomar la ventana más amplia o la primera aplicable
                apertura = min(w[0] for w in windows)
                cierre = max(w[1] for w in windows)
                time_windows[i] = (apertura, cierre)

        # 1. Intentar resolver con OR-Tools y restricciones estrictas de ventanas horarias
        optimal_indices = self._run_ortools_solver(
            num_nodes=num_nodes,
            solver_time_matrix=solver_time_matrix,
            service_times=service_times,
            time_windows=time_windows,
            start_time_offset=start_time_offset,
            strict_windows=True,
        )

        if optimal_indices is not None and len(optimal_indices) == n:
            return optimal_indices

        # 2. Si no hay solución estricta (por horarios incompatibles), resolver relajando ventanas para
        # minimizar distancia/tiempo de traslado global (Criterio 2: identificar conflictos en post-proceso)
        relaxed_windows = [(0, 1440)] * num_nodes
        relaxed_windows[0] = (start_time_offset, start_time_offset)
        optimal_indices = self._run_ortools_solver(
            num_nodes=num_nodes,
            solver_time_matrix=solver_time_matrix,
            service_times=service_times,
            time_windows=relaxed_windows,
            start_time_offset=start_time_offset,
            strict_windows=False,
        )

        if optimal_indices is not None and len(optimal_indices) == n:
            return optimal_indices

        # Fallback de orden secuencial original si el solver no encuentra solución
        return list(range(n))

    def _run_ortools_solver(
        self,
        num_nodes: int,
        solver_time_matrix: List[List[int]],
        service_times: List[int],
        time_windows: List[Tuple[int, int]],
        start_time_offset: int,
        strict_windows: bool = True,
    ) -> Optional[List[int]]:
        """Invoca el solver de Google OR-Tools para TSP con dimensión temporal."""
        try:
            manager = pywrapcp.RoutingIndexManager(num_nodes, 1, 0)
            routing = pywrapcp.RoutingModel(manager)

            def time_callback(from_index: int, to_index: int) -> int:
                from_node = manager.IndexToNode(from_index)
                to_node = manager.IndexToNode(to_index)
                return solver_time_matrix[from_node][to_node] + service_times[from_node]

            transit_callback_index = routing.RegisterTransitCallback(time_callback)
            routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

            # Dimensión temporal
            time_dimension_name = "Time"
            routing.AddDimension(
                transit_callback_index,
                1440,  # Slack max (permite esperar antes de la apertura)
                1440,  # Capacidad máxima del día
                False,  # No forzar inicio a 0 (utiliza start_time_offset)
                time_dimension_name,
            )
            time_dimension = routing.GetDimensionOrDie(time_dimension_name)

            # Establecer ventanas de tiempo
            for node_idx, (start, end) in enumerate(time_windows):
                index = manager.NodeToIndex(node_idx)
                if index != -1:
                    time_dimension.CumulVar(index).SetRange(start, end)

            # Parámetros de búsqueda
            search_parameters = pywrapcp.DefaultRoutingSearchParameters()
            search_parameters.first_solution_strategy = (
                routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
            )
            search_parameters.local_search_metaheuristic = (
                routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
            )
            search_parameters.time_limit.seconds = 2

            solution = routing.SolveWithParameters(search_parameters)

            if solution:
                index = routing.Start(0)
                visited_nodes = []
                while not routing.IsEnd(index):
                    node = manager.IndexToNode(index)
                    if node != 0:  # Ignorar el depot virtual
                        visited_nodes.append(node - 1)  # Convertir a índice de POI (0-based)
                    index = solution.Value(routing.NextVar(index))

                if len(visited_nodes) == num_nodes - 1:
                    return visited_nodes

            return None
        except Exception:
            return None

    def _build_optimization_response(
        self,
        pois: List[PoiOptimizationItem],
        optimal_indices: List[int],
        dist_matrix: List[List[int]],
        time_matrix: List[List[int]],
        day_of_week: Optional[int],
        start_time_offset: int,
    ) -> RouteOptimizationResponse:
        """
        Construye la respuesta estructurada calculando la cascada cronológica de paradas,
        tiempos de traslado, detección de conflictos de horario y totales del día.
        """
        paradas: List[StopOptimizationItem] = []
        conflictos: List[OptimizationConflictItem] = []
        orden_optimizado = [pois[idx].poi_id for idx in optimal_indices]

        current_time = start_time_offset
        total_distance = 0

        for seq_pos, poi_idx in enumerate(optimal_indices):
            poi = pois[poi_idx]
            duracion = poi.duracion_estimada or 60

            # Evaluar horario comercial para la llegada estimada
            fuera_de_horario, hora_cierre, aviso_horario, inicio_visita = self.evaluate_poi_schedule(
                poi=poi, day_of_week=day_of_week, arrival_minutes=current_time
            )

            hora_llegada_str = self.minutes_to_hhmm(current_time)
            offset_hora_inicio = inicio_visita
            current_time = offset_hora_inicio + duracion

            tiempo_traslado_siguiente = None
            distancia_traslado_metros = None

            if seq_pos < len(optimal_indices) - 1:
                next_poi_idx = optimal_indices[seq_pos + 1]
                distancia_traslado_metros = dist_matrix[poi_idx][next_poi_idx]
                tiempo_traslado_siguiente = time_matrix[poi_idx][next_poi_idx]
                total_distance += distancia_traslado_metros
                current_time += tiempo_traslado_siguiente

            if fuera_de_horario:
                conflictos.append(
                    OptimizationConflictItem(
                        poi_id=poi.poi_id,
                        nombre=poi.nombre,
                        hora_llegada=hora_llegada_str,
                        hora_cierre=hora_cierre,
                        mensaje=aviso_horario or f"El lugar cierra a las {hora_cierre} hs.",
                        alternativa_horario=(
                            f"Planificar la visita entre sus horarios de apertura o en otro día."
                            if hora_cierre
                            else None
                        ),
                    )
                )

            paradas.append(
                StopOptimizationItem(
                    poi_id=poi.poi_id,
                    nombre=poi.nombre,
                    orden_secuencia=seq_pos + 1,
                    offset_hora_inicio=offset_hora_inicio,
                    hora_estimada_llegada=hora_llegada_str,
                    duracion_estimada=duracion,
                    tiempo_traslado_siguiente=tiempo_traslado_siguiente,
                    distancia_traslado_metros=distancia_traslado_metros,
                    fuera_de_horario=fuera_de_horario,
                    aviso_horario=aviso_horario,
                    hora_cierre=hora_cierre,
                )
            )

        total_time_minutes = current_time - start_time_offset
        has_conflicts = len(conflictos) > 0
        status = "conflicto_horario" if has_conflicts else "ok"
        message = (
            f"Se detectaron {len(conflictos)} conflictos de horario comercial."
            if has_conflicts
            else "Optimización de ruta completada exitosamente."
        )

        return RouteOptimizationResponse(
            status=status,
            orden_optimizado=orden_optimizado,
            paradas=paradas,
            distancia_total_metros=total_distance,
            tiempo_total_minutos=total_time_minutes,
            conflictos=conflictos,
            used_fallback=False,
            message=message,
        )
