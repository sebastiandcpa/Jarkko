"""Captura de micrófono con sounddevice (PortAudio).

Siempre PCM 16 bits mono al ritmo que espera el reconocedor.  Si el dispositivo no
soporta 16 kHz, se captura a su ritmo nativo y se decima aquí mismo, sin depender
de ``audioop`` (que desaparece en Python 3.13).
"""

from __future__ import annotations

import array
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.config import Settings, get_settings
from app.utils.text import normalize

logger = logging.getLogger(__name__)

#: Ritmos habituales de los micrófonos de portátil, por orden de preferencia.
_FALLBACK_RATES = (16000, 48000, 44100)


class MicrophoneUnavailable(RuntimeError):
    """No hay micrófono utilizable."""


def _downsample(pcm: bytes, source_rate: int, target_rate: int) -> bytes:
    """Decimación simple por selección de muestras (suficiente para voz)."""

    if source_rate == target_rate:
        return pcm
    samples = array.array("h")
    samples.frombytes(pcm)
    step = source_rate / target_rate
    output = array.array("h")
    position = 0.0
    total = len(samples)
    while position < total:
        output.append(samples[int(position)])
        position += step
    return output.tobytes()


class Microphone:
    """Micrófono del sistema, en el formato que necesita Vosk."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._error: str | None = None
        self._capture_rate: int | None = None

    # ------------------------------------------------------------------
    @property
    def target_rate(self) -> int:
        return self._settings.stt_sample_rate

    @property
    def device(self) -> int | None:
        wanted = self._settings.stt_device_name.strip()
        if wanted:
            found = self._find_by_name(wanted)
            if found is not None:
                return found
            logger.warning(
                "No encuentro ningún micrófono que contenga '%s'; uso el predeterminado.",
                wanted,
            )
        return self._settings.input_device

    def _find_by_name(self, fragment: str) -> int | None:
        """Primer dispositivo de entrada cuyo nombre contenga ``fragment``."""

        try:
            sounddevice = self._sounddevice()
            devices = sounddevice.query_devices()
        except (MicrophoneUnavailable, Exception):  # noqa: B014 - PortAudio es variado
            return None
        needle = normalize(fragment)
        for index, info in enumerate(devices):
            if info["max_input_channels"] < 1:
                continue
            if needle in normalize(str(info["name"])):
                return index
        return None

    def _sounddevice(self) -> Any:
        try:
            import sounddevice
        except (ImportError, OSError) as exc:  # OSError: falta PortAudio
            raise MicrophoneUnavailable(
                "El paquete 'sounddevice' no está disponible: no puedo abrir el micrófono."
            ) from exc
        return sounddevice

    def _resolve_rate(self, sounddevice: Any) -> int:
        """Primer ritmo que el dispositivo acepte de verdad."""

        if self._capture_rate is not None:
            return self._capture_rate
        for rate in (self.target_rate, *_FALLBACK_RATES):
            try:
                sounddevice.check_input_settings(
                    device=self.device, channels=1, dtype="int16", samplerate=rate
                )
            except Exception:  # noqa: BLE001 - PortAudio lanza tipos variados
                continue
            self._capture_rate = rate
            if rate != self.target_rate:
                logger.info(
                    "El micrófono no acepta %d Hz; capturo a %d Hz y remuestreo.",
                    self.target_rate,
                    rate,
                )
            return rate
        raise MicrophoneUnavailable(
            "Ningún ritmo de muestreo compatible en el micrófono (probé 16k, 48k y 44.1k)."
        )

    # ------------------------------------------------------------------
    @contextmanager
    def stream(self) -> Iterator[Any]:
        """Abre el micrófono y va entregando bloques de audio ya remuestreados."""

        sounddevice = self._sounddevice()
        rate = self._resolve_rate(sounddevice)
        block = max(1, int(rate * self._settings.stt_block_ms / 1000))

        try:
            raw_stream = sounddevice.RawInputStream(
                samplerate=rate,
                blocksize=block,
                device=self.device,
                channels=1,
                dtype="int16",
            )
        except Exception as exc:  # noqa: BLE001
            raise MicrophoneUnavailable(f"No pude abrir el micrófono: {exc}") from exc

        target = self.target_rate

        class _Reader:
            def __init__(self) -> None:
                self.rate = rate

            def read(self, frames: int | None = None) -> bytes:
                data, overflowed = raw_stream.read(frames or block)
                if overflowed:
                    logger.debug("Desbordamiento de audio (bloque perdido)")
                return _downsample(bytes(data), rate, target)

        with raw_stream:
            yield _Reader()

    def refresh(self) -> None:
        """Reinicia PortAudio para ver los dispositivos que hay AHORA.

        La lista se fija al importar la librería: sin esto, unos auriculares
        conectados después de arrancar no existirían para el asistente.
        """

        self._capture_rate = None
        try:
            sounddevice = self._sounddevice()
            sounddevice._terminate()
            sounddevice._initialize()
        except Exception:  # noqa: BLE001 - reabrir es un intento, no una garantía
            logger.debug("No pude reiniciar PortAudio", exc_info=True)

    # ------------------------------------------------------------------
    def measure_level(self, seconds: float = 2.0) -> dict[str, Any]:
        """Mide el nivel que entra por el micrófono.

        Sirve para distinguir «el código no funciona» de «el micrófono está
        silenciado»: Windows entrega silencio digital sin dar ningún error cuando
        el dispositivo está muteado o deshabilitado.
        """

        import array
        import math

        try:
            with self.stream() as microphone:
                blocks = max(1, int(seconds / (self._settings.stt_block_ms / 1000)))
                peaks: list[float] = []
                for _ in range(blocks):
                    samples = array.array("h")
                    samples.frombytes(microphone.read())
                    if samples:
                        peaks.append(math.sqrt(sum(s * s for s in samples) / len(samples)))
        except MicrophoneUnavailable as exc:
            return {"ok": False, "level": 0.0, "reason": "microphone_unavailable", "message": str(exc)}

        level = round(max(peaks), 1) if peaks else 0.0
        if level < 5:
            diagnosis = (
                "Entra silencio digital. El micrófono está silenciado o deshabilitado en Windows: "
                "revisa Configuración > Sistema > Sonido > Entrada (habla y mira si se mueve la "
                "barra), el mezclador de volumen, y la tecla de función de silenciar micrófono del "
                "portátil. Los permisos de privacidad ya están permitidos."
            )
        elif level < 60:
            diagnosis = "Hay señal pero es débil: sube el volumen de entrada o acércate al micrófono."
        else:
            diagnosis = "Nivel correcto."

        return {
            "ok": level >= 5,
            "level": level,
            "seconds": seconds,
            "diagnosis": diagnosis,
            "device": self.describe().get("device_in_use"),
        }

    # ------------------------------------------------------------------
    def describe(self) -> dict[str, Any]:
        try:
            sounddevice = self._sounddevice()
            devices = [
                {"index": index, "name": info["name"], "channels": info["max_input_channels"]}
                for index, info in enumerate(sounddevice.query_devices())
                if info["max_input_channels"] > 0
            ]
            rate = self._resolve_rate(sounddevice)
            default = sounddevice.query_devices(kind="input")
            index = self.device
            # El que se usa DE VERDAD, que no tiene por qué ser el predeterminado
            # del sistema: informar del predeterminado engaña al diagnosticar.
            if index is None:
                in_use = default["name"] if default else None
            else:
                in_use = next(
                    (item["name"] for item in devices if item["index"] == index), None
                )
            return {
                "available": bool(devices),
                "capture_rate": rate,
                "target_rate": self.target_rate,
                "device": index,
                "device_in_use": in_use,
                "selected_by": "nombre" if self._settings.stt_device_name.strip() else "sistema",
                "default_device": default["name"] if default else None,
                "inputs": devices[:8],
                "error": None,
            }
        except MicrophoneUnavailable as exc:
            return {
                "available": False,
                "capture_rate": None,
                "target_rate": self.target_rate,
                "device": self.device,
                "inputs": [],
                "error": str(exc),
            }
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "inputs": [], "error": str(exc)}
