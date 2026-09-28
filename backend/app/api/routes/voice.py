"""``/api/voice/*`` — voz de JARKKO.

``POST /api/voice/cache/build`` es la única ruta que puede gastar créditos de
ElevenLabs, y solo la dispara el usuario a propósito.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.api.deps import EngineDep
from app.schemas.voice import (
    CacheBuildResponse,
    ListenControlResponse,
    ListenOnceRequest,
    ListenOnceResponse,
    ListenStatusResponse,
    PhraseCatalogResponse,
    SpeakRequest,
    SpeakResponse,
    VoiceStatusResponse,
)
from app.voice.base import SpeechPlan
from app.voice.listener import ListenerService, get_listener
from app.voice.phrases import PHRASES, catalog, total_characters
from app.voice.recognizer import wake_word_match
from app.voice.service import VoiceService, get_voice_service

router = APIRouter(prefix="/api/voice", tags=["voice"])

VoiceDep = Annotated[VoiceService, Depends(get_voice_service)]
ListenerDep = Annotated[ListenerService, Depends(get_listener)]


@router.get("/status", response_model=VoiceStatusResponse, summary="Estado de la voz")
async def voice_status(voice: VoiceDep) -> VoiceStatusResponse:
    result = await voice.status()
    return VoiceStatusResponse.model_validate(result.to_public())


@router.get("/phrases", response_model=PhraseCatalogResponse, summary="Catálogo de frases fijas")
async def voice_phrases() -> PhraseCatalogResponse:
    return PhraseCatalogResponse(
        total=len(PHRASES), total_characters=total_characters(), phrases=catalog()
    )


@router.post("/speak", response_model=SpeakResponse, summary="Hacer hablar a JARKKO")
async def speak(payload: SpeakRequest, voice: VoiceDep) -> SpeakResponse:
    if payload.phrase_key:
        text = PHRASES.get(payload.phrase_key)
        if text is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "phrase_not_found",
                    "message": f"No existe la frase '{payload.phrase_key}'.",
                },
            )
        plan = SpeechPlan(text=text, phrase_key=payload.phrase_key)
    elif payload.text and payload.text.strip():
        plan = SpeechPlan(text=payload.text.strip(), phrase_key=None)
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "nothing_to_say", "message": "Indica 'text' o 'phrase_key'."},
        )

    audio = await voice.say(plan, play=payload.play)
    if audio is None:
        return SpeakResponse(
            spoken=False,
            text=plan.text,
            phrase_key=plan.phrase_key,
            reason="voice_disabled_or_no_engine",
        )
    return SpeakResponse(
        spoken=True,
        engine=audio.engine,
        voice=audio.voice,
        media_type=audio.media_type,
        cached=audio.cached,
        phrase_key=audio.phrase_key,
        text=audio.text,
        audio_url=voice.audio_url(audio),
        bytes=len(audio.data),
    )


@router.get("/audio/{cache_key}", summary="Descargar un audio cacheado")
async def voice_audio(cache_key: str, voice: VoiceDep) -> FileResponse:
    if not cache_key.isalnum() or len(cache_key) > 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_key", "message": "Clave de audio inválida."},
        )
    path = voice.cache.find_by_path(cache_key)
    if path is None or not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "audio_not_found", "message": "Ese audio no está en el caché."},
        )
    media_type = "audio/mpeg" if path.suffix.lower() == ".mp3" else "audio/wav"
    return FileResponse(path, media_type=media_type, filename=path.name)


# ----------------------------------------------------------------------
# escucha
# ----------------------------------------------------------------------
@router.get("/listen/status", response_model=ListenStatusResponse, summary="Estado de la escucha")
async def listen_status(listener: ListenerDep) -> ListenStatusResponse:
    return ListenStatusResponse.model_validate(listener.status())


@router.get(
    "/microphone/test",
    summary="Medir el nivel del micrófono (diagnóstico)",
)
async def microphone_test(listener: ListenerDep, seconds: float = 2.0) -> dict[str, object]:
    from starlette.concurrency import run_in_threadpool

    limit = max(0.5, min(seconds, 10.0))
    return await run_in_threadpool(listener.microphone.measure_level, limit)


@router.post(
    "/listen/start",
    response_model=ListenControlResponse,
    summary="Activar la escucha manos libres («Jarkko, …»)",
)
async def listen_start(listener: ListenerDep, engine: EngineDep) -> ListenControlResponse:
    async def dispatch(order: str) -> None:
        # La orden hablada entra por el MISMO camino que el texto escrito:
        # intención → plan → Validator → Permission Manager → ejecución.
        await engine.chat(order, assistant="jarkko")

    result = listener.start(dispatch)
    return ListenControlResponse(running=listener.running, **result)


@router.post("/listen/stop", response_model=ListenControlResponse, summary="Desactivar la escucha")
async def listen_stop(listener: ListenerDep) -> ListenControlResponse:
    result = listener.stop()
    return ListenControlResponse(running=listener.running, **result)


@router.post(
    "/listen",
    response_model=ListenOnceResponse,
    summary="Escuchar una vez (grabar, transcribir y opcionalmente ejecutar)",
)
async def listen_once(
    payload: ListenOnceRequest, listener: ListenerDep, engine: EngineDep
) -> ListenOnceResponse:
    result = await listener.listen_once(payload.seconds)
    response = ListenOnceResponse.model_validate(result)
    if not response.heard or not payload.execute:
        return response

    require_wake = (
        listener.status()["wake_word_required"]
        if payload.require_wake_word is None
        else payload.require_wake_word
    )
    wake = wake_word_match(response.text)
    if require_wake and not wake.matched:
        response.reason = "no_wake_word"
        return response

    order = wake.command if wake.matched else response.text
    if not order:
        response.reason = "empty_command"
        return response

    outcome = await engine.chat(order, assistant="jarkko")
    response.executed = True
    response.chat = outcome.to_public()
    return response


@router.post(
    "/cache/build",
    response_model=CacheBuildResponse,
    summary="Generar el caché de frases con la voz de identidad (gasta créditos una vez)",
)
async def build_cache(voice: VoiceDep, only_missing: bool = True) -> CacheBuildResponse:
    report = await voice.build_phrase_cache(only_missing=only_missing)
    return CacheBuildResponse.model_validate(report)
