"""Resolución de carpetas conocidas del usuario.

Nunca se hardcodea ``C:\\Users\\Usuario``: el home real se obtiene de ``Path.home()``
y, en Windows, las carpetas conocidas se consultan en el registro para respetar
redirecciones (OneDrive, discos alternativos, nombres localizados).
"""

from __future__ import annotations

import sys
from functools import cached_property
from pathlib import Path

from app.utils.text import normalize

IS_WINDOWS = sys.platform == "win32"

#: Claves canónicas de carpeta conocida.
FOLDER_KEYS = ("home", "desktop", "documents", "downloads", "pictures", "videos", "music")

#: Nombres del registro de Windows (``Shell Folders``) por clave canónica.
_REGISTRY_NAMES: dict[str, str] = {
    "desktop": "Desktop",
    "documents": "Personal",
    "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "pictures": "My Pictures",
    "videos": "My Video",
    "music": "My Music",
}

#: Nombre en disco usado como respaldo si el registro no está disponible.
_FALLBACK_NAMES: dict[str, str] = {
    "desktop": "Desktop",
    "documents": "Documents",
    "downloads": "Downloads",
    "pictures": "Pictures",
    "videos": "Videos",
    "music": "Music",
}

#: Alias en español e inglés -> clave canónica.  Se comparan normalizados.
FOLDER_ALIASES: dict[str, str] = {
    "home": "home",
    "inicio": "home",
    "usuario": "home",
    "mi carpeta": "home",
    "carpeta personal": "home",
    "desktop": "desktop",
    "escritorio": "desktop",
    "documents": "documents",
    "documentos": "documents",
    "mis documentos": "documents",
    "downloads": "downloads",
    "descargas": "downloads",
    "mis descargas": "downloads",
    "pictures": "pictures",
    "imagenes": "pictures",
    "mis imagenes": "pictures",
    "fotos": "pictures",
    "videos": "videos",
    "mis videos": "videos",
    "peliculas": "videos",
    "music": "music",
    "musica": "music",
    "mis canciones": "music",
}


class UserPaths:
    """Carpetas del usuario actual, resueltas de forma perezosa y cacheada."""

    def __init__(self, home: Path | None = None) -> None:
        self._home = (home or Path.home()).expanduser()

    # ------------------------------------------------------------------
    @cached_property
    def home(self) -> Path:
        return self._home

    @cached_property
    def desktop(self) -> Path:
        return self._resolve("desktop")

    @cached_property
    def documents(self) -> Path:
        return self._resolve("documents")

    @cached_property
    def downloads(self) -> Path:
        return self._resolve("downloads")

    @cached_property
    def pictures(self) -> Path:
        return self._resolve("pictures")

    @cached_property
    def videos(self) -> Path:
        return self._resolve("videos")

    @cached_property
    def music(self) -> Path:
        return self._resolve("music")

    # ------------------------------------------------------------------
    def get(self, key: str) -> Path | None:
        """Carpeta por clave canónica (``"downloads"``, ``"documents"``, ...)."""

        if key not in FOLDER_KEYS:
            return None
        return getattr(self, key)

    def resolve_alias(self, name: str) -> Path | None:
        """Carpeta a partir de un alias en lenguaje natural (``"Descargas"``)."""

        key = FOLDER_ALIASES.get(normalize(name))
        return self.get(key) if key else None

    def as_dict(self) -> dict[str, str]:
        """Mapa clave -> ruta, para exponerlo al frontend."""

        return {key: str(self.get(key)) for key in FOLDER_KEYS}

    # ------------------------------------------------------------------
    def _resolve(self, key: str) -> Path:
        if IS_WINDOWS:
            from_registry = self._from_registry(key)
            if from_registry is not None:
                return from_registry
        return self._home / _FALLBACK_NAMES[key]

    def _from_registry(self, key: str) -> Path | None:
        name = _REGISTRY_NAMES.get(key)
        if not name:
            return None
        try:
            import winreg

            sub_key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_key) as handle:
                raw, _ = winreg.QueryValueEx(handle, name)
        except (OSError, ImportError, ValueError):
            return None
        if not isinstance(raw, str) or not raw.strip():
            return None
        try:
            return Path(raw).expanduser()
        except OSError:
            return None


#: Instancia compartida por toda la aplicación.
USER_PATHS = UserPaths()
