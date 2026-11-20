from app.agent.tools import pdf as pdf_tool
from app.agent.tools.pdf import Dia, Lugar, PdfInput, _draw_lugar_entero, formatear_duracion, formatear_precio, formatear_puntuacion, render_itinerario

LUGAR = Lugar(
    nombre="Casa Vigil - Bodega El Enemigo",
    zona="Maipú, zona Russell y Cruz de Piedra",
    descripcion="Universo enogastronómico creado por el enólogo Alejandro Vigil. " * 3,
    precio_desde=45000,
)


def test_formatear_precio_usa_gratis_y_separador_de_miles():
    assert formatear_precio(0) == "Gratis"
    assert formatear_precio(45000) == "desde $45.000"
    assert formatear_precio(None) == ""


def test_lugar_que_no_entra_empieza_en_pagina_siguiente():
    pdf = render_itinerario(PdfInput(name="x.pdf", title="T", dias=[]))
    pdf.set_y(pdf.h - 35)
    _draw_lugar_entero(pdf, LUGAR)
    assert pdf.page == 2
    assert pdf.get_y() < 80


def test_generar_pdf_escribe_archivo_multipagina(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_tool, "PDF_DIR", tmp_path)
    titulo = "Plan de 5 días en Mendoza: bodegas, montaña y buena cocina regional"
    dias = [Dia(titulo=f"Día de prueba {i}", lugares=[LUGAR] * 3).model_dump() for i in range(5)]
    result = pdf_tool.generar_pdf.invoke({"name": "plan.pdf", "title": titulo, "subtitle": "5 días", "dias": dias})
    path = tmp_path / f"{result['file_id']}.pdf"
    assert result["filename"] == "plan.pdf"
    assert path.read_bytes().startswith(b"%PDF")
    assert render_itinerario(PdfInput(name="x", title=titulo, dias=[Dia(**d) for d in dias])).pages_count > 1


def test_formatear_duracion_en_horas_y_minutos():
    assert formatear_duracion(45) == "45 min"
    assert formatear_duracion(180) == "3 h"
    assert formatear_duracion(90) == "1 h 30"


def test_solo_los_dias_con_horarios_se_dibujan_como_linea_de_tiempo(monkeypatch):
    hitos = []
    original = pdf_tool._draw_hito
    monkeypatch.setattr(pdf_tool, "_draw_hito", lambda pdf, lugar, *a: (hitos.append(lugar.llegada), original(pdf, lugar, *a)))
    con_horario = LUGAR.model_copy(update={"llegada": "09:00", "duracion_min": 90, "traslado_siguiente_min": 20})
    ultimo = con_horario.model_copy(update={"llegada": "11:00", "traslado_siguiente_min": None})
    dias = [Dia(titulo="Maipú", lugares=[con_horario, ultimo]), Dia(titulo="Ciudad", lugares=[LUGAR])]
    render_itinerario(PdfInput(name="x.pdf", title="T", dias=dias))
    assert set(hitos) == {"09:00", "11:00"}


def test_formatear_puntuacion_con_y_sin_opiniones():
    assert formatear_puntuacion(4.8, 550) == "★ 4,8 · 550 opiniones"
    assert formatear_puntuacion(5.0, 1) == "★ 5,0 · 1 opinión"
    assert formatear_puntuacion(None, 10) == ""
