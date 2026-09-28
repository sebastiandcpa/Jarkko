"""``GET /api/health`` — comprobación de vida y configuración efectiva."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import EngineDep, SettingsDep, uptime_seconds
from app.schemas.system import HealthResponse
from app.services.assistants import ALIASES, assistant_catalog
from app.voice.service import get_voice_service

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse, summary="Estado del backend")
async def health(engine: EngineDep, settings: SettingsDep) -> HealthResponse:
    voice = get_voice_service()
    voice_engines = [item for item in (engine_info.describe() for engine_info in voice.engines)]
    return HealthResponse(
        status="ok",
        assistant=settings.app_name,
        version=settings.version,
        assistants=assistant_catalog(),
        aliases=sorted(ALIASES),
        voice={
            "enabled": voice.enabled,
            "engines": [item["name"] for item in voice_engines if item.get("available")],
            "identity_voice_configured": settings.has_elevenlabs,
            "cached_phrases": len(voice.cache.stats().get("phrases_cached", [])),
            "autospeak": settings.tts_autospeak,
        },
        ai_provider=engine.provider.describe(),
        tools_registered=len(engine.registry),
        confirmation_threshold=settings.confirmation_threshold.value,
        critical_tools_enabled=settings.enable_critical_tools,
        websocket="/ws/events",
        uptime_seconds=uptime_seconds(),
    )
