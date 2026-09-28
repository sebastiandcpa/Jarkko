"""Caché de audio en disco.

Es la pieza que convierte la voz de pago en voz gratis: cada frase fija se
sintetiza **una vez** y se reutiliza para siempre.  Si el archivo existe, no se
gasta ni un crédito.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from app.voice.base import SpeechAudio

MANIFEST_NAME = "manifest.json"


class AudioCache:
    """Índice de audios cacheados, con manifiesto legible para diagnóstico."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._lock = threading.Lock()
        self._manifest: dict[str, dict[str, Any]] | None = None

    # ------------------------------------------------------------------
    @property
    def manifest_path(self) -> Path:
        return self.root / MANIFEST_NAME

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._manifest is None:
            try:
                raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                self._manifest = raw if isinstance(raw, dict) else {}
            except (OSError, json.JSONDecodeError):
                self._manifest = {}
        return self._manifest

    def _save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(self._load(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    @staticmethod
    def key(*, engine: str, voice: str, model: str, text: str) -> str:
        digest = hashlib.sha256(
            "\x1f".join((engine, voice, model, text.strip())).encode("utf-8")
        ).hexdigest()
        return digest[:32]

    def path_for(self, key: str, *, engine: str, extension: str) -> Path:
        return self.root / engine / f"{key}{extension}"

    # ------------------------------------------------------------------
    def get(self, key: str) -> SpeechAudio | None:
        with self._lock:
            entry = self._load().get(key)
            if entry is None:
                return None
            path = Path(entry["path"])
            if not path.is_absolute():
                path = self.root / path
            try:
                data = path.read_bytes()
            except OSError:
                return None
        return SpeechAudio(
            data=data,
            media_type=entry.get("media_type", "audio/wav"),
            engine=entry.get("engine", "unknown"),
            voice=entry.get("voice", ""),
            cached=True,
            phrase_key=entry.get("phrase_key"),
            text=entry.get("text", ""),
            path=str(path),
            cache_key=key,
        )

    def put(self, key: str, audio: SpeechAudio, *, model: str = "") -> SpeechAudio:
        extension = audio.extension
        path = self.path_for(key, engine=audio.engine, extension=extension)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio.data)
        with self._lock:
            self._load()[key] = {
                "path": str(path.relative_to(self.root)) if path.is_relative_to(self.root) else str(path),
                "engine": audio.engine,
                "voice": audio.voice,
                "model": model,
                "media_type": audio.media_type,
                "phrase_key": audio.phrase_key,
                "text": audio.text,
                "bytes": len(audio.data),
                "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
            self._save()
        audio.cached = True
        audio.path = str(path)
        audio.cache_key = key
        return audio

    def find_by_path(self, key: str) -> Path | None:
        with self._lock:
            entry = self._load().get(key)
        if entry is None:
            return None
        path = Path(entry["path"])
        return path if path.is_absolute() else self.root / path

    # ------------------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        with self._lock:
            manifest = self._load()
            entries = list(manifest.values())
        by_engine: dict[str, int] = {}
        for entry in entries:
            engine = str(entry.get("engine", "unknown"))
            by_engine[engine] = by_engine.get(engine, 0) + 1
        return {
            "entries": len(entries),
            "bytes": sum(int(entry.get("bytes", 0)) for entry in entries),
            "by_engine": by_engine,
            "phrases_cached": sorted(
                str(entry["phrase_key"]) for entry in entries if entry.get("phrase_key")
            ),
            "directory": str(self.root),
        }

    def clear(self) -> None:
        with self._lock:
            self._manifest = {}
            self._save()
