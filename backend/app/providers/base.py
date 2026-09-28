"""Abstracción de proveedores de inteligencia.

El motor del agente nunca habla con un SDK concreto: habla con ``AIProvider``.
Eso permite pasar de ``MockAIProvider`` (offline, determinista) a OpenAI,
Anthropic o Gemini sin tocar el resto del sistema.

El proveedor **no ejecuta nada**: solo propone llamadas a herramientas ya
registradas.  La decisión de ejecutarlas es del Planner, el Validator y el
Permission Manager.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.tools.registry import ToolRegistry


class AIProviderError(RuntimeError):
    """Fallo al hablar con el proveedor de IA."""


class AIProviderNotConfigured(AIProviderError):
    """El proveedor existe pero no está configurado (falta API key o implementación)."""


@dataclass(slots=True)
class ToolCall:
    """Petición de herramienta propuesta por la IA (todavía sin validar)."""

    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_public(self) -> dict[str, Any]:
        return {"tool": self.tool, "arguments": dict(self.arguments), "reason": self.reason}


@dataclass(slots=True)
class ChatTurn:
    """Turno previo de conversación, para dar contexto al proveedor."""

    role: str  # "user" | "assistant"
    content: str


@dataclass(slots=True)
class IntentResult:
    """Interpretación de un mensaje del usuario."""

    reply: str = ""
    actions: list[ToolCall] = field(default_factory=list)
    confidence: float = 0.0
    source: str = "unknown"
    needs_clarification: bool = False
    matched_rule: str | None = None

    def to_public(self) -> dict[str, Any]:
        return {
            "reply": self.reply,
            "actions": [action.to_public() for action in self.actions],
            "confidence": round(self.confidence, 2),
            "source": self.source,
            "needs_clarification": self.needs_clarification,
            "matched_rule": self.matched_rule,
        }


class AIProvider(ABC):
    """Contrato mínimo de un proveedor de inteligencia."""

    #: Identificador estable usado en configuración y respuestas de la API.
    name: str = "base"
    #: Si necesita API key para funcionar.
    requires_api_key: bool = True

    @abstractmethod
    async def parse_intent(
        self,
        message: str,
        *,
        assistant: str,
        registry: ToolRegistry,
        history: Sequence[ChatTurn] = (),
    ) -> IntentResult:
        """Traduce lenguaje natural a una o varias peticiones de herramienta."""

    async def compose_reply(
        self,
        message: str,
        intent: IntentResult,
        outcomes: Sequence[dict[str, Any]],
        *,
        assistant: str,
    ) -> str | None:
        """Redacta la respuesta final.  ``None`` = usar la plantilla del motor."""

        return None

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "requires_api_key": self.requires_api_key, "available": True}


class UnimplementedProvider(AIProvider):
    """Base para proveedores externos aún no implementados.

    Se registran para que la arquitectura esté lista, pero fallan de forma
    explícita si alguien los selecciona sin implementación ni API key.
    """

    vendor: str = "external"

    def __init__(self, *, api_key: str = "", model: str = "") -> None:
        self._api_key = api_key
        self._model = model

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def parse_intent(
        self,
        message: str,
        *,
        assistant: str,
        registry: ToolRegistry,
        history: Sequence[ChatTurn] = (),
    ) -> IntentResult:
        raise AIProviderNotConfigured(
            f"El proveedor '{self.name}' todavía no está implementado. "
            "Usa JARVIS_AI_PROVIDER=mock o implementa la integración."
        )

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "vendor": self.vendor,
            "requires_api_key": True,
            "api_key_present": self.configured,
            "model": self._model or None,
            "available": False,
            "status": "not_implemented",
        }
