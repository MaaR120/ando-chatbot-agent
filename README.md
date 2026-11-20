# Ando — Agente turístico de Mendoza

Trabajo Integrador de **Modelos de Lenguaje** (UTN FRM, 2026): un agente de IA construido con
`create_agent` de LangChain. El agente planifica salidas por Mendoza: busca lugares reales en la base
de Ando, ordena la ruta de cada día con un optimizador, consulta opiniones e itinerarios guardados y
genera un **PDF del itinerario**.

```
frontend/              UI web (Next.js) para conversar con el agente
recommendationService/ API (FastAPI) con el agente, sus tools, skills y servicios
  app/agent/           agent.py (create_agent + checkpointer), middleware.py, prompts.py, tools/, skills/
docker-compose.yml     PostgreSQL 16 con los datos de Ando (init.sql)
```

## Requisitos

- Python 3.12 o superior
- Node.js 20 o superior y [pnpm](https://pnpm.io/installation)
- Docker (para la base de datos)
- Una API key de **Anthropic** (Claude) o de **Groq** (tier gratuito)

## Instalación y ejecución

### 1. Variables de entorno

Copiá el ejemplo en la **raíz del repo** y completá la API key del proveedor que vayas a usar:

```bash
cp .env.example .env
```

| Variable | Valor |
|---|---|
| `LLM_PROVIDER` | `anthropic`, `groq` u `openai` |
| `LLM_MODEL` | por ejemplo `claude-haiku-5-5` (Anthropic) o `openai/gpt-oss-120b` (Groq) |
| `ANTHROPIC_API_KEY` / `GROQ_API_KEY` / `OPENAI_API_KEY` | la key del proveedor elegido |
| `DATABASE_URL` | ya apunta al contenedor de `docker-compose.yml` |

Las variables opcionales de límites (`AGENT_MAX_ITERATIONS`, `AGENT_HISTORY_TURNS`, `LLM_MAX_RETRIES`, etc.)
están explicadas en `.env.example`.

### 2. Base de datos

```bash
docker compose up -d
```

La primera vez, Postgres ejecuta `init.sql` (esquema y datos de POIs, horarios, reseñas, usuarios e
itinerarios de prueba). Tarda unos segundos. Para recrearla desde cero: `docker compose down -v` y
de nuevo `docker compose up -d`.

### 3. Backend (agente)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS
pip install -r recommendationService/requirements.txt
cd recommendationService
uvicorn app.main:app --reload --port 8000
```

La documentación de la API queda en http://localhost:8000/docs.

### 4. Frontend

En otra terminal:

```bash
cd frontend
pnpm install
pnpm dev
```

Abrí http://localhost:3000/chat. Si el backend no está en `http://localhost:8000`, definí
`NEXT_PUBLIC_API_URL` en `frontend/.env.local`.

**Cuentas de prueba:** el chat no tiene login real. En el pie de la barra lateral se elige con qué
cuenta conversar; la lista sale de `GET /agent/users`, que devuelve los turistas de la base ordenados
por historial. Las que tienen más valoraciones (por ejemplo, Sol Falabella o Martina Luconi) reciben
recomendaciones personalizadas. Con **"Sin sesión (invitado)"** el agente no tiene las tools
personales y la conversación no se guarda, aunque mantiene la memoria mientras dure el chat.

### 5. Tests

```bash
cd recommendationService
python -m pytest
```

Los tests del agente usan un modelo falso (no gastan tokens). Los de las tools corren contra el
contenedor de Postgres y se omiten si no está levantado.

## Cómo funciona

- **Agente:** `create_agent` (LangChain 1.x) con el system prompt de `prompts.py` y las tools de
  `tools/`. Corre el loop modelo → tools → modelo hasta que el modelo responde sin pedir tools
  (máximo `AGENT_MAX_ITERATIONS` vueltas).
- **Tools:** `search_pois_tool`, `optimize_route_tool` (OR-Tools), `generar_pdf` (fpdf2),
  `load_skill_tool`, `get_poi_reviews_summary_tool`. Si hay sesión, además `get_user_itinerary_tool`,
  `get_personalized_recommendations_tool` y `get_similar_users_recommendations_tool`. El `user_id` lo
  fija el servidor y nunca el modelo.
- **Memoria de corto plazo:** un checkpointer de LangGraph sobre Postgres (`PostgresSaver`, en la
  misma base de `DATABASE_URL`; crea sus tablas al primer uso) guarda el estado completo de cada
  conversación, con sus tool calls y resultados. El `thread_id` es el `conversation_id`. Como vive en
  la base, la memoria sobrevive a reinicios y funciona aunque cada turno lo atienda otra instancia del
  servidor. Las conversaciones también se guardan en Postgres para listarlas en la UI.
- **Conocimiento propio (skills):** archivos `skills/<nombre>/SKILL.md`. El prompt solo lleva el
  catálogo (nombre y descripción) y el agente carga el cuerpo con `load_skill_tool` cuando lo
  necesita. Por ejemplo, `armar-itinerario`, que guía el plan completo: lugares, reseñas, ruta óptima y PDF.
- **Middleware (propio, `middleware.py`):**
  - `tool_errors_as_messages` convierte la excepción de una tool en un mensaje de error que el
    modelo puede leer, en vez de cortar el turno.
  - `trim_history` le manda al modelo solo los últimos `AGENT_HISTORY_TURNS` turnos, sin borrar nada
    del checkpointer.

  No se usa middleware prearmado de LangChain.
- **Razonamiento:** se lee de los bloques estándar `reasoning` de LangChain (`content_blocks`).
  Claude los devuelve con *adaptive thinking* y gpt-oss en Groq también los expone. La UI los muestra
  en un bloque separado de la respuesta.
- **Streaming (visibilidad del flujo):** la UI usa `POST /agent/chat/stream`, que responde con
  Server-Sent Events mientras el agente trabaja (`AndoTouristAgent.stream()` sobre
  `graph.stream(stream_mode=["messages", "updates"])`). Eventos:

  | Evento | Contenido |
  |---|---|
  | `start` | `conversation_id` |
  | `reasoning` | fragmento del razonamiento |
  | `tool_call` | tool, argumentos y motivo |
  | `tool_result` | resultado de la tool |
  | `token` | fragmento de la respuesta |
  | `done` | respuesta final, razonamiento y tools |
  | `error` | mensaje para el usuario |

  Así la UI muestra en vivo y en orden cada tool con sus argumentos y su resultado, el razonamiento
  y la respuesta palabra por palabra. `POST /agent/chat` sigue disponible y devuelve todo junto al
  final.
- **Límites del proveedor:** ante un error 429 el cliente reintenta con espera (`LLM_MAX_RETRIES`).
  Si se agotan los reintentos, la API responde 429 con un mensaje para el usuario.
