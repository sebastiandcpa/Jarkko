"""Tests de niveles de riesgo y del Permission Manager."""

from __future__ import annotations

from app.security.permissions import PermissionDecision, PermissionManager
from app.security.risk import RiskLevel
from app.tools.base import ToolCategory, ToolDefinition, ToolResult
from app.tools.bootstrap import build_registry


def _tool(risk: RiskLevel, *, enabled: bool = True) -> ToolDefinition:
    return ToolDefinition(
        name=f"demo_{risk.value}",
        description="herramienta de prueba",
        category=ToolCategory.SYSTEM,
        risk_level=risk,
        handler=lambda _: ToolResult.ok("ok"),
        enabled=enabled,
    )


def test_risk_ordering() -> None:
    assert RiskLevel.HIGH.at_least(RiskLevel.MEDIUM)
    assert RiskLevel.CRITICAL.at_least(RiskLevel.HIGH)
    assert not RiskLevel.LOW.at_least(RiskLevel.MEDIUM)
    assert RiskLevel.max(RiskLevel.LOW, RiskLevel.HIGH, RiskLevel.MEDIUM) is RiskLevel.HIGH
    assert RiskLevel.max() is RiskLevel.LOW


def test_low_and_medium_are_allowed_with_default_threshold() -> None:
    manager = PermissionManager()
    assert manager.evaluate(_tool(RiskLevel.LOW)).decision is PermissionDecision.ALLOW
    assert manager.evaluate(_tool(RiskLevel.MEDIUM)).decision is PermissionDecision.ALLOW


def test_high_requires_confirmation_and_confirmation_unlocks_it() -> None:
    manager = PermissionManager()
    tool = _tool(RiskLevel.HIGH)
    verdict = manager.evaluate(tool)
    assert verdict.decision is PermissionDecision.REQUIRES_CONFIRMATION
    assert verdict.code == "confirmation_required"

    confirmed = manager.evaluate(tool, confirmed=True)
    assert confirmed.decision is PermissionDecision.ALLOW
    assert confirmed.code == "user_confirmed"


def test_critical_is_denied_even_when_confirmed() -> None:
    manager = PermissionManager()
    verdict = manager.evaluate(_tool(RiskLevel.CRITICAL), confirmed=True)
    assert verdict.decision is PermissionDecision.DENY
    assert verdict.code == "critical_tools_disabled"


def test_disabled_tool_is_denied() -> None:
    manager = PermissionManager()
    verdict = manager.evaluate(_tool(RiskLevel.LOW, enabled=False))
    assert verdict.decision is PermissionDecision.DENY
    assert verdict.code == "tool_disabled"


def test_escalated_risk_is_honoured_by_the_permission_manager() -> None:
    manager = PermissionManager()
    tool = build_registry().require("open_application")

    calculadora = manager.evaluate(tool, {"app_name": "calculadora"})
    assert calculadora.decision is PermissionDecision.ALLOW
    assert calculadora.risk_level is RiskLevel.LOW

    powershell = manager.evaluate(tool, {"app_name": "powershell"})
    assert powershell.decision is PermissionDecision.REQUIRES_CONFIRMATION
    assert powershell.risk_level is RiskLevel.HIGH
