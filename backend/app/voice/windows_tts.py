"""Voz local de Windows (motor moderno WinRT).

Gratis, offline, ilimitada y sin GPU.  En este equipo expone **Microsoft Raul
(es-MX, masculina)**, que es la voz de trabajo de JARKKO.

Se usa ``winsdk`` (bindings WinRT en proceso) y **no** PowerShell: pasar el texto
del asistente por una línea de comandos sería una vía de inyección, justo lo que
toda la arquitectura evita.

Nota: las voces WinRT no aparecen en el motor SAPI clásico, así que librerías como
``pyttsx3`` no ven a Raul; de ahí esta implementación.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import Settings, get_settings
from app.voice.base import SpeechAudio, SpeechPlan, TTSProvider, TTSUnavailable
from app.utils.text import normalize

logger = logging.getLogger(__name__)


class WindowsTTS(TTSProvider):
    """Síntesis con el motor de voz integrado en Windows."""

    name = "windows"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._voice_name: str | None = None
        self._checked = False
        self._error: str | None = None

    # ------------------------------------------------------------------
    def _load(self) -> Any:
        """Devuelve (SpeechSynthesizer, voz elegida) o lanza ``TTSUnavailable``."""

        try:
            from winsdk.windows.media.speechsynthesis import SpeechSynthesizer
        except ImportError as exc:  # pragma: no cover - depende del entorno
            raise TTSUnavailable(
                "El paquete 'winsdk' no está instalado: no hay voz local disponible."
            ) from exc

        wanted = normalize(self._settings.tts_windows_voice)
        try:
            voices = list(SpeechSynthesizer.all_voices)
        except OSError as exc:
            raise TTSUnavailable(f"Windows no pudo enumerar sus voces: {exc}") from exc
        if not voices:  # pragma: no cover - Windows siempre trae alguna
            raise TTSUnavailable("Windows no reporta ninguna voz instalada.")

        chosen = next((v for v in voices if normalize(v.display_name) == wanted), None)
        if chosen is None:
            chosen = next((v for v in voices if wanted in normalize(v.display_name)), None)
        if chosen is None:
            # Preferir español antes que caer en una voz en inglés.
            chosen = next((v for v in voices if v.language.lower().startswith("es")), voices[0])
            logger.warning(
                "La voz '%s' no está instalada; uso '%s'.",
                self._settings.tts_windows_voice,
                chosen.display_name,
            )

        try:
            synthesizer = SpeechSynthesizer()
            synthesizer.voice = chosen
            synthesizer.options.speaking_rate = 1.05  # un pelín más ágil que el default
        except OSError as exc:
            raise TTSUnavailable(f"El motor de voz de Windows falló: {exc}") from exc
        self._voice_name = chosen.display_name
        return synthesizer, chosen

    # ------------------------------------------------------------------
    async def synthesize(self, plan: SpeechPlan) -> SpeechAudio:
        from winsdk.windows.storage.streams import DataReader

        synthesizer, voice = self._load()
        try:
            stream = await synthesizer.synthesize_text_to_stream_async(plan.text)
            reader = DataReader(stream)
            await reader.load_async(stream.size)
            buffer = bytearray(stream.size)
            reader.read_bytes(buffer)
        except OSError as exc:  # pragma: no cover - fallo del motor del sistema
            raise TTSUnavailable(f"El motor de voz de Windows falló: {exc}") from exc
        finally:
            synthesizer.close()

        return SpeechAudio(
            data=bytes(buffer),
            media_type="audio/wav",
            engine=self.name,
            voice=voice.display_name,
            cached=False,
            phrase_key=plan.phrase_key,
            text=plan.text,
        )

    # ------------------------------------------------------------------
    async def available(self) -> bool:
        return self.describe()["available"]

    def describe(self) -> dict[str, Any]:
        if not self._checked:
            self._checked = True
            try:
                _, voice = self._load()
                self._voice_name = voice.display_name
            except TTSUnavailable as exc:
                self._error = str(exc)
        return {
            "name": self.name,
            "available": self._error is None,
            "voice": self._voice_name,
            "requested_voice": self._settings.tts_windows_voice,
            "cost": "gratis, offline, ilimitada",
            "error": self._error,
        }

    def list_voices(self) -> list[dict[str, str]]:
        try:
            from winsdk.windows.media.speechsynthesis import SpeechSynthesizer

            return [
                {
                    "name": voice.display_name,
                    "language": voice.language,
                    "gender": "female" if int(voice.gender) == 1 else "male",
                }
                for voice in SpeechSynthesizer.all_voices
            ]
        except (ImportError, OSError):  # pragma: no cover
            return []
