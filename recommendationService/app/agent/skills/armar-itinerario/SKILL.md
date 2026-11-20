---
name: armar-itinerario
description: Cómo armar un itinerario o plan de viaje completo con lugares reales, la ruta óptima de cada día, reseñas, precios y el PDF listo para descargar. Cárgala cuando el usuario pida un itinerario, un plan de viaje o el PDF de un plan.
---

# Armar un itinerario completo

El resultado es un plan por día con la ruta óptima, las reseñas y los precios de cada lugar, y su PDF listo para descargar. Usa solo datos que devuelvan las tools: nunca inventes lugares, horarios, precios ni opiniones.

## 1. Entiende el pedido
- Toma del mensaje la cantidad de días, los departamentos o zonas, el tipo de lugares, el presupuesto, la hora de salida y la fecha o día de la semana.
- Si falta algo, no preguntes: usa 1 día, salida a las 09:30 y sin presupuesto, y acláralo en una frase de la respuesta.
- Si el usuario solo pide el PDF de un plan que ya armaste en esta conversación, usa esos lugares y sigue desde el paso 3.

## 2. Elige los lugares
- Con sesión iniciada:
  - Si menciona un itinerario guardado, consúltalo con get_user_itinerary_tool (sin `itinerary_id` para listarlos, con `itinerary_id` para el detalle) y úsalo como base.
  - Si pide algo según sus gustos o no da criterios, llama a get_personalized_recommendations_tool y a get_similar_users_recommendations_tool para priorizar lugares.
- Siempre llama a search_pois_tool, una vez por día, con `department`, `category` y `max_price` según el pedido. Los lugares que vengan de itinerarios o recomendaciones búscalos por nombre para tener su id, zona, descripción, precio y horarios.
- Elige de 2 a 4 lugares por día, del mismo departamento salvo que el usuario pida otra cosa. Descarta los que estén cerrados ese día según `horarios` o que superen el presupuesto.

## 3. Revisa las reseñas
- Llama a get_poi_reviews_summary_tool con el id de cada lugar elegido.
- Si un lugar tiene una puntuación baja o pocas opiniones, cámbialo por otro de la búsqueda y revisa sus reseñas.

## 4. Optimiza la ruta de cada día
- Llama a optimize_route_tool una vez por cada día con 2 o más lugares, con sus `poi_ids`, `hora_inicio` igual a la hora de salida (no antes de que abra el primer lugar) y `fecha` si la conoces.
- Si una parada vuelve con `aviso_horario`, reemplaza ese lugar o cambia la hora de salida y vuelve a optimizar ese día una sola vez.
- Si un día tiene un solo lugar, no llames a la tool.

## 5. Genera el PDF
Llama a generar_pdf con:
- `name`: nombre de archivo corto, sin espacios y con extensión .pdf (por ejemplo "itinerario_maipu.pdf").
- `title`: el nombre del plan. `subtitle`: un resumen corto, por ejemplo "2 días en Luján de Cuyo".
- `dias`: un elemento por día, en orden, con un `titulo` sin "Día N" (la plantilla ya lo numera) y sus `lugares` en el orden de la ruta.
- Cada lugar lleva:
  - `nombre`, `zona` y `descripcion` (una o dos oraciones, según la búsqueda). En `zona` pon el departamento y la zona; si la búsqueda trae la zona "General", pon solo el departamento.
  - `precio_desde`: 0 si es gratis, null si no lo sabes.
  - `llegada`, `duracion_min` y `traslado_siguiente_min`, copiados del resultado de optimize_route_tool. Omítelos en los días sin ruta optimizada.
  - `puntuacion` y `cantidad_reviews`, de get_poi_reviews_summary_tool.
  - `resena`: una frase con lo que más destacan las opiniones recientes, con tus palabras. Si no hay opiniones, omítela.
- Escribe en español con tildes y ñ, sin Markdown, enlaces ni emojis: la plantilla no los renderiza.

## 6. Responde
- La app ya muestra debajo de tu respuesta la línea de tiempo de cada día y el botón para descargar el PDF: no listes las paradas ni repitas horarios, precios o puntuaciones.
- Escribe una o dos oraciones por día con la idea del recorrido y lo que más destacan las reseñas, agrega los avisos de horario si los hay y di que el PDF está listo para descargar con el botón. Sin enlaces ni identificadores.
