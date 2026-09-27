"""Configuración central del backend.

Todas las opciones se leen de variables de entorno con el prefijo ``JARVIS_``
o del archivo ``.env`` ubicado en ``backend/``.  Ver ``.env.example``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.security.risk import RiskLevel

# backend/app/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent

DEFAULT_CORS_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:4173",
    "http://localhost:4173",
)

# Extensiones que NUNCA se abren con `open_file`: abrirlas equivale a ejecutar
# código arbitrario a través del shell de Windows.
DEFAULT_BLOCKED_OPEN_EXTENSIONS = (
    ".exe", ".com", ".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".vbe", ".js",
    ".jse", ".wsf", ".wsh", ".msi", ".msp", ".scr", ".cpl", ".hta", ".reg",
    ".lnk", ".pif", ".jar", ".inf", ".sys", ".dll", ".application", ".gadget",
)


class Settings(BaseSettings):
    """Configuración inmutable de la aplicación."""

    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- identidad ---
    app_name: str = "jarvis-ekko"
    version: str = "0.1.0"

    # --- servidor ---
    host: str = "127.0.0.1"
    port: int = 8765
    cors_origins: str = ",".join(DEFAULT_CORS_ORIGINS)
    log_level: str = "INFO"

    # --- proveedor de IA ---
    ai_provider: str = "mock"
    ai_model: str = ""
    ai_api_key: str = ""

    # --- seguridad ---
    confirmation_threshold: RiskLevel = RiskLevel.HIGH
    enable_critical_tools: bool = False
    extra_allowed_roots: str = ""
    confirmation_ttl_seconds: int = 300
    blocked_open_extensions: str = ",".join(DEFAULT_BLOCKED_OPEN_EXTENSIONS)

    # --- comportamiento ---
    search_engine: str = "google"
    system_status_interval: float = 5.0
    activity_default_limit: int = 50
    activity_max_limit: int = 500
    max_search_results: int = 200
    search_max_scanned_entries: int = 200_000
    database_path: Path = Path("data/jarvis.db")

    @field_validator("log_level")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    # ------------------------------------------------------------------
    # Derivados
    # ------------------------------------------------------------------
    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def extra_allowed_root_paths(self) -> list[Path]:
        roots: list[Path] = []
        for raw in self.extra_allowed_roots.split(","):
            candidate = raw.strip()
            if not candidate:
                continue
            try:
                roots.append(Path(candidate).expanduser().resolve())
            except OSError:  # ruta inválida en el entorno actual
                continue
        return roots

    @property
    def blocked_open_extension_set(self) -> frozenset[str]:
        return frozenset(
            item.strip().lower() if item.strip().startswith(".") else f".{item.strip().lower()}"
            for item in self.blocked_open_extensions.split(",")
            if item.strip()
        )

    @property
    def database_file(self) -> Path:
        path = self.database_path
        return path if path.is_absolute() else (BACKEND_DIR / path)

    @property
    def has_external_ai(self) -> bool:
        return self.ai_provider.lower() != "mock" and bool(self.ai_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve la configuración (cacheada para toda la vida del proceso)."""

    return Settings()
