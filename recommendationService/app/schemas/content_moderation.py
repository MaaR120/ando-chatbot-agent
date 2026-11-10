"""
Pydantic schemas for US-MRIA-10 Content Moderation with AI / LLM.
Ando Recommendation & Routing Service (MRIA).
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class ModerationRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000, description="Texto de la reseña o comentario a moderar")
    entity_type: str = Field(default="review", description="Tipo de contenido: 'review' (turista) o 'response' (prestador)")
    user_id: Optional[str] = Field(default=None, description="UUID del autor del contenido")
    poi_id: Optional[str] = Field(default=None, description="UUID del POI asociado")


class ModerationResponse(BaseModel):
    requiere_revision: bool = Field(..., description="Indica si el contenido requiere intervención o revisión de un Administrador")
    categoria: Optional[str] = Field(
        default=None,
        description="Categoría de infracción detectada: SPAM_COMERCIAL, ACOSO_HOSTIGAMIENTO, AMENAZAS_VIOLENCIA, CONTENIDO_ENGANOSO, CONTENIDO_SEXUAL, DIVULGACION_DATOS_SENSIBLES o null",
    )
    motivo: Optional[str] = Field(
        default=None,
        description="Explicación clara y concisa del motivo por el cual fue marcado por la IA",
    )
    nivel_confianza: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Nivel de certeza de la detección [0.0 a 1.0]",
    )
    palabras_clave_detectadas: List[str] = Field(
        default_factory=list,
        description="Términos, fragmentos sospechosos o números de contacto detectados",
    )
    modelo_utilizado: str = Field(
        default="gemini-2.0-flash",
        description="Identificador del modelo o motor que procesó el texto",
    )


class ModerationCategoryItem(BaseModel):
    codigo: str
    nombre: str
    descripcion: str
    ejemplo: str
