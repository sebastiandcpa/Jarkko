"""Reproducción de audio en Windows sin dependencias externas.

WAV → ``winsound`` (biblioteca estándar).
MP3 → MCI de ``winmm.dll`` vía ``ctypes`` (también estándar).

La reproducción es secuencial: JARKKO no se habla encima de sí mismo.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import tempfile
import threading
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"


class AudioPlayer:
    """Reproductor local, serializado con un lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._temp_dir = Path(tempfile.gettempdir()) / "jarkko-voice"

    # ------------------------------------------------------------------
    def play(self, data: bytes, media_type: str, *, path: str | None = None) -> bool:
        """Reproduce y espera a que termine.  Pensado para un hilo de trabajo."""

        if not IS_WINDOWS:
            logger.debug("Reproducción de audio solo soportada en Windows.")
            return False
        if not data and path is None:
            return False

        target = Path(path) if path and Path(path).is_file() else self._write_temp(data, media_type)
        if target is None:
            return False

        with self._lock:
            try:
                if media_type == "audio/wav":
                    return self._play_wav(target)
                return self._play_mci(target)
            except Exception:  # noqa: BLE001 - nunca romper por un fallo de audio
                logger.exception("No se pudo reproducir el audio")
                return False

    # ------------------------------------------------------------------
    def _write_temp(self, data: bytes, media_type: str) -> Path | None:
        extension = ".mp3" if media_type == "audio/mpeg" else ".wav"
        try:
            self._temp_dir.mkdir(parents=True, exist_ok=True)
            target = self._temp_dir / f"{uuid.uuid4().hex}{extension}"
            target.write_bytes(data)
            return target
        except OSError:
            logger.exception("No se pudo escribir el audio temporal")
            return None

    def _play_wav(self, path: Path) -> bool:
        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME)
        return True

    def _play_mci(self, path: Path) -> bool:
        """Reproduce MP3 con MCI.  El alias evita colisiones entre locuciones."""

        alias = f"jarkko{uuid.uuid4().hex[:8]}"
        send = ctypes.windll.winmm.mciSendStringW
        buffer = ctypes.create_unicode_buffer(256)

        def command(text: str) -> int:
            return int(send(text, buffer, 254, 0))

        if command(f'open "{path}" type mpegvideo alias {alias}') != 0:
            logger.warning("MCI no pudo abrir %s", path)
            return False
        try:
            command(f"play {alias} wait")
        finally:
            command(f"close {alias}")
        return True

    # ------------------------------------------------------------------
    def cleanup(self) -> None:
        """Borra los temporales de esta sesión."""

        if not self._temp_dir.is_dir():
            return
        for item in self._temp_dir.glob("*"):
            try:
                item.unlink()
            except OSError:
                continue


#: Reproductor compartido.
audio_player = AudioPlayer()
