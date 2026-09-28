"""Voz de identidad: ElevenLabs, servida **desde caché**.

Protección de cuota por diseño: en tiempo de ejecución este motor solo devuelve
audio que ya está en disco.  Gastar créditos es una acción explícita del usuario
(``POST /api/voice/cache/build`` o ``python -m app.voice.build_cache``), o requiere
poner ``JARVIS_ELEVENLABS_ALLOW_LIVE=true`` a conciencia.

Así la voz de JARKKO suena como su voz real sin gasto recurrente: el plan gratuito
son ~10.000 créditos al mes y el catálogo completo de frases fijas cuesta unos
2.000 caracteres **una sola vez**.

La API key se lee de ``JARVIS_ELEVENLABS_API_KEY`` y nunca se registra en logs,
en la base de datos ni en el manifiesto del caché.
"""

from __future__ import annotations

import io
import logging
import wave
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.voice.base import (
    CacheMiss,
    SpeechAudio,
    SpeechPlan,
    TTSError,
    TTSProvider,
    TTSUnavailable,
)
from app.voice.cache import AudioCache

logger = logging.getLogger(__name__)

API_BASE = "https://api.elevenlabs.io/v1"
FALLBACK_OUTPUT_FORMAT = "mp3_44100_128"
PCM_SAMPLE_RATES = {
    "pcm_8000": 8000,
    "pcm_16000": 16000,
    "pcm_22050": 22050,
    "pcm_24000": 24000,
    "pcm_44100": 44100,
}


def _wrap_pcm_in_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Envuelve PCM 16 bits mono en un WAV, para reproducirlo sin dependencias."""

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(pcm)
    return buffer.getvalue()


class ElevenLabsTTS(TTSProvider):
    """Motor de la voz de identidad de JARKKO."""

    name = "elevenlabs"

    def __init__(self, settings: Settings | None = None, cache: AudioCache | None = None) -> None:
        self._settings = settings or get_settings()
        self._cache = cache or AudioCache(self._settings.voice_cache_dir)

    # ------------------------------------------------------------------
    @property
    def voice_id(self) -> str:
        return self._settings.elevenlabs_voice_id.strip()

    @property
    def model(self) -> str:
        return self._settings.elevenlabs_model.strip()

    @property
    def configured(self) -> bool:
        return self._settings.has_elevenlabs and bool(self.voice_id)

    def cache_key(self, text: str) -> str:
        return self._cache.key(engine=self.name, voice=self.voice_id, model=self.model, text=text)

    # ------------------------------------------------------------------
    async def synthesize(self, plan: SpeechPlan) -> SpeechAudio:
        if not self.configured:
            raise TTSUnavailable("ElevenLabs no está configurado (falta API key o voice_id).")

        cached = self._cache.get(self.cache_key(plan.text))
        if cached is not None:
            cached.phrase_key = plan.phrase_key or cached.phrase_key
            return cached

        if not self._settings.elevenlabs_allow_live:
            raise CacheMiss(
                "El texto no está en el caché de ElevenLabs y el gasto en vivo está desactivado."
            )
        return await self.generate_and_cache(plan.text, phrase_key=plan.phrase_key)

    # ------------------------------------------------------------------
    async def generate_and_cache(self, text: str, *, phrase_key: str | None = None) -> SpeechAudio:
        """Llama a la API y guarda el resultado.  **Esto sí consume créditos.**"""

        if not self.configured:
            raise TTSUnavailable("ElevenLabs no está configurado (falta API key o voice_id).")

        output_format = self._settings.elevenlabs_output_format.strip() or FALLBACK_OUTPUT_FORMAT
        try:
            data, media_type = await self._request(text, output_format)
        except TTSError:
            if output_format.startswith("pcm_"):
                logger.warning(
                    "El formato '%s' no está disponible en este plan; reintento con %s.",
                    output_format,
                    FALLBACK_OUTPUT_FORMAT,
                )
                data, media_type = await self._request(text, FALLBACK_OUTPUT_FORMAT)
            else:
                raise

        audio = SpeechAudio(
            data=data,
            media_type=media_type,
            engine=self.name,
            voice=self.voice_id,
            phrase_key=phrase_key,
            text=text,
        )
        return self._cache.put(self.cache_key(text), audio, model=self.model)

    async def _request(self, text: str, output_format: str) -> tuple[bytes, str]:
        url = f"{API_BASE}/text-to-speech/{self.voice_id}"
        payload = {
            "text": text,
            "model_id": self.model,
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.0},
        }
        try:
            async with httpx.AsyncClient(timeout=self._settings.elevenlabs_timeout_seconds) as client:
                response = await client.post(
                    url,
                    params={"output_format": output_format},
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise TTSUnavailable(f"No se pudo contactar con ElevenLabs: {exc}") from exc

        if response.status_code >= 400:
            raise self._error_for(response)

        if output_format in PCM_SAMPLE_RATES:
            return _wrap_pcm_in_wav(response.content, PCM_SAMPLE_RATES[output_format]), "audio/wav"
        return response.content, "audio/mpeg"

    def _headers(self) -> dict[str, str]:
        return {
            "xi-api-key": self._settings.elevenlabs_api_key.strip(),
            "accept": "*/*",
            "content-type": "application/json",
        }

    def _error_for(self, response: httpx.Response) -> TTSError:
        """Traduce el error de la API a algo accionable (sin filtrar la clave)."""

        detail = ""
        try:
            body = response.json()
            detail = str(body.get("detail") or body)[:300]
        except ValueError:
            detail = response.text[:200]

        match response.status_code:
            case 401:
                return TTSUnavailable("ElevenLabs rechazó la API key (401). Revisa JARVIS_ELEVENLABS_API_KEY.")
            case 404:
                return TTSUnavailable(
                    f"ElevenLabs no encuentra la voz '{self.voice_id}' (404). "
                    "Añádela a 'My Voices' en tu cuenta: las voces de la Voice Library "
                    "no funcionan por API hasta que están en tu espacio."
                )
            case 429:
                return TTSUnavailable("Cuota de ElevenLabs agotada o límite de peticiones (429).")
            case 422:
                return TTSError(f"ElevenLabs rechazó la petición (422): {detail}")
        return TTSError(f"ElevenLabs devolvió {response.status_code}: {detail}")

    # ------------------------------------------------------------------
    async def subscription(self) -> dict[str, Any]:
        """Créditos usados y disponibles del plan (para vigilar la cuota)."""

        if not self.configured:
            return {"available": False, "reason": "not_configured"}
        try:
            async with httpx.AsyncClient(timeout=self._settings.elevenlabs_timeout_seconds) as client:
                response = await client.get(f"{API_BASE}/user/subscription", headers=self._headers())
        except httpx.HTTPError as exc:
            return {"available": False, "reason": f"network_error: {exc}"}
        if response.status_code >= 400:
            return {"available": False, "reason": f"http_{response.status_code}"}
        body = response.json()
        used = int(body.get("character_count", 0))
        limit = int(body.get("character_limit", 0))
        return {
            "available": True,
            "tier": body.get("tier"),
            "characters_used": used,
            "characters_limit": limit,
            "characters_left": max(limit - used, 0),
            "resets_at": body.get("next_character_count_reset_unix"),
        }

    async def voice_check(self) -> dict[str, Any]:
        """Comprueba que el ``voice_id`` está disponible en la cuenta."""

        if not self.configured:
            return {"ok": False, "reason": "not_configured", "voice_id": self.voice_id}
        try:
            async with httpx.AsyncClient(timeout=self._settings.elevenlabs_timeout_seconds) as client:
                response = await client.get(f"{API_BASE}/voices/{self.voice_id}", headers=self._headers())
        except httpx.HTTPError as exc:
            return {"ok": False, "reason": f"network_error: {exc}", "voice_id": self.voice_id}
        if response.status_code == 200:
            body = response.json()
            return {
                "ok": True,
                "voice_id": self.voice_id,
                "name": body.get("name"),
                "category": body.get("category"),
            }
        if response.status_code == 404:
            return {
                "ok": False,
                "voice_id": self.voice_id,
                "reason": "voice_not_in_account",
                "hint": "Añade la voz a 'My Voices' desde la Voice Library de ElevenLabs.",
            }
        return {"ok": False, "voice_id": self.voice_id, "reason": f"http_{response.status_code}"}

    # ------------------------------------------------------------------
    async def available(self) -> bool:
        return self.configured

    def describe(self) -> dict[str, Any]:
        stats = self._cache.stats()
        return {
            "name": self.name,
            "available": self.configured,
            "voice": self.voice_id,
            "model": self.model,
            "api_key_present": self._settings.has_elevenlabs,
            "live_synthesis_allowed": self._settings.elevenlabs_allow_live,
            "cached_phrases": len(stats.get("phrases_cached", [])),
            "cost": "gratis mientras se sirva del caché",
        }
