import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path

from app.api.routes import agent, health, knowledge_sources
from app.core.config import get_settings
from app.database.db import init_database
from app.services.tts_service import TTSService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    settings = get_settings()
    tts = TTSService(settings.kokoro_model_path, settings.kokoro_voices_path, settings.kokoro_voice)
    agent.set_tts_service(tts)
    yield


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Secure pgvector-backed APMS navigation and conversation API.",
    lifespan=lifespan,
)
app.include_router(health.router)
app.include_router(agent.router, prefix=settings.api_prefix)
app.include_router(knowledge_sources.router, prefix=settings.api_prefix)


@app.get("/", include_in_schema=False)
def chat_ui() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent / "static" / "chat.html")


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception):
    logging.getLogger(__name__).exception("Unhandled API error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "An internal error occurred."})
