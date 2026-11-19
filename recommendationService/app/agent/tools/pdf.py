"""
LangChain Tool for transforming User Itineraries and Travel Plans into PDFs
files.
"""

import uuid
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import MethodReturnValue, XPos, YPos
from langchain_core.tools import tool
from pydantic import BaseModel, Field

FONTS_DIR = Path(__file__).parent / "fonts"
PDF_DIR = Path(__file__).resolve().parents[3] / "generated_pdfs"

ACCENT = (122, 31, 52)
ACCENT_SOFT = (240, 214, 220)
INK = (33, 33, 33)
GREY = (115, 115, 115)
WHITE = (255, 255, 255)

BAND_PAD = 14
TITLE_LINE = 10
PRICE_W = 38
DAY_KEEP = 45  # alto mínimo para no dejar un encabezado de día solo al pie


class Lugar(BaseModel):
    nombre: str = Field(description="Nombre del lugar")
    zona: str = Field(description="Departamento y zona, por ejemplo 'Maipú, zona Coquimbito'")
    descripcion: str = Field(description="Descripción breve del lugar")
    precio_desde: int | None = Field(
        default=None, description="Precio mínimo en ARS. 0 si es gratis, null si no se conoce"
    )


class Dia(BaseModel):
    titulo: str = Field(description="Título del día, sin 'Día N', por ejemplo 'Maipú: bodegas y olivos'")
    lugares: list[Lugar]


class PdfInput(BaseModel):
    name: str = Field(description="Nombre de archivo corto, sin espacios y con extensión .pdf, por ejemplo 'itinerario_maipu.pdf'")
    title: str = Field(description="Título del documento")
    subtitle: str | None = Field(default=None, description="Subtítulo breve, por ejemplo '5 días en Mendoza'")
    dias: list[Dia] = Field(description="Días del plan, en orden")


class ItineraryPdf(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font("DejaVu", size=8)
        self.set_text_color(*GREY)
        self.cell(0, 10, text="Ando")
        self.set_x(self.l_margin)
        self.cell(0, 10, text=f"Página {self.page_no()}/{{nb}}", align="R")


def formatear_precio(precio: int | None) -> str:
    if precio is None:
        return ""
    if precio == 0:
        return "Gratis"
    return f"desde ${precio:,}".replace(",", ".")


def _draw_portada(pdf: FPDF, title: str, subtitle: str | None) -> None:
    pdf.set_font("DejaVu", style="B", size=22)
    lines = pdf.multi_cell(pdf.epw, TITLE_LINE, text=title, dry_run=True, output=MethodReturnValue.LINES)
    alto = 2 * BAND_PAD + len(lines) * TITLE_LINE + (8 if subtitle else 0)
    pdf.set_fill_color(*ACCENT)
    pdf.rect(0, 0, pdf.w, alto, style="F")
    pdf.set_xy(pdf.l_margin, BAND_PAD)
    pdf.set_text_color(*WHITE)
    pdf.multi_cell(0, TITLE_LINE, text=title, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if subtitle:
        pdf.set_font("DejaVu", size=12)
        pdf.set_text_color(*ACCENT_SOFT)
        pdf.multi_cell(0, 8, text=subtitle, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_y(alto + 6)


def _draw_encabezado_dia(pdf: FPDF, numero: int, titulo: str) -> None:
    if pdf.will_page_break(DAY_KEEP):
        pdf.add_page()
    pdf.ln(4)
    etiqueta = f"Día {numero}"
    pdf.set_font("DejaVu", style="B", size=9)
    pdf.set_fill_color(*ACCENT)
    pdf.set_text_color(*WHITE)
    pdf.cell(pdf.get_string_width(etiqueta) + 6, 7, text=etiqueta, fill=True, align="C")
    pdf.set_x(pdf.get_x() + 3)
    pdf.set_font("DejaVu", style="B", size=14)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 7, text=titulo, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*ACCENT_SOFT)
    pdf.line(pdf.l_margin, pdf.get_y() + 2, pdf.l_margin + pdf.epw, pdf.get_y() + 2)
    pdf.ln(5)


def _draw_lugar(pdf: FPDF, lugar: Lugar) -> None:
    top = pdf.get_y()
    pdf.set_font("DejaVu", style="B", size=11)
    pdf.set_text_color(*INK)
    pdf.multi_cell(pdf.epw - PRICE_W, 6, text=lugar.nombre, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    bottom = pdf.get_y()
    pdf.set_xy(pdf.l_margin + pdf.epw - PRICE_W, top)
    pdf.set_font("DejaVu", style="B", size=10)
    pdf.set_text_color(*ACCENT)
    pdf.cell(PRICE_W, 6, text=formatear_precio(lugar.precio_desde), align="R")
    pdf.set_xy(pdf.l_margin, bottom)
    pdf.set_font("DejaVu", size=9)
    pdf.set_text_color(*GREY)
    pdf.multi_cell(0, 5, text=lugar.zona, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)
    pdf.set_font("DejaVu", size=10)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 5.5, text=lugar.descripcion, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)


def _draw_lugar_entero(pdf: FPDF, lugar: Lugar) -> None:
    with pdf.offset_rendering() as prueba:
        _draw_lugar(prueba, lugar)
    if prueba.page_break_triggered:
        pdf.add_page()
    _draw_lugar(pdf, lugar)


def render_itinerario(data: PdfInput) -> FPDF:
    pdf = ItineraryPdf()
    pdf.add_font("DejaVu", "", FONTS_DIR / "DejaVuSans.ttf")
    pdf.add_font("DejaVu", "B", FONTS_DIR / "DejaVuSans-Bold.ttf")
    pdf.set_auto_page_break(True, margin=20)
    pdf.add_page()
    _draw_portada(pdf, data.title, data.subtitle)
    for numero, dia in enumerate(data.dias, start=1):
        _draw_encabezado_dia(pdf, numero, dia.titulo)
        for lugar in dia.lugares:
            _draw_lugar_entero(pdf, lugar)
    return pdf


@tool(args_schema=PdfInput)
def generar_pdf(name: str, title: str, dias: list[Dia], subtitle: str | None = None) -> dict:
    """Crea un PDF con el plan de viaje: título, subtítulo y los lugares de cada día. Los textos van en español con tildes y ñ, sin Markdown, enlaces ni emojis."""
    PDF_DIR.mkdir(exist_ok=True)
    file_id = str(uuid.uuid4())
    data = PdfInput(name=name, title=title, subtitle=subtitle, dias=dias)
    render_itinerario(data).output(PDF_DIR / f"{file_id}.pdf")
    return {"file_id": file_id, "filename": name}
