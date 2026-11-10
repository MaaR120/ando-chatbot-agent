"""
AI Assistant Chat Service (US-ACIA-01 / US-ACIA-02).
Generates conversational tourist recommendations with real POIs from database.
Optimized for minimum token usage and maximum resilience.
"""
import re
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import httpx
from app.core.config import settings
from app.schemas.assistant import (
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantExtractRequest,
    AssistantExtractResponse,
    ChatMessageItem,
)

SYSTEM_PROMPT = """Eres el asistente turístico oficial de 'Ando', la plataforma de turismo de Mendoza, Argentina.
Tu misión es guiar al turista por Mendoza y sus atractivos de manera cálida, clara y concisa.

DIRECTIVAS ESTRICTAS:
1. Dominio exclusivo: Solo responde sobre turismo, gastronomía, bodegas, alojamiento, actividades y transporte en Mendoza o sobre el uso de la plataforma Ando.
- Una consulta está DENTRO del dominio si pide lugares, actividades, comida, alojamiento, transporte o planes en Mendoza, aunque mencione un tema como fútbol, música o cine (ej: "dónde ver un partido mientras como algo", "dónde escuchar música en vivo"). En ese caso responde normalmente recomendando lugares reales, SIN mensaje de rechazo.
- Solo si la consulta es un dato o tarea ajena al turismo y no pide ningún lugar ni plan en Mendoza (ej: "quién ganó el mundial 2022", "dame una receta de lasagna", "resuelve esta ecuación"), NO la respondas ni des datos sobre el tema. Responde únicamente, en el idioma del usuario, con este mensaje: "Como asistente oficial de Ando, solo puedo ayudarte con temas de turismo en Mendoza (bodegas, gastronomía, naturaleza, aventura, alojamiento y atractivos provinciales o el uso de la aplicación). ¿En qué te gustaría que te oriente sobre tu viaje a Mendoza?"
- NUNCA combines el mensaje de rechazo con recomendaciones de lugares: o respondes la consulta turística, o rechazas, pero no ambas cosas.
2. POIs Reales y Fidelidad a los Datos: Si se te proporciona una sección 'POIS_REALES_DISPONIBLES_EN_BD', debes basar tus recomendaciones EXCLUSIVAMENTE en esos lugares reales y en la información provista en su Detalle.
- NO inventes comodidades, servicios ni instalaciones que no figuren expresamente en su Detalle (por ejemplo, NO asumas ni inventes que un lugar tiene piscina/pileta, spa o menú gourmet si no figura en los datos).
- PROHIBIDO FORZAR ACTIVIDADES: NO inventes ni justifiques que un lugar permite o se adapta a actividades (como running, trotar, trekking, deportes, etc.) si su Detalle no lo indica expresamente. Si un POI de la lista claramente no coincide con la actividad que busca el usuario (por ejemplo, un local gastronómico cuando busca salir a correr), DESCÁRTALO por completo y no lo menciones.
- Vocabulario y modismos locales de Argentina: En bares o locales nocturnos de Mendoza, la palabra 'pool' hace referencia a mesas de billar (juego de pool americano), NUNCA a una piscina o natatorio.
3. Lenguaje Natural y sin Enlaces Técnicos: Menciona los lugares en lenguaje natural fluido y agradable. Puedes destacar el nombre en negrita con asteriscos (ej: **Casa Vigil** o **Bodega Norton**) y describir brevemente por qué es una excelente opción. NUNCA incluyas URLs, enlaces Markdown [Nombre](app://...) ni identificadores UUID en tu respuesta de texto; la aplicación mostrará automáticamente las tarjetas interactivas de cada lugar debajo de tu mensaje.
4. Consultas y Modificaciones de Itinerario (US-ACIA-04 / US-GDI-03):
- Si recibes datos en 'DATOS_ITINERARIO_CONSULTADO', informa amablemente el estado actual, el porcentaje de avance, paradas completadas y pendientes, y resalta la próxima parada con hora estimada.
- Si el contexto indica 'DERIVACION_MODIFICACION' o el usuario desea modificar un viaje, explica con entusiasmo las opciones de edición (abrir editor para agregar/quitar paradas, reordenar actividades o ajustar fechas) y proporciona siempre el enlace Markdown al editor [Nombre del Viaje](app://itinerario/UUID).
- Si no tiene itinerarios o la consulta es múltiple/ambigua, guía al turista con las opciones provistas.
5. Criterios Relajados (¡OBLIGATORIO!): Si se incluye una 'NOTA_IMPORTANTE_RELAJACION', es OBLIGATORIO que aclares al usuario que no hubo coincidencias exactas para su pedido y le expliques el motivo de las sugerencias alternativas. Si lo omites, el usuario se confundirá.
6. Concisión y Continuidad: REGLA ESTRICTA: TIENES PROHIBIDO saludar (no digas "Hola", "Qué tal", "Buenas", etc.). La interfaz ya saludó al turista. Ve directamente a la respuesta.
7. Coherencia conversacional y Ubicación:
- Si el usuario busca recomendaciones turísticas (ej: qué hacer, lugares para visitar, bodegas, paseos, aventura), RECOMIENDA directamente los lugares provistos en la base de datos indicando en qué departamento o zona de Mendoza se encuentran (ej: Potrerillos, Luján de Cuyo, San Rafael, etc.).
- NO asumas que el turista solo busca lugares donde se encuentra físicamente ni le preguntes "¿en qué zona o localidad te encuentras?" para poder recomendar: los turistas viajan y se mueven libremente entre departamentos de Mendoza.
- NUNCA hagas una pregunta para pedir contexto y al mismo tiempo listes recomendaciones de lugares en el mismo mensaje. O respondes recomendando las opciones disponibles, o si falta un dato indispensable que el usuario haya pedido expresamente, preguntas amablemente.
- ÚNICAMENTE si el usuario pide de forma explícita recomendaciones "cerca de mí", "a mi alrededor" o "por donde estoy" sin especificar departamento ni zona, pregúntale amablemente qué departamento o zona de Mendoza planea visitar o en cuál se encuentra, sin volcar lugares al azar.
- Si no hay POIs disponibles en la BD para la búsqueda o categoría solicitada, responde con sinceridad indicando que por el momento no contamos con opciones registradas para esa categoría en la plataforma, y sugiere opciones afines o cómo explorar otras categorías en Ando (como bodegas, gastronomía, naturaleza o alojamiento), sin inventar POIs ficticios.
- Enfoque exclusivo en el pedido actual: Responde EXCLUSIVAMENTE a la consulta actual del usuario. Si el usuario cambió de tema o categoría (por ejemplo, de trekking o actividades al aire libre a comida o bodegas), enfócate 100% en el nuevo tema y NO vuelvas a mencionar ni te justifiques por búsquedas de turnos anteriores.
"""

EXTRACTION_SYSTEM_PROMPT = """Eres el clasificador semántico de intenciones turísticas para Mendoza ('Ando').
Analiza el mensaje del usuario y clasifica con precisión la intención del turista y extrae los parámetros clave en formato JSON.

INTENCIONES (intent):
- "task_continue": El usuario está respondiendo a una solicitud previa o completando datos para la tarea activa (ej: dando fechas 'mañana y que dure 1 día', 'del 10 al 14', personas 'somos 2', 'dale sigamos').
- "task_cancel": El usuario quiere cancelar o dejar la tarea activa (ej: 'no, dejá', 'cancelar', 'olvidate', 'no quiero el itinerario', 'dejalo hasta acá').
- "task_subquery": El usuario hace una pregunta puntual o informativa sobre un lugar, menú, horario o servicio (ej: '¿tienen facturas?', '¿a qué hora abre?', '¿cuánto cuesta?'), o pide una consulta intermedia durante una tarea activa.
- "itinerary_create": El usuario pide crear, armar, diseñar o planificar un viaje o itinerario desde cero (ej: 'armame un viaje', 'quiero planificar unos días', 'preparame un itinerario', 'organizame una ruta').
- "itinerary_query": El usuario consulta el estado, avance, próximas paradas o información de sus viajes existentes (ej: 'cómo va mi viaje', 'qué parada sigue', 'cuánto me falta').
- "itinerary_modify": El usuario quiere cambiar, editar, reordenar o quitar paradas de su itinerario.
- "recommendation": El usuario busca recomendaciones de lugares, actividades, bodegas, restaurantes, paseos o alojamiento en Mendoza.
- "general_chat": Saludos, preguntas de uso de la app o charla casual sin pedido turístico.

REGLAS DE EXTRACCIÓN:
1. is_recommendation: true ÚNICAMENTE si busca descubrir o que le recomienden lugares nuevos; debe ser FALSE si el usuario hace una pregunta puntual/informativa sobre un lugar ya mencionado, menú, horarios, precios, facturas, etc. (ej: '¿tienen facturas?', '¿a qué hora abre?', '¿cuánto cuesta?', '¿tienen estacionamiento?' -> is_recommendation: false).
2. search_keyword: El término sustantivo, lugar o concepto específico que busca el usuario, libre de verbos de acción, cortesía y adjetivos generales ('bueno', 'lindo', 'rico', 'mejor', 'hermoso', 'increíble', 'tranquilo').
   - NUNCA pongas verbos generales como search_keyword (ej: 'comer', 'tomar', 'beber', 'almorzar', 'cenar', 'ir', 'visitar', 'dormir', 'hospedarme', 'pasear' NO son search_keyword; en esos casos deja search_keyword = null).
   - Ejemplos correctos:
     - 'lugares con buenas vistas' -> search_keyword: 'vistas', categories: ['Naturaleza'].
     - 'dónde ver lindos paisajes' -> search_keyword: 'paisajes', categories: ['Naturaleza'].
     - 'lugares con mirador' -> search_keyword: 'mirador', categories: ['Naturaleza'].
     - 'lugares para comer' -> search_keyword: null, categories: ['Gastronomía'].
     - 'lugares para tomar café' -> search_keyword: 'café', categories: ['Gastronomía'].
     - 'lugares para tomar tragos' o 'dónde salir a tomar algo' -> search_keyword: 'tragos', categories: ['Gastronomía'].
     - 'dónde comer un buen asado' -> search_keyword: 'asado', categories: ['Gastronomía'].
     - 'quiero visitar bodegas' -> search_keyword: null, categories: ['Bodegas y Viñedos'].
3. search_synonyms: Lista de 2 a 5 sinónimos o conceptos turísticos afines al search_keyword para enriquecer la búsqueda en BD (ej: si search_keyword='vistas' -> ['vista', 'mirador', 'panorámica', 'paisaje']; si es 'tragos' o 'tomar algo' -> ['tragos', 'bar', 'pub', 'coctelería', 'birra', 'cerveza']; si es 'asado' -> ['asado', 'parrilla', 'chivito']; si es 'trekking' -> ['trekking', 'senderismo', 'caminata']; si es 'degustación' -> ['degustación', 'cata', 'maridaje']; si search_keyword es null -> []).
4. categories: Lista de nombres de categorías aplicables de la lista disponible (ej: 'Bodegas y Viñedos', 'Gastronomía', 'Naturaleza', 'Turismo Aventura', 'Alojamiento', 'Cultura'). Siempre que el pedido del usuario se relacione con alguna categoría disponible (ej: aire libre, paisajes o miradores -> 'Naturaleza' o 'Turismo Aventura'; comida o bebida -> 'Gastronomía'), asígnala.
5. max_price: Número si el usuario especifica un presupuesto o precio numérico explícito (ej: 'hasta 20000', 'menos de 30 mil', 'presupuesto de 25000'). Si sólo dice términos cualitativos como 'económico', 'barato', 'accesible', 'bajo costo', pon max_price: null y preferencia_economica: true.
6. preferencia_economica: true si el usuario busca opciones económicas, baratas, accesibles o de bajo costo sin dar una cifra exacta; false en caso contrario.
7. department: Nombre de departamento de Mendoza si lo menciona (ej: 'Luján de Cuyo', 'Maipú', 'San Rafael', 'Capital', 'Godoy Cruz', 'Guaymallén', 'Tunuyán', 'Tupungato', 'San Carlos', 'Las Heras', 'Lavalle', 'Rivadavia', 'Junín', 'Santa Rosa', 'La Paz', 'General Alvear', 'Malargüe').
8. zone: Localidad o zona específica (ej: 'Chacras de Coria', 'Agrelo', 'Potrerillos', 'Cacheuta', 'Uspallata', 'Valle de Uco', 'Los Chacayes').
9. start_date: Fecha de inicio en formato YYYY-MM-DD si la menciona o resuelve (año actual 2026).
10. people_count: Número entero de personas si lo menciona (ej: 2 si dice 'para 2 personas' o 'en pareja', 1 si dice 'solo', 4 si dice 'familia').
11. itinerary_target: Nombre o número del viaje si lo menciona.
12. itinerary_name: Nombre o título deseado para el itinerario si lo menciona explícitamente (ej: 'Escapada Romántica', 'Ruta del Vino', 'Aventura en los Andes'). Si el usuario dice 'que se llame X' o 'con nombre X', extrae ÚNICAMENTE el nombre X limpio, sin frases accesorias ni conectores de duración/fechas/compañía (ej: 'que se llame ACIA lo hace y que dure 2 días' -> itinerary_name: 'ACIA lo hace').
13. travel_type: 'Solitario', 'Pareja', 'Familia', 'Amigos' según la composición de viajeros.
14. travel_mode: Modo de transporte preferido si lo indica ('auto', 'pie', 'bicicleta', 'moto', 'micro').
15. SEGUIMIENTO, REINTENTO Y CONTINUIDAD (CONTEXTO_ACTUAL):
Si el usuario dice 'otro', 'otra opción', 'más lugares', 'algo diferente', 'recomiéndame otro', 'reintenta', 'reintenta la consulta anterior', 'probá de nuevo', 'otra vez', 'repetí' o hace preguntas de seguimiento ('y en Maipú?', 'uno más barato', 'y cerca de...?'):
- DEBES clasificar intent="recommendation" e is_recommendation=true.
- CONTINUIDAD PURA: Si el usuario pide paginación ('otro', 'más opciones') o refinamiento de filtro ('y en Maipú?', 'algo más barato') SIN introducir una nueva actividad ni nuevos sustantivos:
  - HEREDA el 'search_keyword' y 'categories' de CONTEXTO_ACTUAL.
  - Si cambia ubicación (ej: 'y en Godoy Cruz?'), actualiza department/zone y conserva search_keyword y categories anteriores.
  - Si cambia precio (ej: 'algo más barato'), actualiza max_price y conserva el resto.
- NUEVA ACTIVIDAD, VERBO O TEMA (INCLUSO CON 'Y ...' O EN LA MISMA CATEGORÍA): Si el usuario menciona una acción, verbo o rubro diferente (ej: 'para comer', 'lugares para cenar', 'bodegas', 'alojamiento', 'y sushi?', 'y cafés?', 'y rafting?') tras haber buscado otro tema (ej: trekking, asado):
  - NUNCA HEREDES el 'search_keyword' anterior.
  - Si especifica un nuevo término concreto (ej: 'sushi', 'café', 'rafting'), pon 'search_keyword': ese término limpio.
  - Si es una actividad general (ej: 'para comer', 'donde almorzar', 'lugares para salir'), pon 'search_keyword': null y asigna únicamente las 'categories' correspondientes.

Responde ÚNICAMENTE un JSON válido con este esquema:
{
  "intent": "task_continue" | "task_cancel" | "task_subquery" | "recommendation" | "itinerary_create" | "itinerary_query" | "itinerary_modify" | "general_chat",
  "is_recommendation": true | false,
  "search_keyword": null | string,
  "search_synonyms": ["termino1", "termino2"],
  "categories": ["nombre"],
  "max_price": null | numero,
  "preferencia_economica": true | false,
  "department": null | string,
  "zone": null | string,
  "duration_minutes": null | numero,
  "start_date": null | "YYYY-MM-DD",
  "end_date": null | "YYYY-MM-DD",
  "people_count": null | numero,
  "itinerary_target": null | string,
  "itinerary_name": null | string,
  "travel_type": null | string,
  "travel_mode": null | string
}
"""


SYSTEM_PROMPT += """

REGLAS DE SOPORTE DE PLATAFORMA:
- Para consultas sobre el uso de Ando, responde exclusivamente con DOCUMENTACION_DE_SOPORTE.
- Respeta ROL_ACTUAL y no mezcles instrucciones de otros roles.
- No inventes funcionalidades, pasos, permisos ni enlaces.
- Si la documentación no alcanza, deriva al soporte formal usando solo el fallback y enlaces documentados.
"""


class AssistantService:
    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        llm_model: Optional[str] = None,
        timeout_seconds: float = 12.0,
    ):
        self.gemini_api_key = gemini_api_key if gemini_api_key is not None else settings.gemini_api_key
        self.openai_api_key = openai_api_key if openai_api_key is not None else settings.openai_api_key
        self.groq_api_key = groq_api_key if groq_api_key is not None else settings.groq_api_key
        self.llm_model = llm_model or settings.llm_model or "openai/gpt-oss-120b"
        self.timeout_seconds = timeout_seconds

    def generate_chat_response(self, request: AssistantChatRequest) -> AssistantChatResponse:
        """
        Genera la respuesta conversacional utilizando el LLM configurado (Groq / Gemini / OpenAI).
        Si la API no responde o hay problemas de cuota/red, recurre al fallback determinístico.
        """
        print(f"\n[ACIA-LLM-CHAT] Generando respuesta para: '{request.message}' | POIs en contexto: {len(request.poi_context or '')} caracteres")
        # 1. Intentar con Groq si está configurado (Ultra rápido y gratuito)
        if self.groq_api_key and settings.llm_provider in ["groq", "auto", "gemini"]:
            try:
                res = self._call_groq_api(request)
                if res:
                    print(f"[ACIA-LLM-CHAT] [OK] Respondido via {res.model_used} ({res.tokens_used} tokens)\n[ACIA-LLM-CHAT] [RESPUESTA GENERADA]:\n{res.response}\n")
                    return res
                else:
                    print("[ACIA-LLM-CHAT] [WARN] Groq no devolvio respuesta. Intentando siguiente proveedor...")
            except Exception as e:
                print(f"[ACIA-LLM-CHAT] [ERROR] Error en Groq: {e}. Intentando siguiente proveedor...")

        # 2. Intentar con Gemini
        if self.gemini_api_key:
            try:
                res = self._call_gemini_api(request)
                if res:
                    print(f"[ACIA-LLM-CHAT] [OK] Respondido via {res.model_used} ({res.tokens_used} tokens)\n[ACIA-LLM-CHAT] [RESPUESTA GENERADA]:\n{res.response}\n")
                    return res
                else:
                    print("[ACIA-LLM-CHAT] [WARN] Gemini no devolvio respuesta. Intentando siguiente proveedor...")
            except Exception as e:
                print(f"[ACIA-LLM-CHAT] [ERROR] Error en Gemini: {e}. Intentando siguiente proveedor...")

        # 3. Intentar con OpenAI si está configurado
        if self.openai_api_key and settings.llm_provider == "openai":
            try:
                res = self._call_openai_api(request)
                if res:
                    print(f"[ACIA-LLM-CHAT] [OK] Respondido via {res.model_used} ({res.tokens_used} tokens)\n[ACIA-LLM-CHAT] [RESPUESTA GENERADA]:\n{res.response}\n")
                    return res
                else:
                    print("[ACIA-LLM-CHAT] [WARN] OpenAI no devolvio respuesta.")
            except Exception as e:
                print(f"[ACIA-LLM-CHAT] [ERROR] Error en OpenAI: {e}")

        # 4. Fallback determinístico estructurado (0 tokens, 100% resiliente)
        print("[ACIA-LLM-CHAT] [FALLBACK ACTIVADO] Ningun proveedor LLM respondio. Generando respuesta local estructurada a 0 tokens.")
        fallback_res = self._build_deterministic_fallback(request)
        print(f"[ACIA-LLM-CHAT] [RESPUESTA FALLBACK]:\n{fallback_res.response}\n")
        return fallback_res

    def _get_language_directive(self, language: Optional[str]) -> Optional[str]:
        lang = (language or "es").strip().lower()
        if lang == "en":
            return (
                "MANDATORY LANGUAGE REQUIREMENT: You MUST answer ENTIRELY in ENGLISH (regardless of the language used in user messages or history). "
                "Keep POI names in their original names using bold (e.g. **POI Name**). Do NOT include app links or raw URLs in your text response."
            )
        elif lang == "pt":
            return (
                "INSTRUÇÃO DE IDIOMA OBRIGATÓRIA: Você DEVE responder INTEGRALMENTE em PORTUGUÊS (independentemente do idioma usado nas mensagens do usuário ou histórico). "
                "Mantenha os nomes reais dos POIs em negrito (ex: **Nome**). NÃO inclua links brutos ou URLs técnicas no texto."
            )
    def _call_groq_api(self, request: AssistantChatRequest) -> Optional[AssistantChatResponse]:
        system_text = SYSTEM_PROMPT

        lang_directive = self._get_language_directive(request.language)
        if lang_directive:
            system_text += f"\n\n{lang_directive}"

        system_text += f"\n\nROL_ACTUAL: {request.role or 'no especificado'}"
        if request.support_documentation:
            if request.poi_context:
                system_text += "\nDOCUMENTACION_DE_SOPORTE: Consulta de recomendación turística."
            else:
                system_text += f"\nDOCUMENTACION_DE_SOPORTE:\n{request.support_documentation[:2500]}"
        else:
            system_text += "\nDOCUMENTACION_DE_SOPORTE: No hay documentación configurada."

        if request.user_preferences:
            pref_str = ", ".join(request.user_preferences)
            system_text += f"\nPREFERENCIAS_DECLARADAS_DEL_USUARIO: El turista tiene interés en: {pref_str}."

        if request.poi_context:
            system_text += f"\nCONTEXTO_DE_POIS (IMPORTANTE: Ignóralos si el usuario pidió lugares cerca y no aclaró su ubicación):\n{request.poi_context}"

        if request.itinerary_context:
            system_text += f"\nCONTEXTO_DE_ITINERARIOS:\n{request.itinerary_context}"

        if request.conversation_summary:
            system_text += f"\nRESUMEN_CONVERSACION_PREVIA:\n{request.conversation_summary}"

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_text},
        ]

        recent_history = request.history[-4:] if request.history else []
        for msg in recent_history:
            role = "user" if msg.rol == "usuario" else "assistant"
            content = (
                msg.contenido[:250] + "..."
                if role == "assistant" and len(msg.contenido) > 250
                else msg.contenido
            )
            messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": request.message})

        preferred_model = getattr(settings, "groq_chat_model", "openai/gpt-oss-120b")
        if preferred_model not in ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]:
            preferred_model = "openai/gpt-oss-120b"
        models_to_try = [preferred_model]
        for fallback_model in ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]:
            if fallback_model not in models_to_try:
                models_to_try.append(fallback_model)

        with httpx.Client(timeout=self.timeout_seconds) as client:
            for model_name in models_to_try:
                payload = {
                    "model": model_name,
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 1200,
                }
                try:
                    resp = client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.groq_api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                        tokens = data.get("usage", {}).get("total_tokens", 0)
                        if text:
                            return AssistantChatResponse(
                                response=text,
                                tokens_used=tokens,
                                model_used=f"groq/{model_name}",
                            )
                    else:
                        print(f"[AssistantService] Groq API chat ({model_name}) returned status {resp.status_code} ({resp.text[:150]}).")
                        if resp.status_code in (413, 429):
                            continue
                except Exception as e:
                    print(f"[AssistantService] Groq API chat ({model_name}) exception: {e}")

        return None

    def _call_gemini_api(self, request: AssistantChatRequest) -> Optional[AssistantChatResponse]:
        system_text = SYSTEM_PROMPT

        lang_directive = self._get_language_directive(request.language)
        if lang_directive:
            system_text += f"\n\n{lang_directive}"

        system_text += f"\n\nROL_ACTUAL: {request.role or 'no especificado'}"
        system_text += f"\nDOCUMENTACION_DE_SOPORTE:\n" + (request.support_documentation or "No hay documentación configurada.")

        if request.user_preferences:
            pref_str = ", ".join(request.user_preferences)
            system_text += f"\nPREFERENCIAS_DECLARADAS_DEL_USUARIO: El turista tiene interés en: {pref_str}."

        if request.poi_context:
            system_text += f"\nCONTEXTO_DE_POIS:\n{request.poi_context}"

        if request.itinerary_context:
            system_text += f"\nCONTEXTO_DE_ITINERARIOS:\n{request.itinerary_context}"

        if request.conversation_summary:
            system_text += f"\nRESUMEN_CONVERSACION_PREVIA:\n{request.conversation_summary}"

        contents = []

        # Historial reciente compacto (Ventana deslizante optimizada para ahorro de tokens)
        recent_history = request.history[-6:] if request.history else []
        for msg in recent_history:
            role = "user" if msg.rol == "usuario" else "model"
            contents.append({"role": role, "parts": [{"text": msg.contenido}]})

        # Mensaje actual
        contents.append({"role": "user", "parts": [{"text": request.message}]})

        payload = {
            "system_instruction": {
                "parts": [{"text": system_text}]
            },
            "contents": contents,
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 1000,
                "thinkingConfig": {
                    "thinkingBudget": 0,
                },
            },
        }

        candidate_models = [m for m in [
            self.llm_model,
            "gemini-3.8-flash",
            "gemini-3.5-flash",
            "gemini-2.5-flash",
            "gemini-flash-latest",
        ] if m and m.startswith("gemini")]
        seen = set()
        models_to_try = [m for m in candidate_models if not (m in seen or seen.add(m))]

        with httpx.Client(timeout=self.timeout_seconds) as client:
            for model_name in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.gemini_api_key}"
                try:
                    resp = client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        text = (
                            data.get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [{}])[0]
                            .get("text", "")
                            .strip()
                        )
                        usage = data.get("usageMetadata", {})
                        total_tokens = usage.get("totalTokenCount", 0)

                        if text:
                            return AssistantChatResponse(
                                response=text,
                                tokens_used=total_tokens,
                                model_used=model_name,
                            )
                    elif resp.status_code in [401, 402, 403, 429]:
                        print(f"[AssistantService] Gemini API returned status {resp.status_code} ({resp.text[:120]}). Skipping further Gemini attempts.")
                        break
                except Exception:
                    continue

        return None

    def _call_openai_api(self, request: AssistantChatRequest) -> Optional[AssistantChatResponse]:
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

        lang_directive = self._get_language_directive(request.language)
        if lang_directive:
            messages.append({"role": "system", "content": lang_directive})

        messages.append({"role": "system", "content": f"ROL_ACTUAL: {request.role or 'no especificado'}"})
        messages.append({
            "role": "system",
            "content": "DOCUMENTACION_DE_SOPORTE (fuente única para uso de plataforma):\n"
            + (request.support_documentation or "No hay documentación configurada."),
        })

        if request.user_preferences:
            pref_str = ", ".join(request.user_preferences)
            messages.append({"role": "system", "content": f"PREFERENCIAS_DEL_USUARIO: {pref_str}"})

        if request.poi_context:
            messages.append({"role": "system", "content": f"CONTEXTO_POIS:\n{request.poi_context}"})

        if request.itinerary_context:
            messages.append({"role": "system", "content": f"CONTEXTO_ITINERARIO:\n{request.itinerary_context}"})

        if request.conversation_summary:
            messages.append({"role": "system", "content": f"RESUMEN_CONVERSACION_PREVIA:\n{request.conversation_summary}"})

        recent_history = request.history[-6:] if request.history else []
        for msg in recent_history:
            role = "user" if msg.rol == "usuario" else "assistant"
            messages.append({"role": role, "content": msg.contenido})

        messages.append({"role": "user", "content": request.message})

        payload = {
            "model": "gpt-4o-mini",
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 1200,
        }

        with httpx.Client(timeout=self.timeout_seconds) as client:
            try:
                resp = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    tokens = data.get("usage", {}).get("total_tokens", 0)
                    if text:
                        return AssistantChatResponse(
                            response=text,
                            tokens_used=tokens,
                            model_used="gpt-4o-mini",
                        )
            except Exception:
                pass

        return None

    def _build_deterministic_fallback(self, request: AssistantChatRequest) -> AssistantChatResponse:
        """
        Genera una respuesta cordial utilizando plantillas basadas en los POIs o datos de itinerario provistos.
        Se activa si el LLM no está disponible o falla por cuota/timeout.
        Soporta respuestas multilenguaje (es, en, pt - US-ACIA-06).
        """
        lang = (request.language or "es").strip().lower()
        if lang not in ["es", "en", "pt"]:
            lang = "es"

        if self._is_support_query(request.message) and not request.itinerary_context:
            return self._build_support_fallback(request, lang)

        # 1. Fallback de Itinerario (US-ACIA-04 / US-GDI-03)
        if request.itinerary_context:
            lines_it: List[str] = []
            if "ESTADO_ITINERARIO: El usuario no tiene ningún itinerario" in request.itinerary_context:
                if lang == "en":
                    lines_it.append("You don't have any itineraries created in Ando yet. But we can plan your ideal trip right now!")
                    lines_it.append("\nYou can create it in 3 ways:")
                    lines_it.append("1. **With me (AI Assistant)**: Ask me to build a plan by specifying dates and preferences.")
                    lines_it.append("2. **Manual Creation**: Design your route step by step in the *\"My Itineraries\"* section.")
                    lines_it.append("3. **Community**: Discover and clone public itineraries from other travelers.")
                elif lang == "pt":
                    lines_it.append("Você ainda não possui nenhum itinerário criado no Ando. Mas podemos planejar sua viagem ideal agora mesmo!")
                    lines_it.append("\nVocê pode criá-lo de 3 formas:")
                    lines_it.append("1. **Comigo (Assistente IA)**: Peça-me para montar um plano indicando datas e preferências.")
                    lines_it.append("2. **Criação Manual**: Desenhe sua rota passo a passo na seção *\"Meus Itinerários\"*.")
                    lines_it.append("3. **Comunidade**: Descubra e clone itinerários públicos de outros viajantes.")
                else:
                    lines_it.append("Aún no tienes ningún itinerario creado en Ando. ¡Pero podemos armar tu viaje ideal ahora mismo!")
                    lines_it.append("\nPuedes crearlo de 3 formas:")
                    lines_it.append("1. **Conmigo (Asistente IA)**: Pídeme que te arme un plan indicando fechas y preferencias.")
                    lines_it.append("2. **Creación Manual**: Diseña tu ruta paso a paso desde la sección *\"Mis Itinerarios\"*.")
                    lines_it.append("3. **Comunidad**: Descubre y clona itinerarios públicos de otros viajeros.")
            elif "DERIVACION_MODIFICACION" in request.itinerary_context or "MODIFICAR" in request.itinerary_context:
                link_match = re.search(r"(\[[^\]]+\]\(app:\/\/itinerario\/[^\)]+\))", request.itinerary_context)
                it_link = link_match.group(1) if link_match else "[tu itinerario](app://itinerarios)"
                if lang == "en":
                    lines_it.append(f"To modify your trip **{it_link}**, you can use the interactive editor to add or remove stops, reorder activities, and adjust schedules.")
                    lines_it.append("\nWhat change would you like to make?")
                elif lang == "pt":
                    lines_it.append(f"Para modificar sua viagem **{it_link}**, você pode usar o editor interativo para adicionar ou remover paradas, reordenar atividades e ajustar horários.")
                    lines_it.append("\nQual alteração você gostaria de fazer?")
                else:
                    lines_it.append(f"Para modificar tu viaje **{it_link}**, puedes ingresar directamente a su editor interactivo para agregar o quitar paradas, reordenar actividades y ajustar los horarios.")
                    lines_it.append("\n¿Qué cambio te gustaría realizar?")
            else:
                if lang == "en":
                    lines_it.append("Here are the details requested about your itinerary in Mendoza.")
                    lines_it.append("You can go to the itineraries section in the app to view the full map and make modifications.")
                elif lang == "pt":
                    lines_it.append("Aqui estão os detalhes solicitados sobre seu itinerário em Mendoza.")
                    lines_it.append("Você pode acessar a seção de itinerários no app para ver o mapa completo e fazer alterações.")
                else:
                    lines_it.append("Aquí tienes los detalles solicitados sobre tu itinerario en Mendoza.")
                    lines_it.append("Puedes ingresar a la sección de itinerarios en la app para ver el mapa completo y realizar modificaciones.")

            return AssistantChatResponse(
                response="\n".join(lines_it),
                tokens_used=0,
                model_used="deterministic-fallback",
            )

        # 2. Fallback de POIs / Recomendaciones
        poi_context = request.poi_context or ""
        poi_names = re.findall(r'\[\d+\]\s*"([^"]+)"', poi_context)
        if not poi_names:
            poi_names = re.findall(r"\[([^\]]+)\]\(app:\/\/poi\/[^\)]+\)", poi_context)

        lines: List[str] = []
        if "NOTA_IMPORTANTE_RELAJACION:" in poi_context:
            match_nota = re.search(r"NOTA_IMPORTANTE_RELAJACION:\s*([^\n]+)", poi_context)
            if match_nota:
                lines.append(f"Nota: {match_nota.group(1)}\n")

        if poi_names:
            if lang == "en":
                lines.append("Based on what you're looking for in Mendoza, here are some great recommended options:")
                for name in poi_names[:5]:
                    lines.append(f"• **{name}**")
                lines.append("\nYou can explore their interactive cards below for more photos, ratings, and location details.")
            elif lang == "pt":
                lines.append("De acordo com o que você procura em Mendoza, aqui estão algumas ótimas opções recomendadas:")
                for name in poi_names[:5]:
                    lines.append(f"• **{name}**")
                lines.append("\nVocê pode conferir os cards interativos abaixo para ver fotos, avaliações e localização.")
            else:
                lines.append("Según lo que buscas en Mendoza, aquí tienes excelentes opciones recomendadas:")
                for name in poi_names[:5]:
                    lines.append(f"• **{name}**")
                lines.append("\nPuedes explorar las tarjetas de cada lugar aquí abajo para ver fotos, valoraciones y ubicación.")
        else:
            if lang == "en":
                lines.append(
                    "Hello! I'm at your service to help you plan your trip and suggest places in Mendoza. "
                    "Would you like to explore wineries, restaurants, accommodations, or outdoor adventure tours?"
                )
            elif lang == "pt":
                lines.append(
                    "Olá! Estou à sua disposição para ajudar a planejar sua viagem e sugerir lugares em Mendoza. "
                    "Gostaria de conhecer vinícolas, restaurantes, hospedagens ou passeios de aventura?"
                )
            else:
                lines.append(
                    "¡Hola! Estoy a tu disposición para ayudarte a planificar tu viaje y sugerirte lugares en Mendoza. "
                    "¿Te gustaría conocer bodegas, restaurantes, alojamientos o excursiones de aventura?"
                )

        return AssistantChatResponse(
            response="\n".join(lines),
            tokens_used=0,
            model_used="deterministic-fallback",
        )

    @staticmethod
    def _is_support_query(message: str) -> bool:
        return bool(re.search(
            r"\b(c[oó]mo|crear|gestionar|usar|activar|configurar|funcionalidad|permiso|ayuda|soporte|itinerario)\b",
            message.lower(),
        ))

    def _build_support_fallback(self, request: AssistantChatRequest, lang: str) -> AssistantChatResponse:
        response = {
            "en": "I couldn't resolve this with Ando's available documentation. You can use the Help and Support Contact Channel.",
            "pt": "N\u00e3o pude resolver isso com a documenta\u00e7\u00e3o dispon\u00edvel do Ando. Voc\u00ea pode recorrer ao Canal de Contato de Ajuda e Suporte.",
        }.get(
            lang,
            "No pude resolver esta consulta con la documentaci\u00f3n disponible de Ando. Pod\u00e9s recurrir al Canal de Contacto de Ayuda y Soporte.",
        )
        return AssistantChatResponse(response=response, tokens_used=0, model_used="deterministic-fallback")

    def extract_intent_and_params(self, request: AssistantExtractRequest) -> AssistantExtractResponse:
        """
        Extrae la intención de recomendación y parámetros estructurados usando LLM (Groq / Gemini / OpenAI).
        Si falla o no hay API key, recurre a la extracción heurística de respaldo.
        """
        res: Optional[AssistantExtractResponse] = None

        # 1. Intentar con Groq si está configurado (Ultra rápido y gratuito)
        if self.groq_api_key and settings.llm_provider in ["groq", "auto", "gemini"]:
            try:
                res = self._call_groq_extraction(request)
            except Exception as e:
                print(f"[ACIA-LLM-EXTRACT] [ERROR] Error en extraccion con Groq: {e}")

        # 2. Intentar con Gemini
        if not res and self.gemini_api_key:
            try:
                res = self._call_gemini_extraction(request)
            except Exception as e:
                print(f"[ACIA-LLM-EXTRACT] [ERROR] Error en extraccion con Gemini: {e}")

        # 3. Intentar con OpenAI si está configurado
        if not res and self.openai_api_key and settings.llm_provider == "openai":
            try:
                res = self._call_openai_extraction(request)
            except Exception as e:
                print(f"[ACIA-LLM-EXTRACT] [ERROR] Error en extraccion con OpenAI: {e}")

        # 4. Fallback heurístico
        if not res:
            print("[ACIA-LLM-EXTRACT] [FALLBACK HEURISTICO] Extraccion LLM fallo o no disponible. Usando heuristica local.")
            res = self._heuristic_extraction(request)

        print(f"\n[ACIA-LLM-EXTRACT] Input: '{request.message}' | Contexto previo: {request.current_context}")
        print(f"[ACIA-LLM-EXTRACT] Resultado: intent={res.intent}, name='{res.itinerary_name}', keyword='{res.search_keyword}', categories={res.categories}, depto='{res.department}', zona='{res.zone}' (via {res.model_used})")
        return res

    def _call_groq_extraction(self, request: AssistantExtractRequest) -> Optional[AssistantExtractResponse]:
        today_str = datetime.now().strftime('%Y-%m-%d')
        date_info = f"Fecha actual de referencia: {today_str}. Resuelve fechas relativas como 'hoy', 'mañana', 'próximo fin de semana'."
        task_info = f"TAREA_ACTIVA_ACTUAL: {request.active_task}" if request.active_task else "TAREA_ACTIVA_ACTUAL: ninguna"
        ctx_info = f"CONTEXTO_ACTUAL: {json.dumps(request.current_context, ensure_ascii=False)}" if request.current_context else ""
        cat_info = f"Categorías válidas: {', '.join(request.available_categories)}" if request.available_categories else ""
        dep_info = f"Departamentos válidos en Mendoza: {', '.join(request.available_departments)}" if request.available_departments else ""
        
        history_snippet = ""
        if request.recent_messages:
            h_lines = []
            for m in request.recent_messages[-2:]:
                sender = "Turista" if m.rol in ["usuario", "user"] else "Asistente"
                snippet = m.contenido[:150] + ("..." if len(m.contenido) > 150 else "")
                h_lines.append(f"{sender}: {snippet}")
            if h_lines:
                history_snippet = "ULTIMOS_MENSAJES_PREVIOS:\n" + "\n".join(h_lines)

        prompt_parts = [p for p in [date_info, task_info, ctx_info, history_snippet, cat_info, dep_info] if p]
        user_prompt = "\n".join(prompt_parts) + f"\nMensaje del usuario: \"{request.message}\""

        extract_model = getattr(settings, "groq_extract_model", "openai/gpt-oss-20b")
        models_to_try = [extract_model]
        for fallback_model in ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"]:
            if fallback_model not in models_to_try:
                models_to_try.append(fallback_model)

        with httpx.Client(timeout=self.timeout_seconds) as client:
            for model_name in models_to_try:
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.0,
                    "max_tokens": 800,
                }
                try:
                    resp = client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {self.groq_api_key}", "Content-Type": "application/json"},
                        json=payload,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                        tokens = data.get("usage", {}).get("total_tokens", 0)
                        if raw_text:
                            parsed = json.loads(raw_text)
                            intent = parsed.get("intent")
                            is_rec = bool(parsed.get("is_recommendation", False) or intent == "recommendation")
                            return AssistantExtractResponse(
                                is_recommendation=is_rec,
                                intent=intent,
                                search_keyword=parsed.get("search_keyword"),
                                search_synonyms=list(parsed.get("search_synonyms", [])),
                                categories=list(parsed.get("categories", [])),
                                max_price=float(parsed["max_price"]) if parsed.get("max_price") is not None else None,
                                preferencia_economica=bool(parsed.get("preferencia_economica", False)),
                                department=parsed.get("department"),
                                zone=parsed.get("zone"),
                                duration_minutes=int(parsed["duration_minutes"]) if parsed.get("duration_minutes") is not None else None,
                                start_date=parsed.get("start_date"),
                                end_date=parsed.get("end_date"),
                                people_count=int(parsed["people_count"]) if parsed.get("people_count") is not None else None,
                                itinerary_target=parsed.get("itinerary_target"),
                                itinerary_name=parsed.get("itinerary_name"),
                                travel_type=parsed.get("travel_type"),
                                travel_mode=parsed.get("travel_mode"),
                                tokens_used=tokens,
                                model_used=f"groq/{model_name}",
                            )
                    else:
                        print(f"[AssistantService] Groq extraction ({model_name}) status {resp.status_code} ({resp.text[:120]})")
                        if resp.status_code in (413, 429):
                            continue
                except Exception:
                    pass

        return None

    def _call_gemini_extraction(self, request: AssistantExtractRequest) -> Optional[AssistantExtractResponse]:
        today_str = datetime.now().strftime('%Y-%m-%d')
        date_info = f"Fecha actual de referencia: {today_str}. Resuelve fechas relativas como 'hoy', 'mañana', 'próximo fin de semana'."
        task_info = f"TAREA_ACTIVA_ACTUAL: {request.active_task}" if request.active_task else "TAREA_ACTIVA_ACTUAL: ninguna"
        ctx_info = f"CONTEXTO_ACTUAL: {json.dumps(request.current_context, ensure_ascii=False)}" if request.current_context else ""
        cat_info = f"Categorías válidas en la app: {', '.join(request.available_categories)}" if request.available_categories else ""
        dep_info = f"Departamentos válidos en Mendoza: {', '.join(request.available_departments)}" if request.available_departments else ""
        
        history_snippet = ""
        if request.recent_messages:
            h_lines = []
            for m in request.recent_messages[-2:]:
                sender = "Turista" if m.rol in ["usuario", "user"] else "Asistente"
                snippet = m.contenido[:150] + ("..." if len(m.contenido) > 150 else "")
                h_lines.append(f"{sender}: {snippet}")
            if h_lines:
                history_snippet = "ULTIMOS_MENSAJES_PREVIOS:\n" + "\n".join(h_lines)

        prompt_parts = [p for p in [date_info, task_info, ctx_info, history_snippet, cat_info, dep_info] if p]
        user_prompt = "\n".join(prompt_parts) + f"\nMensaje del usuario a analizar: \"{request.message}\""

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": EXTRACTION_SYSTEM_PROMPT},
                        {"text": user_prompt},
                    ]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.0,
                "maxOutputTokens": 800,
                "thinkingConfig": {
                    "thinkingBudget": 0,
                },
            },
        }

        candidate_models = [m for m in [
            self.llm_model,
            "gemini-3.8-flash",
            "gemini-3.5-flash",
            "gemini-2.5-flash",
            "gemini-flash-latest",
        ] if m and m.startswith("gemini")]
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
                            .strip()
                        )
                        tokens = data.get("usageMetadata", {}).get("totalTokenCount", 0)
                        if raw_text:
                            parsed = json.loads(raw_text)
                            intent = parsed.get("intent")
                            is_rec = bool(parsed.get("is_recommendation", False) or intent == "recommendation")
                            return AssistantExtractResponse(
                                is_recommendation=is_rec,
                                intent=intent,
                                search_keyword=parsed.get("search_keyword"),
                                search_synonyms=list(parsed.get("search_synonyms", [])),
                                categories=list(parsed.get("categories", [])),
                                max_price=float(parsed["max_price"]) if parsed.get("max_price") is not None else None,
                                preferencia_economica=bool(parsed.get("preferencia_economica", False)),
                                department=parsed.get("department"),
                                zone=parsed.get("zone"),
                                duration_minutes=int(parsed["duration_minutes"]) if parsed.get("duration_minutes") is not None else None,
                                start_date=parsed.get("start_date"),
                                end_date=parsed.get("end_date"),
                                people_count=int(parsed["people_count"]) if parsed.get("people_count") is not None else None,
                                itinerary_target=parsed.get("itinerary_target"),
                                itinerary_name=parsed.get("itinerary_name"),
                                travel_type=parsed.get("travel_type"),
                                travel_mode=parsed.get("travel_mode"),
                                tokens_used=tokens,
                                model_used=model_name,
                            )
                    elif resp.status_code in [401, 402, 403, 429]:
                        print(f"[AssistantService] Gemini API returned status {resp.status_code} ({resp.text[:120]}). Skipping further Gemini extraction attempts.")
                        break
                except Exception:
                    continue

        return None

    def _call_openai_extraction(self, request: AssistantExtractRequest) -> Optional[AssistantExtractResponse]:
        today_str = datetime.now().strftime('%Y-%m-%d')
        date_info = f"Fecha actual de referencia: {today_str}. Resuelve fechas relativas como 'hoy', 'mañana', 'próximo fin de semana'."
        task_info = f"TAREA_ACTIVA_ACTUAL: {request.active_task}" if request.active_task else "TAREA_ACTIVA_ACTUAL: ninguna"
        ctx_info = f"CONTEXTO_ACTUAL: {json.dumps(request.current_context, ensure_ascii=False)}" if request.current_context else ""
        cat_info = f"Categorías válidas: {', '.join(request.available_categories)}" if request.available_categories else ""
        dep_info = f"Departamentos válidos en Mendoza: {', '.join(request.available_departments)}" if request.available_departments else ""
        user_prompt = f"{date_info}\n{task_info}\n{ctx_info}\n{cat_info}\n{dep_info}\nMensaje del usuario: \"{request.message}\""

        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
            "max_tokens": 400,
        }

        with httpx.Client(timeout=self.timeout_seconds) as client:
            try:
                resp = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.openai_api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    raw_text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    tokens = data.get("usage", {}).get("total_tokens", 0)
                    if raw_text:
                        parsed = json.loads(raw_text)
                        intent = parsed.get("intent")
                        is_rec = bool(parsed.get("is_recommendation", False) or intent == "recommendation")
                        return AssistantExtractResponse(
                            is_recommendation=is_rec,
                            intent=intent,
                            search_keyword=parsed.get("search_keyword"),
                            search_synonyms=list(parsed.get("search_synonyms", [])),
                            categories=list(parsed.get("categories", [])),
                            max_price=float(parsed["max_price"]) if parsed.get("max_price") is not None else None,
                            preferencia_economica=bool(parsed.get("preferencia_economica", False)),
                            department=parsed.get("department"),
                            zone=parsed.get("zone"),
                            duration_minutes=int(parsed["duration_minutes"]) if parsed.get("duration_minutes") is not None else None,
                            start_date=parsed.get("start_date"),
                            end_date=parsed.get("end_date"),
                            people_count=int(parsed["people_count"]) if parsed.get("people_count") is not None else None,
                            itinerary_target=parsed.get("itinerary_target"),
                            itinerary_name=parsed.get("itinerary_name"),
                            travel_type=parsed.get("travel_type"),
                            travel_mode=parsed.get("travel_mode"),
                            tokens_used=tokens,
                            model_used="gpt-4o-mini",
                        )
            except Exception:
                pass

        return None

    def _heuristic_extraction(self, request: AssistantExtractRequest) -> AssistantExtractResponse:
        text = request.message.lower().strip()
        intent: Optional[str] = None

        # 0. Chequeo contextual si hay una tarea activa en curso
        if request.active_task:
            if any(w in text for w in ["cancelar", "cancela", "deja", "dejar", "olvidate", "no quiero", "dejalo", "no gracias", "abortar"]):
                intent = "task_cancel"
            elif any(w in text for w in ["recomiend", "recomend", "sugier", "suger", "donde comer", "donde ir", "adonde ir", "que visitar", "que hacer", "que puedo hacer"]):
                intent = "task_subquery"
            elif any(w in text for w in ["mañana", "hoy", "fin de semana", "del ", "al ", "para ", "somos ", "dias", "dia"]):
                intent = "task_continue"

        if not intent:
            if any(w in text for w in ["armar", "crear", "planificar", "hacer un viaje", "plan de viaje", "armame", "creame"]):
                intent = "itinerary_create"
            elif any(w in text for w in ["modificar", "cambiar", "editar", "reordenar", "quitar parada", "sacar parada", "agregar parada"]) and any(w in text for w in ["viaje", "itinerario", "ruta", "parada", "recorrido", "paradas"]):
                intent = "itinerary_modify"
            elif any(w in text for w in ["como va", "como viene", "proxima parada", "siguiente parada", "mi viaje", "mi itinerario"]):
                intent = "itinerary_query"
            elif any(
                trigger in text
                for trigger in [
                    "recomiend", "recomend", "sugier", "suger", "donde comer", "donde ir", "adonde ir",
                    "que visitar", "que hacer", "que puedo hacer", "actividades", "aire libre", "lugares",
                    "bodega", "restaurante", "hotel", "paseo", "pasear", "hay algun", "hay alguna",
                    "conoces algun", "tragos", "beber", "nocturno", "bar", "bares", "pub", "cafe", "café",
                    "caminar", "caminata", "caminatas", "senderismo", "trekking", "paseo", "pasear",
                    "otro", "otra", "otros", "otras", "mas opciones", "algo mas", "algo diferente"
                ]
            ):
                intent = "recommendation"

        ctx = request.current_context or {}
        has_action_verb = any(v in text for v in [
            "comer", "cenar", "almorzar", "desayunar", "merendar", "tomar", "beber",
            "dormir", "hospedar", "alojar", "acampar", "visitar", "pasear",
            "conocer", "caminar", "trotar", "pedalear", "escalar", "cabalgar",
            "trekking", "rafting", "tirolesa", "kayak", "degustar", "catar"
        ])
        is_continuity = not has_action_verb and any(
            w in text for w in ["otro", "otra", "otros", "otras", "algo mas", "mas opciones", "diferente", "que mas", "demas", "siguiente"]
        )
        is_rec = intent == "recommendation" or (
            intent == "task_subquery" and any(w in text for w in ["recomiend", "sugier", "otro", "otra", "otros", "otras", "opcion", "opciones", "distinto", "diferente"])
        )
        found_categories: List[str] = []
        if "bodega" in text or "vino" in text:
            found_categories.append("Bodegas y Viñedos")
        if any(w in text for w in ["comer", "restaurante", "asado", "tragos", "beber", "bar", "bares", "pub", "nocturno", "coctel", "cerveceria", "cafe", "café", "cafeteria"]):
            found_categories.append("Gastronomía")
        if any(w in text for w in ["aire libre", "naturaleza", "montaña", "lago", "caminar", "caminata", "caminatas", "pasear", "paseo"]):
            found_categories.append("Naturaleza")
        if any(w in text for w in ["aventura", "rafting", "trekking", "senderismo", "tirolesa", "cabalgata"]):
            found_categories.append("Turismo Aventura")
        if "hotel" in text or "dormir" in text or "cabaña" in text or "alojamiento" in text:
            found_categories.append("Alojamiento")

        search_keyword = None
        if "cafe" in text or "café" in text or "cafeteria" in text:
            search_keyword = "café"
        elif "cerveza" in text or "cerveceria" in text:
            search_keyword = "cerveza"
        elif "asado" in text or "parrilla" in text:
            search_keyword = "asado"

        # Heredar de contexto SOLO en caso de continuidad legítima sin nueva actividad/tema
        has_new_activity_or_category = bool(has_action_verb or found_categories)
        if is_continuity and not has_new_activity_or_category and ctx:
            if not found_categories and ctx.get("categoriasNombres"):
                found_categories.extend(ctx.get("categoriasNombres", []))
            if not search_keyword and ctx.get("lastSearchKeyword"):
                search_keyword = ctx.get("lastSearchKeyword")

        price: Optional[float] = None
        preferencia_economica = False
        num_price_match = re.search(r"(?:hasta|menos de|presupuesto de|maximo|tope de|\$)\s*\$?\s*([\d\.\,]+)", text)
        if num_price_match:
            try:
                raw_num = num_price_match.group(1).replace(".", "").replace(",", ".")
                price = float(raw_num)
            except ValueError:
                pass

        if any(w in text for w in ["economico", "economica", "barato", "barata", "accesible", "bajo costo"]):
            preferencia_economica = True

        start_date = None
        end_date = None
        now = datetime.now()
        if "mañana" in text:
            days = 1
            dur_match = re.search(r"(\d+)\s*dia", text)
            if dur_match:
                days = int(dur_match.group(1))
            st = now + timedelta(days=1)
            en = st + timedelta(days=max(1, days) - 1)
            start_date = st.strftime('%Y-%m-%d')
            end_date = en.strftime('%Y-%m-%d')
        elif "hoy" in text:
            days = 1
            dur_match = re.search(r"(\d+)\s*dia", text)
            if dur_match:
                days = int(dur_match.group(1))
            st = now
            en = st + timedelta(days=max(1, days) - 1)
            start_date = st.strftime('%Y-%m-%d')
            end_date = en.strftime('%Y-%m-%d')

        search_synonyms = []
        if search_keyword:
            if "vist" in search_keyword or "mirador" in search_keyword:
                search_synonyms = ["vista", "mirador", "panoramica", "paisaje"]
            elif "asado" in search_keyword or "parrilla" in search_keyword:
                search_synonyms = ["asado", "parrilla", "chivito"]
            elif "cerveza" in search_keyword:
                search_synonyms = ["cerveza", "artesanal", "cerveceria"]
            elif "cafe" in search_keyword:
                search_synonyms = ["cafe", "cafeteria", "pasteleria"]
            else:
                search_synonyms = [search_keyword]

        travel_type = None
        if any(w in text for w in ["en pareja", "con mi pareja", "con mi novio", "con mi novia", "con mi esposo", "con mi esposa", "de a dos", "romantico"]):
            travel_type = "Pareja"
        elif any(w in text for w in ["familia", "con mi familia", "familiar", "con los chicos", "con mis hijos"]):
            travel_type = "Familia"
        elif any(w in text for w in ["con amigos", "amigas", "grupo de amigos"]):
            travel_type = "Amigos"
        elif any(w in text for w in ["solo", "sola", "viajo solo", "voy solo", "para mi solo", "solitario"]):
            travel_type = "Solitario"

        travel_mode = None
        if any(w in text for w in ["en auto", "con auto", "coche", "vehiculo propio", "alquiler de auto", "manejando"]):
            travel_mode = "auto"
        elif any(w in text for w in ["a pie", "caminando", "andando"]):
            travel_mode = "pie"
        elif any(w in text for w in ["en bici", "bicicleta", "cicloturismo"]):
            travel_mode = "bicicleta"
        elif any(w in text for w in ["en micro", "colectivo", "transporte publico", "en bus"]):
            travel_mode = "micro"

        itinerary_name = None
        name_match = re.search(r'(?:nombre|llamado|llamalo|titulalo|viaje)\s*[:=]?\s*["\'“]([^"\'“”\n]{3,40})["\'”]', request.message, re.I)
        if name_match:
            itinerary_name = name_match.group(1).strip()
        else:
            name_kw = re.search(r'(?:nombre(?:\s+del\s+viaje)?|llamalo|titulado)\s*[:=]\s*([a-zA-Z0-9áéíóúÁÉÍÓÚñÑ\s]{3,35})', request.message, re.I)
            if name_kw:
                itinerary_name = name_kw.group(1).strip()

        return AssistantExtractResponse(
            is_recommendation=is_rec,
            intent=intent,
            search_keyword=search_keyword,
            search_synonyms=search_synonyms,
            categories=found_categories,
            max_price=price,
            preferencia_economica=preferencia_economica,
            department=ctx.get("departamentoNombre") if (is_continuity and not any(w in text for w in ["lujan", "maipu", "capital"])) else None,
            zone=ctx.get("zonaNombre") if is_continuity else None,
            duration_minutes=None,
            start_date=start_date,
            end_date=end_date,
            people_count=None,
            itinerary_target=None,
            itinerary_name=itinerary_name,
            travel_type=travel_type,
            travel_mode=travel_mode,
            tokens_used=0,
            model_used="heuristic-fallback",
        )
