"""VoiceService: decide qué dice JARKKO, con qué motor y cuándo.

Cadena de motores (configurable con ``JARVIS_TTS_ENGINE``):

1. **elevenlabs** — la voz de identidad, solo si la frase está en caché;
2. **windows** — Microsoft Raul, gratis, offline e ilimitada.

Si el primero no puede (no hay clave, o la frase no está cacheada), el segundo
habla igual: JARKKO nunca se queda mudo por falta de cuota.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.config import Settings, get_settings
from app.services.events import EventBus, EventType, event_bus
from app.voice.base import (
    CacheMiss,
    SpeechAudio,
    SpeechPlan,
    TTSError,
    TTSProvider,
    VoiceStatus,
)
from app.voice.cache import AudioCache
from app.voice.elevenlabs import ElevenLabsTTS
from app.voice.phrases import (
    PHRASES,
    SPOKEN_DYNAMIC_TOOLS,
    phrase,
    phrase_for_action,
    total_characters,
)
from app.voice.player import AudioPlayer, audio_player
from app.voice.windows_tts import WindowsTTS
from app.utils.text import truncate

logger = logging.getLogger(__name__)


class VoiceService:
    """Orquestador de la voz."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        cache: AudioCache | None = None,
        engines: Sequence[TTSProvider] | None = None,
        player: AudioPlayer | None = None,
        events: EventBus | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self.cache = cache or AudioCache(self._settings.voice_cache_dir)
        self._player = player or audio_player
        self._events = events or event_bus
        self._engines = list(engines) if engines is not None else self._build_engines()
        self._last_spoken: dict[str, Any] | None = None
        self._tasks: set[asyncio.Task[Any]] = set()
        # JARKKO no se habla encima: las locuciones se reproducen de una en una.
        # La espera ocurre aquí (en async) para que ``duration_ms`` mida solo el
        # audio y no el tiempo en cola.
        self._play_lock = asyncio.Lock()
        # Mientras JARKKO habla, el micrófono debe ignorarse: si no, se oye a sí
        # mismo por los altavoces y se responde solo.
        self._speaking = False

    # ------------------------------------------------------------------
    def _build_engines(self) -> list[TTSProvider]:
        choice = self._settings.tts_engine.strip().lower()
        elevenlabs = ElevenLabsTTS(self._settings, self.cache)
        windows = WindowsTTS(self._settings)
        match choice:
            case "none":
                return []
            case "windows":
                return [windows]
            case "elevenlabs":
                return [elevenlabs]
        # auto: identidad primero (si está configurada), voz local siempre detrás
        return ([elevenlabs] if elevenlabs.configured else []) + [windows]

    @property
    def engines(self) -> list[TTSProvider]:
        return list(self._engines)

    @property
    def enabled(self) -> bool:
        return self._settings.tts_enabled and bool(self._engines)

    @property
    def speaking(self) -> bool:
        """``True`` mientras suena una locución (el oyente ignora el micro)."""

        return self._speaking

    @property
    def elevenlabs(self) -> ElevenLabsTTS | None:
        return next((e for e in self._engines if isinstance(e, ElevenLabsTTS)), None)

    # ------------------------------------------------------------------
    # planificación de lo que se dice
    # ------------------------------------------------------------------
    def plan_for_chat(
        self,
        *,
        chat_status: str,
        reply: str,
        actions: Sequence[Any] = (),
        intent_rule: str | None = None,
        needs_clarification: bool = False,
    ) -> SpeechPlan | None:
        """Traduce una respuesta del agente a lo que conviene decir en voz alta.

        Lo escrito y lo hablado no son lo mismo: en pantalla va la ruta completa,
        en voz va una frase corta y fija (que es la que suena con la voz de
        identidad, gratis, desde el caché).
        """

        if chat_status == "awaiting_confirmation":
            return self.phrase_plan("confirm.required")

        if not actions:
            if needs_clarification:
                # Si el motor explicó QUÉ falló («no encuentro la carpeta X»), se dice
                # eso con la voz local (gratis, ilimitada).  La frase fija genérica
                # queda solo para cuando no hay nada concreto que explicar.
                if intent_rule and intent_rule.startswith("unresolved:"):
                    return self._dynamic_plan(reply)
                return self.phrase_plan("no_understand")
            if intent_rule == "empty":
                return self.phrase_plan("empty")
            if intent_rule == "smalltalk":
                return self.phrase_plan("capabilities")
            return self._dynamic_plan(reply)

        if len(actions) == 1:
            return self._plan_for_single_action(actions[0], reply)

        all_ok = all(getattr(action, "succeeded", False) for action in actions)
        return self.phrase_plan("ack.generic" if all_ok else "error.generic")

    def _plan_for_single_action(self, action: Any, reply: str) -> SpeechPlan | None:
        tool = str(getattr(action, "tool", ""))
        status = getattr(action, "status", None)
        if tool in SPOKEN_DYNAMIC_TOOLS and getattr(action, "succeeded", False):
            # Aquí el dato ES la respuesta: se lee en voz alta con la voz local.
            return self._dynamic_plan(reply)

        data = getattr(action, "data", {}) or {}
        found = bool(data.get("total")) if tool == "search_files" else None
        key = phrase_for_action(tool, status, found_results=found) if status is not None else None
        if key is None:
            return self._dynamic_plan(reply)
        return self.phrase_plan(key)

    def phrase_plan(self, key: str) -> SpeechPlan | None:
        """Plan de locución para una frase fija del catálogo."""

        text = phrase(key)
        if not text:
            return None
        return SpeechPlan(text=text, phrase_key=key)

    def _dynamic_plan(self, text: str) -> SpeechPlan | None:
        cleaned = (text or "").strip()
        if not cleaned:
            return None
        return SpeechPlan(text=truncate(cleaned, self._settings.tts_max_characters), phrase_key=None)

    # ------------------------------------------------------------------
    # síntesis y reproducción
    # ------------------------------------------------------------------
    async def say(self, plan: SpeechPlan | str, *, play: bool | None = None) -> SpeechAudio | None:
        if isinstance(plan, str):
            built = self._dynamic_plan(plan)
            if built is None:
                return None
            plan = built
        if not self.enabled:
            return None

        audio = await self.synthesize(plan)
        if audio is None:
            return None

        self._events.publish(
            EventType.ASSISTANT_SPEAKING,
            {
                "text": audio.text,
                "engine": audio.engine,
                "voice": audio.voice,
                "cached": audio.cached,
                "phrase_key": audio.phrase_key,
                "audio_url": self.audio_url(audio),
            },
        )

        should_play = self._settings.tts_playback if play is None else play
        duration_ms: int | None = None
        if should_play:
            async with self._play_lock:
                self._speaking = True
                started = time.perf_counter()
                try:
                    await run_in_threadpool(
                        self._player.play, audio.data, audio.media_type, path=audio.path
                    )
                    duration_ms = int((time.perf_counter() - started) * 1000)
                finally:
                    # Margen extra: el eco de los altavoces tarda en apagarse.
                    await asyncio.sleep(0.35)
                    self._speaking = False

        self._last_spoken = {
            "text": audio.text,
            "engine": audio.engine,
            "voice": audio.voice,
            "cached": audio.cached,
            "phrase_key": audio.phrase_key,
            "played": bool(should_play),
            "duration_ms": duration_ms,
        }
        self._events.publish(EventType.ASSISTANT_SPOKEN, dict(self._last_spoken))
        return audio

    async def synthesize(self, plan: SpeechPlan) -> SpeechAudio | None:
        """Recorre la cadena de motores hasta que uno produzca audio."""

        if not self.enabled:
            return None
        problems: list[str] = []
        for engine in self._engines:
            try:
                audio = await engine.synthesize(plan)
            except CacheMiss as exc:
                problems.append(f"{engine.name}: {exc}")
                continue
            except TTSError as exc:
                problems.append(f"{engine.name}: {exc}")
                logger.warning("Motor de voz '%s' no disponible: %s", engine.name, exc)
                continue
            except Exception:  # noqa: BLE001 - la voz nunca debe tumbar una respuesta
                logger.exception("Fallo inesperado en el motor de voz '%s'", engine.name)
                continue

            # Las frases fijas se cachean también con la voz local: ahorra CPU y
            # le da al frontend una URL estable que reproducir.
            if plan.cacheable and not audio.cached:
                key = self.cache.key(
                    engine=audio.engine, voice=audio.voice, model="", text=plan.text
                )
                audio = self.cache.put(key, audio)
            return audio

        if problems:
            logger.info("Ningún motor de voz pudo hablar: %s", " | ".join(problems))
        return None

    def say_later(self, plan: SpeechPlan | None) -> None:
        """Habla sin bloquear la respuesta HTTP (fire-and-forget)."""

        if plan is None or not self.enabled or not self._settings.tts_autospeak:
            return
        try:
            task = asyncio.create_task(self._say_guarded(plan))
        except RuntimeError:  # pragma: no cover - sin bucle en marcha
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _say_guarded(self, plan: SpeechPlan) -> None:
        try:
            await self.say(plan)
        except Exception:  # noqa: BLE001
            logger.exception("Fallo al hablar")

    # ------------------------------------------------------------------
    @staticmethod
    def audio_url(audio: SpeechAudio) -> str | None:
        """URL estable del audio cacheado, para que el frontend lo reproduzca."""

        return f"/api/voice/audio/{audio.cache_key}" if audio.cache_key else None

    # ------------------------------------------------------------------
    async def build_phrase_cache(self, *, only_missing: bool = True) -> dict[str, Any]:
        """Genera el catálogo de frases con la voz de identidad.  **Gasta créditos.**"""

        elevenlabs = self.elevenlabs or ElevenLabsTTS(self._settings, self.cache)
        if not elevenlabs.configured:
            return {
                "ok": False,
                "reason": "elevenlabs_not_configured",
                "message": (
                    "Falta JARVIS_ELEVENLABS_API_KEY en backend/.env. "
                    "Sin ella JARKKO sigue hablando con la voz local."
                ),
                "phrases": [],
            }

        results: list[dict[str, Any]] = []
        generated = characters = 0
        for key, text in sorted(PHRASES.items()):
            cache_key = elevenlabs.cache_key(text)
            if only_missing and self.cache.get(cache_key) is not None:
                results.append({"phrase": key, "status": "already_cached", "characters": 0})
                continue
            try:
                await elevenlabs.generate_and_cache(text, phrase_key=key)
            except TTSError as exc:
                results.append({"phrase": key, "status": "failed", "error": str(exc)})
                continue
            generated += 1
            characters += len(text)
            results.append({"phrase": key, "status": "generated", "characters": len(text)})

        failures = [item for item in results if item["status"] == "failed"]
        return {
            "ok": not failures,
            "generated": generated,
            "characters_spent": characters,
            "catalog_characters": total_characters(),
            "failed": len(failures),
            "phrases": results,
            "subscription": await elevenlabs.subscription(),
        }

    # ------------------------------------------------------------------
    async def status(self) -> VoiceStatus:
        engines: list[dict[str, Any]] = []
        for engine in self._engines:
            info = engine.describe()
            info["position"] = len(engines) + 1
            engines.append(info)

        identity: dict[str, Any] = {"configured": False}
        elevenlabs = self.elevenlabs
        if elevenlabs is not None:
            identity = {
                "configured": elevenlabs.configured,
                "voice_id": elevenlabs.voice_id,
                "model": elevenlabs.model,
                "live_synthesis_allowed": self._settings.elevenlabs_allow_live,
            }
            if elevenlabs.configured:
                identity["voice_check"] = await elevenlabs.voice_check()
                identity["subscription"] = await elevenlabs.subscription()

        stats = self.cache.stats()
        stats["catalog_phrases"] = len(PHRASES)
        stats["catalog_characters"] = total_characters()
        return VoiceStatus(
            enabled=self.enabled,
            autospeak=self._settings.tts_autospeak,
            playback=self._settings.tts_playback,
            engines=engines,
            cache=stats,
            identity_voice=identity,
            last_spoken=self._last_spoken,
        )


_voice_service: VoiceService | None = None


def get_voice_service() -> VoiceService:
    global _voice_service
    if _voice_service is None:
        _voice_service = VoiceService()
    return _voice_service


def reset_voice_service() -> None:
    """Fuerza la reconstrucción del servicio.  Uso en tests y al recargar config."""

    global _voice_service
    _voice_service = None
