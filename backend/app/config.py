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
    # Vite en desarrollo y en preview.
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:4173",
    "http://localhost:4173",
    # Electron empaquetado: carga dist/index.html con loadFile, así que su origen
    # es "file://" (Chromium lo envía como "null" en las peticiones fetch).
    "file://",
    "null",
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

    # --- voz (TTS) ---
    tts_enabled: bool = True
    """Interruptor general de la voz.  ``false`` deja el asistente mudo."""
    tts_autospeak: bool = True
    """Si JARKKO habla solo al responder en /api/chat."""
    tts_playback: bool = True
    """Si el backend reproduce el audio por los altavoces (se apaga en tests)."""
    tts_engine: str = "auto"
    """auto | elevenlabs | windows | none"""
    tts_windows_voice: str = "Microsoft Raul"
    """Voz del motor de Windows (gratis, offline, ilimitada)."""
    tts_cache_dir: Path = Path("data/voice")
    tts_max_characters: int = 400
    """Longitud máxima de una locución: leer rutas larguísimas no aporta nada."""

    # --- escucha (STT) ---
    stt_enabled: bool = True
    stt_model_path: Path = Path("data/models/vosk-model-small-es-0.42")
    stt_sample_rate: int = 16000
    stt_device: int = -1
    """Índice del dispositivo de entrada; -1 = el predeterminado de Windows."""
    stt_device_name: str = ""
    """Parte del nombre del micrófono a usar, p.ej. "Senary".

    Más fiable que el índice: los índices cambian al conectar o quitar auriculares.
    Tiene prioridad sobre ``stt_device`` y sobre el predeterminado del sistema."""
    stt_block_ms: int = 250
    stt_listen_seconds: float = 8.0
    stt_silence_seconds: float = 1.2
    stt_silence_watchdog_seconds: float = 45.0
    """Silencio digital seguido tras el cual se reabre el micrófono (0 = nunca)."""
    stt_autostart: bool = False
    """Si la escucha continua arranca con el servidor."""
    wake_word: str = "jarkko"
    wake_word_required: bool = True
    """Si ``false``, cualquier frase se interpreta como orden (más cómodo, más falsos positivos)."""

    # --- ElevenLabs (voz de identidad) ---
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "WEXRePkZGpmcFLvCOaB1"
    elevenlabs_model: str = "eleven_multilingual_v2"
    elevenlabs_allow_live: bool = False
    """PROTECCIÓN DE CUOTA: con ``false``, ElevenLabs solo sirve audio ya cacheado.
    Nunca se gastan créditos en texto dinámico sin activarlo a conciencia."""
    elevenlabs_output_format: str = "pcm_24000"
    """pcm_* se envuelve en WAV y se reproduce sin dependencias; mp3_* usa MCI."""
    elevenlabs_timeout_seconds: float = 30.0

    # --- comportamiento ---
    search_engine: str = "google"
    news_country: str = "PE"
    """País de las noticias (código ISO de dos letras, para Google News)."""
    news_language: str = "es-419"
    """Idioma de las noticias: es-419 es el español de Latinoamérica."""
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

    @property
    def voice_cache_dir(self) -> Path:
        path = self.tts_cache_dir
        return path if path.is_absolute() else (BACKEND_DIR / path)

    @property
    def has_elevenlabs(self) -> bool:
        return bool(self.elevenlabs_api_key.strip())

    @property
    def stt_model_dir(self) -> Path:
        path = self.stt_model_path
        return path if path.is_absolute() else (BACKEND_DIR / path)

    @property
    def input_device(self) -> int | None:
        return None if self.stt_device < 0 else self.stt_device


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve la configuración (cacheada para toda la vida del proceso)."""

    return Settings()
