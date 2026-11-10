"""
AI Review Summary Service (US-RYV-06).
Analyzes reviews for a POI and generates a concise, structured natural language summary
highlighting positive points, areas of improvement, and recurrent topics.
"""
import re
import json
from typing import Optional, List, Dict, Any
import httpx
from app.core.config import settings
from app.schemas.reviews_summary import (
    ReviewSummaryRequest,
    ReviewSummaryResponse,
    ReviewItemPayload,
)

SYSTEM_PROMPT = """Eres el analista de opiniones turísticas de la plataforma 'Ando' (Mendoza, Argentina).
Tu misión es procesar un conjunto de reseñas reales de un Punto de Interés (POI) y redactar un resumen objetivo, breve y útil en español neutro.

DIRECTIVAS ESTRICTAS:
1. Síntesis General (resumen): Redacta un párrafo breve (máximo 2 a 3 oraciones) que capture la opinión global y la experiencia del visitante.
2. Puntos Positivos (puntos_positivos): Lista de 2 a 4 aspectos positivos o fortalezas recurrentes (ej: "Excelente atención y calidez del personal", "Vistas panorámicas hacia la cordillera").
3. Puntos Negativos / A mejorar (puntos_negativos): Lista de 1 a 3 críticas o puntos a considerar mencionados (ej: "Demoras en el servicio en días concurridos", "Precios elevados en carta"). Si no hay críticas relevantes en las reseñas, devuelve una lista vacía.
4. Temas Clave (temas_recurrentes): Lista de 2 a 4 tópicos clave (ej: ["Atención", "Degustación", "Paisajes", "Precios"]).
5. Moderación y Seguridad: NUNCA incluyas insultos, acusaciones personales, lenguaje vulgar ni datos privados. Mantén un tono formal, profesional y constructivo.
6. Foco en la Veracidad: Basa el resumen EXCLUSIVAMENTE en las reseñas proporcionadas. No inventes características, platos ni servicios no mencionados.

Responde ÚNICAMENTE un objeto JSON válido con la siguiente estructura:
{
  "resumen": "string",
  "puntos_positivos": ["string"],
  "puntos_negativos": ["string"],
  "temas_recurrentes": ["string"]
}
"""


class ReviewSummaryService:
    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        llm_model: Optional[str] = None,
        timeout_seconds: float = 15.0,
    ):
        self.gemini_api_key = gemini_api_key if gemini_api_key is not None else settings.gemini_api_key
        self.openai_api_key = openai_api_key if openai_api_key is not None else settings.openai_api_key
        self.groq_api_key = groq_api_key if groq_api_key is not None else settings.groq_api_key
        self.llm_model = llm_model or settings.llm_model or "gemini-3.5-flash"
        self.timeout_seconds = timeout_seconds

    def generate_summary(self, request: ReviewSummaryRequest) -> ReviewSummaryResponse:
        """
        Genera el resumen estructurado de reseñas.
        Intenta primero con LLM (Gemini/OpenAI) y degrada de forma resiliente
        hacia un motor heurístico determinístico.
        """
        total = len(request.reviews)
        if total == 0:
            return ReviewSummaryResponse(
                poi_id=request.poi_id,
                resumen="No hay reseñas disponibles para generar un resumen.",
                puntos_positivos=[],
                puntos_negativos=[],
                temas_recurrentes=[],
                total_resenas=0,
                puntuacion_promedio=0.0,
                tokens_used=0,
                model_used="none",
            )

        avg_score = round(sum(r.puntuacion for r in request.reviews) / total, 2)

        # 1. Intentar con Groq si está configurado (Ultra rápido, soporte JSON estructurado y gratuito)
        if self.groq_api_key and settings.llm_provider in ["groq", "auto", "gemini"]:
            try:
                res = self._call_groq_api(request, avg_score)
                if res:
                    return res
            except Exception:
                pass

        # 2. Intentar con Gemini
        if self.gemini_api_key:
            try:
                res = self._call_gemini_api(request, avg_score)
                if res:
                    return res
            except Exception:
                pass

        # 2. Intentar con OpenAI si está configurado
        if self.openai_api_key and settings.llm_provider == "openai":
            try:
                res = self._call_openai_api(request, avg_score)
                if res:
                    return res
            except Exception:
                pass

        # 3. Fallback heurístico determinístico (0 tokens, robusto y rápido)
        return self._build_deterministic_summary(request, avg_score)

    def _format_reviews_context(self, request: ReviewSummaryRequest) -> str:
        lines = [
            f"POI: {request.poi_nombre}",
            f"Categorías: {', '.join(request.categorias) if request.categorias else 'Turismo general'}",
            f"Total de reseñas: {len(request.reviews)}",
            "RESEÑAS DISPONIBLES:",
        ]
        for idx, r in enumerate(request.reviews, 1):
            comment = r.comentario.strip() if r.comentario else "(Solo calificación de estrellas)"
            lines.append(f"- Reseña {idx} [{r.puntuacion}★]: {comment}")
        return "\n".join(lines)

    def _call_gemini_api(self, request: ReviewSummaryRequest, avg_score: float) -> Optional[ReviewSummaryResponse]:
        context = self._format_reviews_context(request)
        user_message = f"Analiza las siguientes reseñas y genera el JSON:\n\"\"\"\n{context}\n\"\"\""
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": SYSTEM_PROMPT},
                        {"text": user_message},
                    ]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1,
            },
        }

        candidate_models = [m for m in [
            self.llm_model,
            "gemini-3.8-flash",
            "gemini-3-flash-preview",
            "gemini-3.1-flash-lite-preview",
            "gemini-flash-latest",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
        ] if m and m.startswith("gemini")]
        # Eliminar duplicados preservando orden
        seen = set()
        models_to_try = [m for m in candidate_models if not (m in seen or seen.add(m))]

        with httpx.Client(timeout=self.timeout_seconds) as client:
            for model_name in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.gemini_api_key}"
                try:
                    resp = client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_text = (
                            data.get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [{}])[0]
                            .get("text", "")
                        )
                        tokens_used = data.get("usageMetadata", {}).get("totalTokenCount", 0)
                        if raw_text:
                            parsed = self._extract_json(raw_text)
                            if parsed and "resumen" in parsed:
                                return ReviewSummaryResponse(
                                    poi_id=request.poi_id,
                                    resumen=str(parsed.get("resumen", "")).strip(),
                                    puntos_positivos=list(parsed.get("puntos_positivos") or []),
                                    puntos_negativos=list(parsed.get("puntos_negativos") or []),
                                    temas_recurrentes=list(parsed.get("temas_recurrentes") or []),
                                    total_resenas=len(request.reviews),
                                    puntuacion_promedio=avg_score,
                                    tokens_used=tokens_used,
                                    model_used=model_name,
                                )
                except Exception:
                    continue
        return None

    def _call_openai_api(self, request: ReviewSummaryRequest, avg_score: float) -> Optional[ReviewSummaryResponse]:
        context = self._format_reviews_context(request)
        url = "https://api.openai.com/v1/chat/completions"

        body = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Analiza las siguientes reseñas y genera el JSON:\n\n{context}"},
            ],
            "temperature": 0.2,
            "max_tokens": 600,
            "response_format": {"type": "json_object"},
        }

        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self.timeout_seconds) as client:
            resp = client.post(url, json=body, headers=headers)
            if resp.status_code != 200:
                return None
            data = resp.json()

            choices = data.get("choices", [])
            if not choices:
                return None

            raw_json = choices[0].get("message", {}).get("content", "")
            tokens_used = data.get("usage", {}).get("total_tokens", 0)

            parsed = self._extract_json(raw_json)
            if not parsed or "resumen" not in parsed:
                return None

            return ReviewSummaryResponse(
                poi_id=request.poi_id,
                resumen=parsed.get("resumen", "").strip(),
                puntos_positivos=parsed.get("puntos_positivos", []) or [],
                puntos_negativos=parsed.get("puntos_negativos", []) or [],
                temas_recurrentes=parsed.get("temas_recurrentes", []) or [],
                total_resenas=len(request.reviews),
                puntuacion_promedio=avg_score,
                tokens_used=tokens_used,
                model_used="openai-gpt-4o-mini",
            )

    def _call_groq_api(self, request: ReviewSummaryRequest, avg_score: float) -> Optional[ReviewSummaryResponse]:
        context = self._format_reviews_context(request)
        url = f"{settings.groq_api_base}/chat/completions"
        models_to_try = [
            getattr(settings, "groq_chat_model", "openai/gpt-oss-120b"),
            "openai/gpt-oss-20b",
        ]
        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self.timeout_seconds) as client:
            for model_name in models_to_try:
                body = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Analiza las siguientes reseñas y genera el JSON:\n\n{context}"},
                    ],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                }
                try:
                    resp = client.post(url, json=body, headers=headers)
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        continue
                    raw_json = choices[0].get("message", {}).get("content", "")
                    tokens_used = data.get("usage", {}).get("total_tokens", 0)

                    parsed = self._extract_json(raw_json)
                    if not parsed or "resumen" not in parsed:
                        continue

                    return ReviewSummaryResponse(
                        poi_id=request.poi_id,
                        resumen=parsed.get("resumen", "").strip(),
                        puntos_positivos=parsed.get("puntos_positivos", []) or [],
                        puntos_negativos=parsed.get("puntos_negativos", []) or [],
                        temas_recurrentes=parsed.get("temas_recurrentes", []) or [],
                        total_resenas=len(request.reviews),
                        puntuacion_promedio=avg_score,
                        tokens_used=tokens_used,
                        model_used=f"groq/{model_name}",
                    )
                except Exception:
                    continue
        return None

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(text.strip())
        except Exception:
            pass

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
        return None

    def _build_deterministic_summary(
        self, request: ReviewSummaryRequest, avg_score: float
    ) -> ReviewSummaryResponse:
        """
        Generador heurístico determinístico cuando no hay conexión LLM disponible.
        Extrae aspectos clave basados en calificaciones, polaridad y patrones en los textos.
        """
        total = len(request.reviews)
        comments = [r.comentario.strip() for r in request.reviews if r.comentario and len(r.comentario.strip()) > 2]
        all_text = " ".join(comments).lower()

        # Detección de tópicos frecuentes
        temas = []
        if any(w in all_text for w in ["atencion", "atención", "personal", "guia", "guía", "amable", "mozo", "servicio", "trato"]):
            temas.append("Atención del personal")
        if any(w in all_text for w in ["vino", "bodega", "degustacion", "degustación", "copa", "maridaje"]):
            temas.append("Vinos y Degustación")
        if any(w in all_text for w in ["comida", "plato", "almuerzo", "cena", "postre", "carta", "sabor", "rico", "porciones"]):
            temas.append("Gastronomía")
        if any(w in all_text for w in ["vista", "paisaje", "montaña", "cordillera", "jardin", "jardín", "foto"]):
            temas.append("Paisajes y Vistas")
        if any(w in all_text for w in ["precio", "costo", "caro", "barato", "accesible", "economico", "económico"]):
            temas.append("Relación Precio/Calidad")
        if any(w in all_text for w in ["instalaciones", "limpieza", "lugar", "ambiente", "espacio", "estacionamiento", "ruido", "baño"]):
            temas.append("Ambiente e Instalaciones")

        if not temas and request.categorias:
            temas = request.categorias[:3]
        elif not temas:
            temas = ["Experiencia general", "Atención"]

        # Puntos positivos
        positivos: List[str] = []
        high_ratings = [r for r in request.reviews if r.puntuacion >= 4.0]
        if len(high_ratings) >= 3 or avg_score >= 4.0:
            positivos.append(f"Valoración favorable por parte de la mayoría de los visitantes (promedio {avg_score}★).")
        if any(w in all_text for w in ["excelente atencion", "muy amable", "gran atencion", "muy atentos", "cordial", "buena atencion", "buen trato"]):
            positivos.append("Destacan la amabilidad y predisposición del personal.")
        if any(w in all_text for w in ["hermosa vista", "vistas increibles", "paisaje hermoso", "lugar increible", "lindo lugar", "ambiente calido"]):
            positivos.append("Elogian las vistas panorámicas y el entorno.")
        if any(w in all_text for w in ["vino excelente", "ricos vinos", "comida exquisita", "muy rico", "platos excelentes", "sabores"]):
            positivos.append("Muy buena valoración de la oferta gastronómica y bebidas.")

        if not positivos and avg_score >= 3.0:
            positivos.append("Se aprecian aspectos generales de la visita.")

        # Puntos negativos / áreas de mejora
        negativos: List[str] = []
        low_rating_reviews = [r for r in request.reviews if r.puntuacion <= 3.0]
        
        if any(w in all_text for w in ["demora", "tardo", "tardaron", "espera", "lento", "esperar mucho", "tardanza", "demorado"]):
            negativos.append("Se señalan demoras en los tiempos de atención o en la entrega de pedidos.")
        if any(w in all_text for w in ["mala atencion", "pesima atencion", "pésima atención", "poco amable", "desagradable", "mala experiencia", "mal servicio", "no lo recomiendo", "mala atención"]):
            negativos.append("Críticas sobre inconsistencias en la atención y calidad del servicio.")
        if any(w in all_text for w in ["caro", "precio elevado", "costoso", "muy caro", "excesivo", "no vale el precio"]):
            negativos.append("Algunos visitantes consideran que los precios son elevados en relación a lo ofrecido.")
        if any(w in all_text for w in ["frio", "frío", "mala comida", "poco sabor", "porciones chicas", "comida regular", "sin sabor"]):
            negativos.append("Observaciones sobre la preparación de platos o tamaño de las porciones.")
        if any(w in all_text for w in ["ruido", "ruidoso", "sucio", "suciedad", "baños", "descuidado", "sin mantenimiento"]):
            negativos.append("Menciones a aspectos de ambientación, ruidos o mantenimiento del espacio.")
        if any(w in all_text for w in ["reserva", "sin lugar", "lleno", "imposible entrar"]):
            negativos.append("Se sugiere reservar con anticipación para evitar inconvenientes de cupo.")

        # Si hay reseñas con baja puntuación (<= 3 estrellas) y no se detectó texto específico:
        if len(low_rating_reviews) >= 1 and not negativos:
            negativos.append(f"Existen opiniones con valoraciones bajas ({len(low_rating_reviews)} de {total}) que señalan oportunidades de mejora en la experiencia global.")

        # Síntesis general
        if avg_score >= 4.5:
            resumen = f"Los turistas expresan una experiencia altamente satisfactoria en {request.poi_nombre}, destacando principalmente {temas[0].lower()} y la ambientación general."
        elif avg_score >= 3.8:
            resumen = f"Los visitantes valoran positivamente su paso por {request.poi_nombre}, con buenas opiniones en {temas[0].lower()} y algunas sugerencias de mejora."
        else:
            resumen = f"Las opiniones sobre {request.poi_nombre} presentan balances diversos entre sus visitantes, con aspectos valorados en {temas[0].lower()} junto a observaciones sobre el servicio y la experiencia."

        return ReviewSummaryResponse(
            poi_id=request.poi_id,
            resumen=resumen,
            puntos_positivos=positivos[:3],
            puntos_negativos=negativos[:3],
            temas_recurrentes=temas[:4],
            total_resenas=total,
            puntuacion_promedio=avg_score,
            tokens_used=0,
            model_used="deterministic-heuristics",
        )
