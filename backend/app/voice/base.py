"""Contratos del subsistema de voz.

Misma filosofía que ``AIProvider``: el resto del sistema habla con ``TTSProvider``,
nunca con un SDK concreto.  Así conviven la voz de identidad (ElevenLabs, cacheada)
y la voz de trabajo (Windows, offline e ilimitada) sin que nadie más se entere.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class TTSError(RuntimeError):
    """Fallo al sintetizar voz."""


class TTSUnavailable(TTSError):
    """El motor no está disponible (falta clave, falta voz, sin red)."""


class CacheMiss(TTSError):
    """El texto no está en el caché y el motor no tiene permiso para gastar cuota."""


@dataclass(slots=True)
class SpeechAudio:
    """Audio sintetizado, listo para reproducir o servir al frontend."""

    data: bytes
    media_type: str  # "audio/wav" | "audio/mpeg"
    engine: str
    voice: str
    cached: bool = False
    phrase_key: str | None = None
    text: str = ""
    path: str | None = None
    """Ruta en disco cuando el audio está cacheado (la sirve /api/voice/audio)."""
    cache_key: str | None = None
    """Clave del caché; identifica el audio en ``GET /api/voice/audio/{clave}``."""

    @property
    def extension(self) -> str:
        return ".mp3" if self.media_type == "audio/mpeg" else ".wav"

    def to_public(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "voice": self.voice,
            "media_type": self.media_type,
            "cached": self.cached,
            "phrase_key": self.phrase_key,
            "text": self.text,
            "bytes": len(self.data),
        }


@dataclass(slots=True)
class SpeechPlan:
    """Qué se va a decir en voz alta.

    El texto hablado **no** tiene que ser el texto escrito: en el chat se muestra
    la ruta completa de un archivo, pero en voz basta «Listo, carpeta creada».
    Esas frases fijas son las que se cachean con la voz de identidad.
    """

    text: str
    phrase_key: str | None = None
    prefer_identity_voice: bool = True

    @property
    def cacheable(self) -> bool:
        return self.phrase_key is not None


class TTSProvider(ABC):
    """Motor de síntesis de voz."""

    name: str = "base"

    @abstractmethod
    async def synthesize(self, plan: SpeechPlan) -> SpeechAudio:
        """Devuelve el audio, o lanza ``TTSError`` si no puede."""

    async def available(self) -> bool:
        return True

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "available": True}


@dataclass(slots=True)
class VoiceStatus:
    """Estado del subsistema de voz para ``GET /api/voice/status``."""

    enabled: bool
    autospeak: bool
    playback: bool
    engines: list[dict[str, Any]] = field(default_factory=list)
    cache: dict[str, Any] = field(default_factory=dict)
    identity_voice: dict[str, Any] = field(default_factory=dict)
    last_spoken: dict[str, Any] | None = None

    def to_public(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "autospeak": self.autospeak,
            "playback": self.playback,
            "engines": self.engines,
            "cache": self.cache,
            "identity_voice": self.identity_voice,
            "last_spoken": self.last_spoken,
        }
