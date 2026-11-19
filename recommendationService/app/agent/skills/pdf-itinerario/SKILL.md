---
name: pdf-itinerario
description: Cómo armar el contenido de generar_pdf cuando el usuario pide un PDF de un itinerario o de un plan de viaje. Cárgala antes de llamar a generar_pdf.
---

# Generar el PDF de un itinerario o plan de viaje

## 1. Reúne los datos antes de generar
Arma el contenido solo con datos de esta conversación:
- Si el usuario pide el PDF de un itinerario suyo guardado, usa el detalle que devolvió get_user_itinerary_tool. Si todavía no lo consultaste, llama a esa tool primero (sin `itinerary_id` para listarlos, con `itinerary_id` para el detalle).
- Si pide el PDF del plan que propusiste, usa ese plan por día tal como se lo mostraste.
- Si no tienes ninguna de las dos fuentes, consíguelas con la tool correspondiente en vez de inventar lugares.
- La tool de itinerarios solo trae el nombre de cada parada. Para la `zona`, la `descripcion` y el `precio_desde` busca el lugar con search_pois_tool por su nombre y usa lo que devuelve. Si un dato no aparece en ningún resultado, déjalo vacío o usa null en el precio, no lo completes por tu cuenta.

## 2. Arma los argumentos de generar_pdf
- `name`: nombre de archivo corto, sin espacios y con extensión .pdf (por ejemplo "itinerario_maipu.pdf").
- `title`: el nombre del viaje o del plan.
- `subtitle`: un resumen corto (por ejemplo "5 días en Mendoza"). Es opcional.
- `dias`: un elemento por día, en el orden del viaje. Cada día lleva un `titulo` sin "Día N" (la plantilla ya lo numera) y sus `lugares`.
- Cada lugar lleva `nombre`, `zona`, `descripcion` y `precio_desde`: 0 si es gratis, null si no lo sabes.

## 3. Reglas de redacción
- Escribe todos los textos en español con tildes y ñ.
- Sin Markdown, sin enlaces y sin emojis: la plantilla del PDF no los renderiza.
- Descripciones de una o dos oraciones, con lo que ofrece el lugar según los datos de la tool.

## 4. Después de generar
Cuando la tool termine, dile al usuario que el PDF está listo para descargar con el botón debajo del mensaje. No incluyas enlaces ni identificadores del archivo.
