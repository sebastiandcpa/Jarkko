"""Identidad del asistente: **JARKKO**.

JARKKO es la fusión de JARVIS y EKKO: un solo motor, una sola personalidad, un
solo modelo.  Los nombres ``jarvis`` y ``ekko`` se siguen aceptando como alias
para no romper nada del frontend, pero resuelven siempre a JARKKO.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.utils.text import normalize

DEFAULT_ASSISTANT = "jarkko"


@dataclass(frozen=True, slots=True)
class AssistantProfile:
    key: str
    display_name: str
    tagline: str
    ack: str
    failure: str
    confirmation: str
    idle: str
    voice_id: str = ""
    """Voz de identidad (ElevenLabs).  La voz local es el respaldo gratuito."""

    def style(self, message: str, *, status: str) -> str:
        """Aplica el tono de JARKKO al mensaje final."""

        text = (message or "").strip()
        if not text:
            text = self.idle
        prefix = {
            "success": self.ack,
            "error": self.failure,
            "awaiting_confirmation": self.confirmation,
            "idle": self.idle,
            "no_action": self.idle,
        }.get(status, "")
        if not prefix:
            return text
        # Si el propio mensaje ya empieza por la muletilla, no se repite:
        # «Aquí estoy. Aquí estoy, te escucho» suena a loro.
        head = normalize(prefix).rstrip(".,;:!¡¿?")
        if head and normalize(text).startswith(head):
            return text
        return f"{prefix} {text}".strip()

    def to_public(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "display_name": self.display_name,
            "tagline": self.tagline,
            "voice_id": self.voice_id,
        }


JARKKO = AssistantProfile(
    key="jarkko",
    display_name="JARKKO",
    tagline="Preciso como JARVIS, cercano como EKKO. Un solo asistente.",
    ack="Hecho.",
    failure="No pude completarlo.",
    confirmation="Necesito tu autorización.",
    idle="Aquí estoy.",
    voice_id="WEXRePkZGpmcFLvCOaB1",
)

ASSISTANTS: dict[str, AssistantProfile] = {"jarkko": JARKKO}

#: Nombres antiguos aceptados por compatibilidad; todos son JARKKO.
ALIASES: dict[str, str] = {
    "jarvis": "jarkko",
    "ekko": "jarkko",
    "jarvis-ekko": "jarkko",
    "jarko": "jarkko",
    "jarkos": "jarkko",
}


def resolve_assistant(name: str | None) -> AssistantProfile:
    """Perfil por nombre o alias.  Cualquier valor desconocido es JARKKO."""

    key = normalize(name or "")
    key = ALIASES.get(key, key)
    return ASSISTANTS.get(key, ASSISTANTS[DEFAULT_ASSISTANT])


def assistant_catalog() -> list[dict[str, Any]]:
    return [profile.to_public() for profile in ASSISTANTS.values()]


def accepted_names() -> list[str]:
    """Todo lo que la API acepta en el campo ``assistant``."""

    return sorted({*ASSISTANTS, *ALIASES})
