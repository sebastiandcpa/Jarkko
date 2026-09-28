"""Planner: convierte peticiones de la IA en un plan ejecutable y auditado.

Por cada acción propuesta:

1. **ToolSelector** la resuelve a una herramienta registrada;
2. **Validator** valida y normaliza los argumentos (rutas, URLs, tipos);
3. **Permission Manager** decide: ejecutar, pedir confirmación o bloquear.

El plan resultante es un dato inerte: no toca el sistema.  Ejecutarlo es tarea del
Tool Executor.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.agent.tool_selector import SelectionResult, ToolSelector
from app.providers.base import ToolCall
from app.security.permissions import PermissionManager, PermissionVerdict
from app.security.risk import RiskLevel
from app.security.validator import ArgumentValidator, ValidationError
from app.tools.base import ToolDefinition
from app.tools.registry import ToolRegistry
from app.utils.redaction import sanitize_arguments


class PlanStatus(str, Enum):
    READY = "ready"
    NEEDS_CONFIRMATION = "needs_confirmation"
    REJECTED = "rejected"


@dataclass(slots=True)
class PlannedAction:
    """Una acción evaluada: lista para ejecutar, pendiente de confirmar o rechazada."""

    call: ToolCall
    status: PlanStatus
    risk_level: RiskLevel = RiskLevel.LOW
    tool: ToolDefinition | None = None
    validated_arguments: dict[str, Any] | None = None
    verdict: PermissionVerdict | None = None
    error: dict[str, Any] | None = None

    @property
    def tool_name(self) -> str:
        return self.tool.name if self.tool else str(self.call.tool)

    @property
    def raw_arguments(self) -> dict[str, Any]:
        return dict(self.call.arguments or {})

    def description(self) -> str:
        """Texto legible para pedir confirmación o registrar la acción."""

        arguments = sanitize_arguments(self.validated_arguments or self.raw_arguments)
        rendered = ", ".join(f"{key}={value}" for key, value in arguments.items())
        base = self.tool.description if self.tool else self.tool_name
        return f"{base} → {self.tool_name}({rendered})" if rendered else f"{base} → {self.tool_name}()"

    def to_public(self) -> dict[str, Any]:
        return {
            "tool": self.tool_name,
            "arguments": sanitize_arguments(self.validated_arguments or self.raw_arguments),
            "status": self.status.value,
            "risk_level": self.risk_level.value,
            "reason": self.call.reason,
            "error": self.error,
            "permission": self.verdict.to_public() if self.verdict else None,
        }


@dataclass(slots=True)
class ExecutionPlan:
    actions: list[PlannedAction] = field(default_factory=list)

    @property
    def requires_confirmation(self) -> bool:
        return any(action.status is PlanStatus.NEEDS_CONFIRMATION for action in self.actions)

    @property
    def ready(self) -> list[PlannedAction]:
        return [action for action in self.actions if action.status is PlanStatus.READY]

    @property
    def pending(self) -> list[PlannedAction]:
        return [action for action in self.actions if action.status is PlanStatus.NEEDS_CONFIRMATION]

    @property
    def rejected(self) -> list[PlannedAction]:
        return [action for action in self.actions if action.status is PlanStatus.REJECTED]

    @property
    def max_risk(self) -> RiskLevel:
        return RiskLevel.max(*(action.risk_level for action in self.actions)) if self.actions else RiskLevel.LOW

    def to_public(self) -> list[dict[str, Any]]:
        return [action.to_public() for action in self.actions]


class Planner:
    """Construye planes seguros a partir de peticiones de herramienta."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        selector: ToolSelector | None = None,
        validator: ArgumentValidator | None = None,
        permissions: PermissionManager | None = None,
    ) -> None:
        self._registry = registry
        self._selector = selector or ToolSelector(registry)
        self._validator = validator or ArgumentValidator()
        self._permissions = permissions or PermissionManager()

    # ------------------------------------------------------------------
    def plan(self, calls: Sequence[ToolCall], *, confirmed: bool = False) -> ExecutionPlan:
        return ExecutionPlan(actions=[self.plan_action(call, confirmed=confirmed) for call in calls])

    def plan_action(self, call: ToolCall, *, confirmed: bool = False) -> PlannedAction:
        selection: SelectionResult = self._selector.select(call)
        if not selection.found or selection.tool is None:
            return PlannedAction(
                call=call,
                status=PlanStatus.REJECTED,
                error={"code": selection.code, "message": selection.error, "field": None},
            )

        tool = selection.tool
        call.tool = tool.name  # nombre canónico a partir de aquí

        try:
            validated = self._validator.validate(tool, call.arguments)
        except ValidationError as exc:
            return PlannedAction(
                call=call,
                status=PlanStatus.REJECTED,
                tool=tool,
                risk_level=tool.risk_level,
                error=exc.to_public(),
            )

        verdict = self._permissions.evaluate(tool, validated, confirmed=confirmed)
        if verdict.denied:
            return PlannedAction(
                call=call,
                status=PlanStatus.REJECTED,
                tool=tool,
                risk_level=verdict.risk_level,
                validated_arguments=validated,
                verdict=verdict,
                error={"code": verdict.code, "message": verdict.reason, "field": None},
            )

        status = PlanStatus.NEEDS_CONFIRMATION if verdict.needs_confirmation else PlanStatus.READY
        return PlannedAction(
            call=call,
            status=status,
            tool=tool,
            risk_level=verdict.risk_level,
            validated_arguments=validated,
            verdict=verdict,
        )

    # ------------------------------------------------------------------
    def plan_raw(
        self, tool_name: str, arguments: Mapping[str, Any] | None, *, confirmed: bool = False
    ) -> PlannedAction:
        """Atajo para ``POST /api/actions/execute`` y para las confirmaciones."""

        return self.plan_action(
            ToolCall(tool=tool_name, arguments=dict(arguments or {})), confirmed=confirmed
        )
