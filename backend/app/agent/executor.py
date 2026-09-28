"""ToolExecutor: el único punto del sistema que invoca handlers.

Se ejecuta solo lo que el Planner marcó como ``READY``.  Cada ejecución emite
eventos, se verifica cuando corresponde y queda registrada en la actividad.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.agent.planner import PlanStatus, PlannedAction
from app.security.risk import RiskLevel
from app.security.validator import ValidationError
from app.services.activity import ActivityService, activity_service
from app.services.events import EventBus, EventType, event_bus
from app.services.verification import VerificationService, verification_service
from app.tools.base import ToolResult, ToolStatus
from app.utils.redaction import redact_structure, sanitize_arguments

logger = logging.getLogger(__name__)


class ActionStatus(str, Enum):
    """Estado final de una acción tal y como lo ve el frontend."""

    SUCCESS = "success"
    ERROR = "error"
    CONFLICT = "conflict"
    DENIED = "denied"
    REJECTED = "rejected"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


_TOOL_STATUS_MAP = {
    ToolStatus.SUCCESS: ActionStatus.SUCCESS,
    ToolStatus.ERROR: ActionStatus.ERROR,
    ToolStatus.CONFLICT: ActionStatus.CONFLICT,
    ToolStatus.DENIED: ActionStatus.DENIED,
}


@dataclass(slots=True)
class ActionOutcome:
    """Resultado de una acción, listo para la API y para el registro."""

    tool: str
    status: ActionStatus
    message: str
    risk_level: RiskLevel = RiskLevel.LOW
    arguments: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    verified: bool | None = None
    verification_detail: str | None = None
    confirmation_id: str | None = None
    duration_ms: int | None = None
    error: dict[str, Any] | None = None

    @property
    def succeeded(self) -> bool:
        return self.status is ActionStatus.SUCCESS

    def to_public(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "status": self.status.value,
            "message": self.message,
            "risk_level": self.risk_level.value,
            "arguments": self.arguments,
            "data": self.data,
            "verified": self.verified,
            "verification_detail": self.verification_detail,
            "confirmation_id": self.confirmation_id,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


class ToolExecutor:
    """Ejecuta acciones ya autorizadas, verifica y registra."""

    def __init__(
        self,
        *,
        events: EventBus | None = None,
        activity: ActivityService | None = None,
        verification: VerificationService | None = None,
    ) -> None:
        self._events = events or event_bus
        self._activity = activity or activity_service
        self._verification = verification or verification_service

    # ------------------------------------------------------------------
    async def execute(
        self,
        action: PlannedAction,
        *,
        assistant: str = "jarkko",
        conversation_id: str | None = None,
    ) -> ActionOutcome:
        if action.status is not PlanStatus.READY or action.tool is None:
            raise ValueError("Solo se ejecutan acciones en estado READY.")

        tool = action.tool
        arguments = action.validated_arguments or {}
        public_arguments = sanitize_arguments(arguments)

        self._events.publish(
            EventType.ACTION_STARTED,
            {
                "tool": tool.name,
                "arguments": public_arguments,
                "risk_level": action.risk_level.value,
                "assistant": assistant,
                "conversation_id": conversation_id,
            },
        )

        started = time.perf_counter()
        try:
            result = await run_in_threadpool(tool.handler, arguments)
            if not isinstance(result, ToolResult):  # pragma: no cover - contrato interno
                raise TypeError(f"El handler de '{tool.name}' no devolvió un ToolResult.")
        except ValidationError as exc:
            result = ToolResult.denied(exc.message, reason=exc.code, field=exc.field)
        except Exception as exc:  # noqa: BLE001 - un handler no debe tumbar el backend
            logger.exception("Fallo inesperado ejecutando '%s'", tool.name)
            result = ToolResult.error(
                f"Error inesperado al ejecutar {tool.name}: {exc}", reason="unhandled_exception"
            )
        duration_ms = int((time.perf_counter() - started) * 1000)

        outcome_status = _TOOL_STATUS_MAP.get(result.status, ActionStatus.ERROR)

        # --- verificación real del efecto ---
        verification = await run_in_threadpool(self._verification.verify, tool, arguments, result)
        if verification is not None:
            result.verified = verification.verified
            result.verification_detail = verification.detail
            if not verification.verified and outcome_status is ActionStatus.SUCCESS:
                outcome_status = ActionStatus.ERROR
                result.message = (
                    f"{result.message} Sin embargo, no pude verificar el resultado: {verification.detail}"
                )

        outcome = ActionOutcome(
            tool=tool.name,
            status=outcome_status,
            message=result.message,
            risk_level=action.risk_level,
            arguments=public_arguments,
            data=redact_structure(result.data),
            verified=result.verified,
            verification_detail=result.verification_detail,
            duration_ms=duration_ms,
        )

        event_type = (
            EventType.ACTION_COMPLETED if outcome.succeeded else EventType.ACTION_FAILED
        )
        self._events.publish(
            event_type,
            {
                "tool": tool.name,
                "status": outcome.status.value,
                "message": outcome.message,
                "risk_level": outcome.risk_level.value,
                "verified": outcome.verified,
                "duration_ms": duration_ms,
                "assistant": assistant,
                "conversation_id": conversation_id,
            },
        )

        await self._activity.record(
            tool=tool.name,
            arguments=arguments,
            risk_level=action.risk_level.value,
            status=outcome.status.value,
            message=outcome.message,
            assistant=assistant,
            conversation_id=conversation_id,
            duration_ms=duration_ms,
            verified=outcome.verified,
        )
        return outcome

    # ------------------------------------------------------------------
    async def record_non_execution(
        self,
        action: PlannedAction,
        *,
        status: ActionStatus,
        message: str | None = None,
        confirmation_id: str | None = None,
        assistant: str = "jarkko",
        conversation_id: str | None = None,
    ) -> ActionOutcome:
        """Registra una acción que no se ejecutó (rechazada, pendiente o saltada)."""

        text = message or (action.error or {}).get("message") or ""
        outcome = ActionOutcome(
            tool=action.tool_name,
            status=status,
            message=text,
            risk_level=action.risk_level,
            arguments=sanitize_arguments(action.validated_arguments or action.raw_arguments),
            confirmation_id=confirmation_id,
            error=action.error,
        )
        await self._activity.record(
            tool=action.tool_name,
            arguments=action.validated_arguments or action.raw_arguments,
            risk_level=action.risk_level.value,
            status=status.value,
            message=text,
            assistant=assistant,
            conversation_id=conversation_id,
        )
        return outcome
