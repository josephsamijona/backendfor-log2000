"""
FastAPI Backend — Load Test Dashboard
Bridge entre le frontend React et le moteur Locust.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from api.routes import router as api_router
from api.websockets import router as ws_router
from api.auth import router as auth_router
from core.logger import get_logger
from core.database import connect_to_mongo, close_mongo_connection
from core.config import settings

logger = get_logger("app")

TEMPLATES_DIR = Path(__file__).parent / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Démarrage du Backend LoadTest API")
    await connect_to_mongo()
    yield
    close_mongo_connection()
    logger.info("Arrêt du Backend LoadTest API")


app = FastAPI(title="LoadTest Dashboard API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclusion des routeurs
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(api_router, prefix="/api")
app.include_router(ws_router)


@app.get("/test", response_class=HTMLResponse)
async def test_dashboard():
    """Sert la page HTML du dashboard de test E2E."""
    html_file = TEMPLATES_DIR / "test_dashboard.html"
    return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
