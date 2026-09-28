"""Modelos de ``/api/voice/*``."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SpeakRequest(BaseModel):
    text: str | None = Field(default=None, max_length=2000, description="Texto a decir.")
    phrase_key: str | None = Field(
        default=None,
        max_length=64,
        description="Clave del catálogo de frases fijas (suena con la voz de identidad).",
    )
    play: bool | None = Field(
        default=None, description="Reproducir por los altavoces del equipo. Por defecto, sí."
    )


class SpeakResponse(BaseModel):
    spoken: bool
    engine: str | None = None
    voice: str | None = None
    media_type: str | None = None
    cached: bool = False
    phrase_key: str | None = None
    text: str = ""
    audio_url: str | None = None
    bytes: int = 0
    reason: str | None = None


class VoiceStatusResponse(BaseModel):
    enabled: bool
    autospeak: bool
    playback: bool
    engines: list[dict[str, Any]] = Field(default_factory=list)
    cache: dict[str, Any] = Field(default_factory=dict)
    identity_voice: dict[str, Any] = Field(default_factory=dict)
    last_spoken: dict[str, Any] | None = None


class PhraseCatalogResponse(BaseModel):
    total: int
    total_characters: int
    phrases: list[dict[str, Any]] = Field(default_factory=list)


class ListenOnceRequest(BaseModel):
    seconds: float | None = Field(
        default=None, ge=1, le=30, description="Tiempo máximo de grabación."
    )
    execute: bool = Field(
        default=False,
        description="Si es true, la orden entendida se ejecuta por el mismo camino que /api/chat.",
    )
    require_wake_word: bool | None = Field(
        default=None, description="Exigir la palabra clave. Por defecto, la configuración."
    )


class ListenOnceResponse(BaseModel):
    heard: bool
    text: str = ""
    command: str = ""
    wake_word: bool = False
    seconds: float | None = None
    executed: bool = False
    chat: dict[str, Any] | None = None
    reason: str | None = None
    message: str | None = None


class ListenControlResponse(BaseModel):
    running: bool
    started: bool | None = None
    stopped: bool | None = None
    wake_word: str | None = None
    reason: str | None = None
    message: str | None = None


class ListenStatusResponse(BaseModel):
    enabled: bool
    running: bool
    available: bool
    wake_word: str
    wake_word_required: bool
    recognizer: dict[str, Any] = Field(default_factory=dict)
    microphone: dict[str, Any] = Field(default_factory=dict)
    stats: dict[str, int] = Field(default_factory=dict)
    recent: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None


class CacheBuildResponse(BaseModel):
    ok: bool
    generated: int = 0
    characters_spent: int = 0
    catalog_characters: int = 0
    failed: int = 0
    phrases: list[dict[str, Any]] = Field(default_factory=list)
    subscription: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    message: str | None = None
