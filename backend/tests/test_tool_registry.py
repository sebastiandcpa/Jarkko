"""Tests del Tool Registry y de la coherencia del catálogo."""

from __future__ import annotations

import pytest

from app.security.risk import RiskLevel
from app.tools.base import ToolCategory, ToolDefinition, ToolResult
from app.tools.bootstrap import build_registry
from app.tools.registry import DuplicateToolError, ToolNotFoundError, ToolRegistry

MVP_TOOLS = {
    "open_url",
    "web_search",
    "open_application",
    "list_files",
    "search_files",
    "open_file",
    "open_folder",
    "create_folder",
    "move_file",
    "copy_file",
    "rename_file",
    "get_system_info",
    "get_disk_usage",
    "get_memory_usage",
    "get_running_processes",
}

EXPECTED_RISK = {
    "open_url": RiskLevel.LOW,
    "web_search": RiskLevel.LOW,
    "open_application": RiskLevel.LOW,
    "list_files": RiskLevel.LOW,
    "search_files": RiskLevel.LOW,
    "open_file": RiskLevel.LOW,
    "open_folder": RiskLevel.LOW,
    "create_folder": RiskLevel.MEDIUM,
    "move_file": RiskLevel.MEDIUM,
    "copy_file": RiskLevel.MEDIUM,
    "rename_file": RiskLevel.MEDIUM,
    "delete_file": RiskLevel.CRITICAL,
}


def _dummy(_: object) -> ToolResult:  # pragma: no cover - nunca se ejecuta
    return ToolResult.ok("dummy")


def test_registry_contains_every_mvp_tool() -> None:
    registry = build_registry()
    assert MVP_TOOLS.issubset(set(registry.names()))


def test_risk_levels_match_the_specification() -> None:
    registry = build_registry()
    for name, expected in EXPECTED_RISK.items():
        assert registry.require(name).risk_level is expected, name


def test_delete_file_is_defined_but_disabled_by_default() -> None:
    registry = build_registry()
    delete_file = registry.require("delete_file")
    assert delete_file.risk_level is RiskLevel.CRITICAL
    assert delete_file.enabled is False


def test_every_tool_has_description_and_callable_handler() -> None:
    for tool in build_registry():
        assert tool.description.strip(), tool.name
        assert callable(tool.handler), tool.name
        assert isinstance(tool.category, ToolCategory)


def test_duplicate_registration_is_rejected() -> None:
    registry = ToolRegistry()
    definition = ToolDefinition(
        name="demo",
        description="demo",
        category=ToolCategory.SYSTEM,
        risk_level=RiskLevel.LOW,
        handler=_dummy,
    )
    registry.register(definition)
    with pytest.raises(DuplicateToolError):
        registry.register(definition)


def test_unknown_tool_raises() -> None:
    registry = build_registry()
    assert registry.get("no_existe") is None
    with pytest.raises(ToolNotFoundError):
        registry.require("no_existe")


def test_catalog_is_serializable_and_sorted() -> None:
    catalog = build_registry().catalog()
    assert catalog
    for entry in catalog:
        assert set(entry) >= {"name", "description", "category", "risk_level", "enabled", "parameters"}
    categories = [entry["category"] for entry in catalog]
    assert categories == sorted(categories)


def test_prompt_description_excludes_disabled_tools() -> None:
    description = build_registry().describe_for_prompt()
    assert "open_url" in description
    assert "delete_file" not in description


def test_open_application_escalates_risk_for_shells() -> None:
    tool = build_registry().require("open_application")
    assert tool.risk_for({"app_name": "calculadora"}) is RiskLevel.LOW
    assert tool.risk_for({"app_name": "powershell"}) is RiskLevel.HIGH
