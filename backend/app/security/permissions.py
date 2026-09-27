"""Permission Manager: decide si una acción se ejecuta, se confirma o se bloquea.

Es el único componente autorizado a dar luz verde.  El Tool Executor no ejecuta
nada sin un veredicto ``ALLOW``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.config import Settings, get_settings
from app.security.risk import RiskLevel
from app.tools.base import ToolDefinition


class PermissionDecision(str, Enum):
    ALLOW = "allow"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class PermissionVerdict:
    decision: PermissionDecision
    risk_level: RiskLevel
    reason: str
    code: str

    @property
    def allowed(self) -> bool:
        return self.decision is PermissionDecision.ALLOW

    @property
    def needs_confirmation(self) -> bool:
        return self.decision is PermissionDecision.REQUIRES_CONFIRMATION

    @property
    def denied(self) -> bool:
        return self.decision is PermissionDecision.DENY

    def to_public(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "risk_level": self.risk_level.value,
            "reason": self.reason,
            "code": self.code,
        }


class PermissionManager:
    """Aplica la política de riesgo configurada."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def confirmation_threshold(self) -> RiskLevel:
        return self._settings.confirmation_threshold

    def evaluate(
        self,
        tool: ToolDefinition,
        arguments: Mapping[str, Any] | None = None,
        *,
        confirmed: bool = False,
    ) -> PermissionVerdict:
        risk = tool.risk_for(arguments or {})

        if not tool.enabled:
            return PermissionVerdict(
                PermissionDecision.DENY,
                risk,
                f"La herramienta '{tool.name}' está deshabilitada en esta instalación.",
                "tool_disabled",
            )

        if risk is RiskLevel.CRITICAL and not self._settings.enable_critical_tools:
            return PermissionVerdict(
                PermissionDecision.DENY,
                risk,
                (
                    f"'{tool.name}' es de riesgo crítico y las herramientas críticas están "
                    "desactivadas (JARVIS_ENABLE_CRITICAL_TOOLS=false)."
                ),
                "critical_tools_disabled",
            )

        if risk.at_least(self.confirmation_threshold):
            if confirmed:
                return PermissionVerdict(
                    PermissionDecision.ALLOW,
                    risk,
                    "Confirmación explícita recibida del usuario.",
                    "user_confirmed",
                )
            return PermissionVerdict(
                PermissionDecision.REQUIRES_CONFIRMATION,
                risk,
                f"'{tool.name}' tiene riesgo {risk.value} y requiere confirmación explícita.",
                "confirmation_required",
            )

        return PermissionVerdict(
            PermissionDecision.ALLOW,
            risk,
            f"Riesgo {risk.value} por debajo del umbral de confirmación.",
            "below_threshold",
        )
