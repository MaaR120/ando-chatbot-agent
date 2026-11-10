"""
Main FastAPI Application Entrypoint.
Ando Recommendation Service (MRIA).
"""
import sys

# En Windows la consola/pipe usa cp1252 por defecto: un print() de texto con caracteres como
# U+202F (espacio fino que suelen emitir los modelos) lanza UnicodeEncodeError y hacía que una
# respuesta válida del LLM se descartara como "error del proveedor". Se fuerza UTF-8 sin fallar.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes_recommendations import router as recommendations_router
from app.api.routes_optimization import router as optimization_router
from app.api.routes_moderation import router as moderation_router
from app.api.routes_assistant import router as assistant_router
from app.api.routes_reviews import router as reviews_router
from app.api.routes_itinerary import router as itinerary_router
from app.api.routes_agent import router as agent_router
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Microservicio de Recomendación e Inteligencia Artificial para Ando (Mendoza).",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclusión de Routers
app.include_router(agent_router)
app.include_router(recommendations_router)
app.include_router(optimization_router)
app.include_router(moderation_router)
app.include_router(assistant_router)
app.include_router(reviews_router)
app.include_router(itinerary_router)




@app.get("/health", tags=["health"])
def health_check():
    """Healthcheck endpoint para orquestación en Docker y Kubernetes."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }


@app.get("/", tags=["root"])
def root():
    return {
        "message": "Bienvenido al Microservicio de Recomendación de Ando",
        "docs": "/docs",
        "health": "/health",
    }
