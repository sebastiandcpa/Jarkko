"""Punto de entrada de la API de JARVIS - EKKO.

    uvicorn app.main:app --host 127.0.0.1 --port 8765
    python -m app.main
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import actions, activity, chat, files, health, system, tools, voice
from app.api.websocket import router as websocket_router, system_status_broadcaster
from app.agent.engine import get_engine
from app.config import Settings, get_settings
from app.database.db import get_database
from app.security.validator import ValidationError
from app.services.confirmations import ConfirmationError
from app.tools.bootstrap import get_registry
from app.voice.listener import get_listener
from app.voice.player import audio_player
from app.voice.service import get_voice_service

logger = logging.getLogger("jarvis")

DESCRIPTION = """
Backend de **JARKKO**, el asistente de escritorio (proyecto JARVIS - EKKO).

La IA nunca accede a PowerShell, CMD ni al sistema operativo: solo puede solicitar
herramientas registradas, que pasan por validación, política de riesgo y
verificación posterior.

Una sola identidad: **JARKKO**. Los nombres `jarvis` y `ekko` se aceptan como
alias históricos y resuelven al mismo asistente y al mismo motor.

JARKKO habla: voz de identidad (ElevenLabs, servida desde caché) con respaldo en
la voz local de Windows, gratis e ilimitada.
"""


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)

    get_database()  # crea el archivo SQLite y el esquema
    registry = get_registry()
    engine = get_engine()
    logger.info(
        "JARKKO %s listo · %d herramientas · proveedor de IA: %s",
        settings.version,
        len(registry),
        engine.provider.name,
    )

    voice_service = get_voice_service()
    voice_status = await voice_service.status()
    active = [item["name"] for item in voice_status.engines if item.get("available")]
    logger.info("Voz: %s", " → ".join(active) if active else "desactivada")

    listener = get_listener()
    if settings.stt_autostart:
        started = listener.start(lambda order: engine.chat(order, assistant="jarkko"))
        if started.get("started"):
            logger.info(
                "Escucha manos libres activa · di «%s, …» para dar órdenes", settings.wake_word
            )
        else:
            logger.warning("No pude activar la escucha: %s", started)
    else:
        logger.info("Escucha desactivada (POST /api/voice/listen/start para encenderla)")

    broadcaster = asyncio.create_task(system_status_broadcaster())
    try:
        yield
    finally:
        listener.stop()
        broadcaster.cancel()
        try:
            await broadcaster
        except asyncio.CancelledError:
            pass
        audio_player.cleanup()
        get_database().close()
        logger.info("JARKKO detenido.")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(
        title="JARKKO API",
        description=DESCRIPTION,
        version=settings.version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    for module in (health, system, tools, chat, actions, activity, files, voice):
        app.include_router(module.router)
    app.include_router(websocket_router)

    # ------------------------------------------------------------------
    @app.exception_handler(ValidationError)
    async def _validation_error(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": exc.to_public()})

    @app.exception_handler(ConfirmationError)
    async def _confirmation_error(_: Request, exc: ConfirmationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Error no controlado en %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": {
                    "code": "internal_error",
                    "message": "Error interno del backend. Revisa los logs del servidor.",
                }
            },
        )

    @app.get("/", tags=["health"], summary="Información básica del backend")
    async def root() -> dict[str, object]:
        return {
            "assistant": settings.app_name,
            "version": settings.version,
            "identity": "jarkko",
            "aliases": ["jarvis", "ekko"],
            "docs": "/docs",
            "health": "/api/health",
            "websocket": "/ws/events",
        }

    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
