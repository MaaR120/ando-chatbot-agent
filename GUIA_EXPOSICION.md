# Guión de exposición: Ando

Una sección por diapositiva, con lo que hay que decir. Al final, las preguntas probables de la defensa.

## 1. Portada

- Ando es un agente que planifica una salida por Mendoza y la entrega en PDF.
- Está hecho con LangChain `create_agent` y Claude Haiku 5.5, con FastAPI, Next.js y PostgreSQL.
- Vamos a recorrer los 6 criterios de la consigna y terminar con la demo.

## 2. Caso de uso y agente

- **Caso de uso:** un turista arma su viaje sobre la base real de Ando, que tiene lugares con precios, horarios, coordenadas y reseñas.
- **Varios pasos:** carga la skill, busca, revisa reseñas, optimiza la ruta y genera el PDF. El PDF es el resultado tangible.
- **Dominio acotado:** el bloque `<alcance>` del prompt rechaza los temas ajenos.
- **Agente:** `create_agent` arma un grafo con un nodo model y un nodo tools. Va de uno a otro hasta que el modelo responde sin pedir tools. No usa Deep Agents.
- **Modelo:** elegimos Haiku porque hace tool calling robusto con schemas anidados y devuelve su razonamiento. Groq es la alternativa gratis.
- **429:** el cliente reintenta 6 veces con espera y, si no alcanza, muestra un mensaje amigable.

## 3. Tools

- Son 8 tools, todas propias. **El modelo decide y las tools hacen.**
- `search_pois` trae lugares reales; sin ella, el modelo inventaría.
- `optimize_route` resuelve el ruteo con OR-Tools; un LLM lo haría a ojo.
- `get_poi_reviews_summary` descarta lugares mal puntuados.
- `generar_pdf` entrega el resultado.
- Las 3 tools personales solo existen con sesión, y el `user_id` lo fija el servidor, nunca el modelo.
- **Errores:** las validaciones devuelven `{"error"}` y el modelo se corrige. Si una tool falla, el middleware lo devuelve como mensaje en lugar de cortar el turno.

## 4. Conocimiento propio: skills

- **Skills en lugar de RAG:** los datos ya están en SQL y se consultan con filtros exactos, así que vectorizarlos no suma. Lo que el modelo no sabe es el procedimiento de Ando, y eso es una skill.
- La skill `armar-itinerario` tiene 6 pasos y encadena todas las tools: entender el pedido, elegir lugares, revisar reseñas, optimizar cada día, generar el PDF y responder corto.
- Al prompt solo entra una línea por skill. El cuerpo (unos 900 tokens) entra cuando el usuario pide un itinerario.

## 5. Memoria, interfaz y flujo

- **Memoria:** `PostgresSaver` guarda el estado completo por `thread_id`, con mensajes, tool calls y resultados.
  - Pasamos de `InMemorySaver` a `PostgresSaver` porque en Vercel cada turno puede caer en otra instancia.
  - `trim_history` le manda al modelo solo los últimos 5 turnos.
- **Streaming:** con SSE llegan en vivo el razonamiento, cada tool con sus argumentos y su resultado, y los tokens.
- **Interfaz:** la ruta se muestra como línea de tiempo con llegada, duración, traslados, precio y puntuación, y tiene el botón del PDF.

## 6. Repositorio

- El proyecto se levanta siguiendo el README: `.env`, `docker compose`, backend, frontend.
- `.env.example` no tiene claves y los datos son reproducibles con `init.sql`.
- Hay 100 tests que usan un modelo falso, así que no gastan tokens.

## 7. Demo, limitaciones y mejoras

1. Pedir: «Armame un día con 3 bodegas en Luján de Cuyo, hasta 40.000 pesos». Mostrar el razonamiento, las tools en orden y la línea de tiempo.
2. Pedir: «Cambiá la segunda por otra con mejor puntuación». Así se ve la memoria: reusa los lugares, reoptimiza y genera el PDF de nuevo.
3. Descargar y abrir el PDF.

**Limitaciones y mejoras:**
- Los PDFs se guardan en disco; habría que pasarlos a Vercel Blob.
- No hay login real.
- Los traslados son estimados.
- No conoce la ubicación del usuario.
- Propone itinerarios, pero no los guarda en la app.

## Preguntas probables

- **¿Por qué el `user_id` no es un argumento de las tools?** Porque el modelo podría inventarlo, o un prompt injection podría pedir datos de otro usuario. Se fija desde el servidor con una closure.
- **¿Cómo evitan alucinaciones?** El bloque `<veracidad>` exige usar solo datos de tools. Si un dato no aparece en el historial recortado, el modelo vuelve a consultar la tool en vez de corregirse.
- **¿Qué hace `create_agent` por dentro?** Si el último mensaje del modelo trae tool calls, va al nodo tools; si no, termina. El checkpointer guarda el estado después de cada paso.
- **¿Para qué sirven los modos `messages` y `updates` del stream?** `messages` da el texto token por token y `updates` da cada tool call con su resultado completo.
- **¿Por qué no usaron middleware prearmado?** `SummarizationMiddleware` gasta otra llamada al LLM. Recortar por turnos es gratis y determinista.
- **¿Qué pasa si se reinicia el servidor?** Nada, porque el estado está en Postgres.
- **¿Cómo llega el PDF al usuario?** La tool devuelve un `file_id`, que es un UUID validado, y la UI arma el link a `/agent/pdfs/{file_id}`.
