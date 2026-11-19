from app.agent.tools import pdf as pdf_tool
from app.agent.tools.pdf import Dia, Lugar, PdfInput, _draw_lugar_entero, formatear_precio, render_itinerario

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
