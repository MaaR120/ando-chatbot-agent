"""
Planificación de itinerarios con LLM (US-GDI-02 / US-GDI-04).

El modelo recibe los parámetros del viaje y los POIs reales disponibles, y devuelve qué
lugares visitar cada día. Acá no hay planificación por reglas de respaldo: si ningún
proveedor de LLM responde a tiempo se lanza LlmUnavailableError y el backend informa
el error al usuario, tal como pide la US.

El orden de las paradas dentro de cada día y los horarios los resuelve después el
optimizador de rutas (OR-Tools); el modelo solo decide qué va en cada día.
"""
import json
import os
import re
from typing import Dict, List, Optional, Set, Tuple

import httpx

from app.core.config import settings
from app.schemas.itinerary_plan import (
    ItineraryPlanRequest,
    ItineraryPlanResponse,
    PlanCandidatePoi,
    PlannedDay,
)

# Tiempo máximo para la respuesta del modelo de lenguaje
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "25.0"))

SYSTEM_PROMPT = """Sos el planificador de viajes de 'Ando', una app de turismo en Mendoza, Argentina.
Tu tarea es decidir qué LUGARES visitar cada día del viaje usando sus números de ID entre corchetes.

REGLAS OBLIGATORIAS:
1. Usá ÚNICAMENTE los números de ID entre corchetes de la lista de LUGARES (ej. 1, 2, 3). Nunca inventes números ni uses nombres ni UUIDs.
2. Cada lugar puede aparecer como máximo una vez en todo el viaje.
3. La suma de las duraciones de un día, más unos 30 minutos de traslado entre paradas, no puede superar los minutos disponibles por día.
4. Agrupá en el mismo día lugares del mismo Polo o zona cercana para minimizar los tiempos de viaje.
5. Respetá "Abre: Días ...": un lugar solo puede ir en un día en el que abre.
6. Armá días variados con actividades coherentes con sus horarios de atención, e incluí lugares gastronómicos para almorzar o cenar cuando haya opciones.
7. Tené en cuenta los intereses, el tipo de viaje, la cantidad de personas, el presupuesto y las preferencias del usuario.

FORMATO DE RESPUESTA: únicamente un objeto JSON con esta estructura exacta:
{"dias": [{"dia": 1, "poi_ids": [1, 2]}, {"dia": 2, "poi_ids": [3, 4]}]}
- En modo seleccionar NO incluyas sobrantes.
- En modo organizar podés incluir "sobrantes": [5, 6] cerrando 'dias' con ']' primero:
{"dias": [{"dia": 1, "poi_ids": [1, 2]}], "sobrantes": [3, 4]}
- NO agregues explicaciones, markdown fuera del json ni campos adicionales.
"""


def _assign_polos(candidatos: List[PlanCandidatePoi]) -> Dict[str, str]:
    """
    Asigna una etiqueta de polo geográfico a cada candidato.
    Prioriza c.zona (ej. 'Luján de Cuyo', 'Maipú', 'Capital').
    Si no tiene zona, agrupa por cuadrícula de coordenadas (~10 km) en 'Polo A', 'Polo B', etc.
    """
    polos: Dict[str, str] = {}
    missing_geo = []
    for c in candidatos:
        if c.zona and c.zona.strip():
            polos[c.poi_id] = c.zona.strip()
        else:
            missing_geo.append(c)

    if missing_geo:
        grid_map: Dict[Tuple[float, float], str] = {}
        for c in missing_geo:
            grid_key = (round(c.latitud, 1), round(c.longitud, 1))
            if grid_key not in grid_map:
                grid_map[grid_key] = f"Polo {chr(65 + (len(grid_map) % 26))}"
            polos[c.poi_id] = grid_map[grid_key]

    return polos

MODE_INSTRUCTIONS = {
    "seleccionar": (
        "MODO: armar un viaje nuevo. Elegí los lugares que mejor se ajusten al viajero; no hace falta usar "
        "todos. Cada día debería tener entre 2 y 5 paradas según cuánto dure cada una."
    ),
    "organizar": (
        "MODO: organizar lugares que el viajero ya eligió. Ubicá la mayor cantidad posible respetando las "
        "reglas. Los que no entren por tiempo u horario van en \"sobrantes\"."
    ),
}


class LlmUnavailableError(Exception):
    """Ningún proveedor de LLM devolvió un plan válido a tiempo."""


class ItineraryPlannerService:
    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        timeout_seconds: float = LLM_TIMEOUT_SECONDS,
    ):
        self.gemini_api_key = gemini_api_key if gemini_api_key is not None else settings.gemini_api_key
        self.openai_api_key = openai_api_key if openai_api_key is not None else settings.openai_api_key
        self.groq_api_key = groq_api_key if groq_api_key is not None else settings.groq_api_key
        self.timeout_seconds = timeout_seconds

    # ------------------------------------------------------------------ API pública

    def plan(self, request: ItineraryPlanRequest) -> ItineraryPlanResponse:
        import logging
        logger = logging.getLogger("uvicorn.error")

        user_prompt = self._build_user_prompt(request)

        def _invoke_groq(p: str):
            try:
                return self._call_groq(p, request)
            except TypeError:
                return self._call_groq(p)
        _invoke_groq.__name__ = "_call_groq"

        attempts = []
        if self.groq_api_key and settings.llm_provider in ["groq", "auto", "gemini"]:
            attempts.append(_invoke_groq)
        if self.gemini_api_key:
            attempts.append(self._call_gemini)
        if self.openai_api_key:
            attempts.append(self._call_openai)

        if not attempts:
            raise LlmUnavailableError(
                "No hay ningún proveedor de LLM configurado (GROQ_API_KEY, GEMINI_API_KEY u OPENAI_API_KEY)."
            )

        logger.info(f"[ItineraryPlanner] Iniciando planificación con {len(request.candidatos)} candidatos para {len(request.dias)} días.")
        last_error = "sin respuesta"
        for attempt in attempts:
            provider_name = attempt.__name__
            try:
                result = attempt(user_prompt)
            except httpx.TimeoutException:
                logger.warning(f"[ItineraryPlanner] {provider_name} tardó más de {self.timeout_seconds}s (Timeout).")
                last_error = f"el modelo tardó más de {int(self.timeout_seconds)} segundos"
                continue
            except Exception as exc:
                logger.warning(f"[ItineraryPlanner] {provider_name} falló con error: {exc}")
                last_error = str(exc)
                continue
            if not result:
                logger.warning(f"[ItineraryPlanner] {provider_name} no devolvió respuesta.")
                last_error = "el proveedor devolvió un error"
                continue

            raw_text, tokens, model = result
            logger.info(f"[ItineraryPlanner] {model} devolvió respuesta ({tokens} tokens). Validando plan...")
            plan = self._parse_and_validate(raw_text, request)
            if plan is None:
                logger.warning(f"[ItineraryPlanner] {model} devolvió un plan que no superó la validación. Texto: {raw_text[:300]}")
                last_error = "el modelo devolvió un plan inválido"
                continue
            plan.tokens_used = tokens
            plan.model_used = model
            logger.info(f"[ItineraryPlanner] Plan generado con éxito mediante {model} ({sum(len(d.poi_ids) for d in plan.dias)} lugares asignados).")
            return plan

        raise LlmUnavailableError(f"El modelo no devolvió un plan utilizable: {last_error}.")

    # ------------------------------------------------------------------ prompt

    def _build_user_prompt(self, request: ItineraryPlanRequest) -> str:
        dias_info = [f"Día {d.dia} ({d.dia_semana} {d.fecha})" for d in request.dias]
        viaje_lines = [
            f"- Días de viaje: {len(request.dias)} [{', '.join(dias_info)}]",
            f"- Minutos disponibles por día: {request.minutos_por_dia}",
        ]
        if request.tipo_viaje:
            viaje_lines.append(f"- Tipo de viaje: {request.tipo_viaje}")
        if request.cantidad_personas:
            viaje_lines.append(f"- Personas: {request.cantidad_personas}")
        if request.presupuesto_diario:
            viaje_lines.append(f"- Presupuesto diario: {request.presupuesto_diario} ARS")
        if request.intereses:
            viaje_lines.append(f"- Intereses: {', '.join(request.intereses)}")
        if request.descripcion_libre:
            viaje_lines.append(f"- Preferencias: {request.descripcion_libre.strip()}")
        if request.modo_transporte:
            viaje_lines.append(f"- Transporte: {request.modo_transporte}")

        polos = _assign_polos(request.candidatos)
        candidatos_lines = []
        for idx, c in enumerate(request.candidatos, 1):
            polo = polos.get(c.poi_id, "General")
            cat = c.categoria or "Lugar"
            dur = f"{c.duracion_minutos}min"
            horario_str = f"Horario: {c.horario}" if c.horario else "Horario: flexible"
            if c.dias_abierto:
                dias_str = f"Abre: Días {', '.join(str(d) for d in c.dias_abierto)}"
            else:
                dias_str = "Abre: Todos los días"

            cand_line = f"[{idx}] {c.nombre} | {cat} | Polo: {polo} | {dur} | {horario_str} | {dias_str}"
            if c.descripcion and c.descripcion.strip():
                desc = c.descripcion.strip()
                if len(desc) > 160:
                    desc = desc[:157] + "..."
                candidatos_lines.append(f"{cand_line}\n  Desc: {desc}")
            else:
                candidatos_lines.append(cand_line)

        return (
            f"{MODE_INSTRUCTIONS[request.modo]}\n\n"
            f"DATOS DEL VIAJE:\n" + "\n".join(viaje_lines) + "\n\n"
            f"LUGARES DISPONIBLES:\n" + "\n".join(candidatos_lines)
        )

    # ------------------------------------------------------------------ validación

    def _parse_and_validate(
        self, raw_text: str, request: ItineraryPlanRequest
    ) -> Optional[ItineraryPlanResponse]:
        """Descarta todo lo que no respete los datos reales: ids inventados, repetidos o días inexistentes."""
        import logging
        logger = logging.getLogger("uvicorn.error")

        cleaned = (raw_text or "").strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        # Reparación común en LLMs: olvidar cerrar el corchete ']' de 'dias' antes de '"sobrantes"' o '"resumen"'
        if '"sobrantes"' in cleaned and re.search(r'\}\s*,\s*"sobrantes"', cleaned):
            cleaned = re.sub(r'\}\s*,\s*"sobrantes"', r'}], "sobrantes"', cleaned)
        if '"resumen"' in cleaned and re.search(r'\}\s*,\s*"resumen"', cleaned):
            cleaned = re.sub(r'\}\s*,\s*"resumen"', r'}], "resumen"', cleaned)
        if cleaned.count("{") > cleaned.count("}"):
            cleaned += "}" * (cleaned.count("{") - cleaned.count("}"))
        if cleaned.count("[") > cleaned.count("]"):
            cleaned = cleaned.rstrip("}") + ("]" * (cleaned.count("[") - cleaned.count("]"))) + "}"

        try:
            parsed = json.loads(cleaned)
        except (TypeError, ValueError) as exc:
            logger.warning(f"[ItineraryPlanner] Error al deserializar JSON: {exc}. Contenido: {cleaned[:200]}")
            return None
        if not isinstance(parsed, dict) or not isinstance(parsed.get("dias"), list):
            logger.warning(f"[ItineraryPlanner] JSON no contiene el campo 'dias' en formato lista: {parsed}")
            return None

        idx_to_uuid: Dict[int, str] = {i + 1: str(c.poi_id).strip() for i, c in enumerate(request.candidatos)}
        valid_uuids: Set[str] = {str(c.poi_id).strip() for c in request.candidatos}
        name_to_uuid: Dict[str, str] = {
            c.nombre.strip().lower(): str(c.poi_id).strip() for c in request.candidatos if c.nombre
        }
        open_days: Dict[str, Optional[List[int]]] = {str(c.poi_id).strip(): c.dias_abierto for c in request.candidatos}
        valid_days: Set[int] = {d.dia for d in request.dias}

        def resolve_poi_id(raw_val) -> Optional[str]:
            if isinstance(raw_val, int) and raw_val in idx_to_uuid:
                return idx_to_uuid[raw_val]
            s = str(raw_val).strip()
            if s.isdigit():
                num = int(s)
                if num in idx_to_uuid:
                    return idx_to_uuid[num]
            if s in valid_uuids:
                return s
            if s.lower() in name_to_uuid:
                return name_to_uuid[s.lower()]
            return None

        used: Set[str] = set()
        by_day: Dict[int, PlannedDay] = {}

        for entry in parsed["dias"]:
            if not isinstance(entry, dict):
                continue
            try:
                day_number = int(entry.get("dia"))
            except (TypeError, ValueError):
                continue
            if day_number not in valid_days or day_number in by_day:
                continue

            poi_ids: List[str] = []
            for raw_id in entry.get("poi_ids") or []:
                resolved_id = resolve_poi_id(raw_id)
                if not resolved_id or resolved_id in used:
                    continue
                allowed = open_days.get(resolved_id)
                if allowed is not None and day_number not in allowed:
                    continue
                poi_ids.append(resolved_id)
                used.add(resolved_id)

            motivo = entry.get("motivo")
            by_day[day_number] = PlannedDay(
                dia=day_number,
                poi_ids=poi_ids,
                motivo=str(motivo)[:300] if motivo else None,
            )

        if not used:
            logger.warning(f"[ItineraryPlanner] Ningún POI del modelo pudo ser validado (total_candidatos={len(valid_uuids)}).")
            return None

        dias = [by_day.get(d.dia, PlannedDay(dia=d.dia, poi_ids=[])) for d in request.dias]

        sobrantes: List[str] = []
        if request.modo == "organizar":
            raw_sobrantes = parsed.get("sobrantes")
            if isinstance(raw_sobrantes, list):
                for s in raw_sobrantes:
                    res = resolve_poi_id(s)
                    if res and res not in used and res not in sobrantes:
                        sobrantes.append(res)
            for c in request.candidatos:
                if c.poi_id not in used and c.poi_id not in sobrantes:
                    sobrantes.append(c.poi_id)

        resumen = parsed.get("resumen")
        return ItineraryPlanResponse(
            dias=dias,
            sobrantes=sobrantes,
            resumen=str(resumen)[:500] if resumen else None,
        )

    # ------------------------------------------------------------------ proveedores

    def _call_chat_completions(
        self, url: str, api_key: str, model: str, user_prompt: str, is_groq: bool = False
    ) -> Optional[Tuple[str, int]]:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 4000,
        }
        # Para Groq usamos reasoning_effort: low (evita agotar TPM y responde en 1-2s); para OpenAI response_format
        if is_groq:
            payload["reasoning_effort"] = "low"
        else:
            payload["response_format"] = {"type": "json_object"}

        import logging
        logger = logging.getLogger("uvicorn.error")

        logger.info(f"[ItineraryPlanner] Consultando {model} en {url}...")
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(
                    url,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.TimeoutException:
            logger.warning(f"[ItineraryPlanner] Modelo {model} tardó más de {self.timeout_seconds}s (Timeout individual).")
            return None
        except Exception as exc:
            logger.warning(f"[ItineraryPlanner] Modelo {model} falló en petición HTTP: {exc}")
            return None

        if resp.status_code != 200:
            logger.warning(
                f"[ItineraryPlanner] Proveedor {url} (modelo {model}) respondió HTTP {resp.status_code}: {resp.text[:300]}"
            )
            return None
        data = resp.json()
        raw_text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        tokens = data.get("usage", {}).get("total_tokens", 0)
        logger.info(f"[ItineraryPlanner] {model} devolvió respuesta (longitud={len(raw_text)}, tokens={tokens}).")
        return (raw_text, tokens) if raw_text else None

    def _call_groq(
        self, user_prompt: str, request: Optional[ItineraryPlanRequest] = None
    ) -> Optional[Tuple[str, int, str]]:
        models_to_try = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
        import logging
        logger = logging.getLogger("uvicorn.error")

        for model in models_to_try:
            result = self._call_chat_completions(
                f"{settings.groq_api_base}/chat/completions",
                self.groq_api_key,
                model,
                user_prompt,
                is_groq=True,
            )
            if not result:
                continue

            raw_text, tokens = result
            if request is not None and self._parse_and_validate(raw_text, request) is None:
                logger.warning(
                    f"[ItineraryPlanner] {model} devolvió respuesta pero no superó la validación. Probando siguiente modelo de Groq..."
                )
                continue

            return (raw_text, tokens, f"groq/{model}")
        return None

    def _call_openai(self, user_prompt: str) -> Optional[Tuple[str, int, str]]:
        model = "gpt-4o-mini"
        result = self._call_chat_completions(
            "https://api.openai.com/v1/chat/completions", self.openai_api_key, model, user_prompt, is_groq=False
        )
        return (result[0], result[1], model) if result else None

    def _call_gemini(self, user_prompt: str) -> Optional[Tuple[str, int, str]]:
        payload = {
            "contents": [{"parts": [{"text": SYSTEM_PROMPT}, {"text": user_prompt}]}],
            "generationConfig": {"response_mime_type": "application/json", "temperature": 0.4},
        }
        candidate_models = [m for m in [settings.llm_model, "gemini-1.5-flash", "gemini-flash-latest"] if m and m.startswith("gemini")]
        if not candidate_models:
            candidate_models = ["gemini-1.5-flash", "gemini-flash-latest"]
        seen: Set[str] = set()
        models_to_try = [m for m in candidate_models if m and not (m in seen or seen.add(m))]

        with httpx.Client(timeout=self.timeout_seconds) as client:
            for model_name in models_to_try:
                url = (
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model_name}:generateContent?key={self.gemini_api_key}"
                )
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_text = (
                        data.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", "")
                        .strip()
                    )
                    tokens = data.get("usageMetadata", {}).get("totalTokenCount", 0)
                    if raw_text:
                        return raw_text, tokens, model_name
                else:
                    import logging
                    logging.getLogger("uvicorn.error").warning(
                        f"[ItineraryPlanner] Gemini ({model_name}) respondió HTTP {resp.status_code}: {resp.text[:300]}"
                    )
                    if resp.status_code in [401, 402, 403, 429]:
                        break
        return None
