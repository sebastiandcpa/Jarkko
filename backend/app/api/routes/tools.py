"""``GET /api/tools`` — catálogo de herramientas disponibles."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import RegistryDep, SettingsDep
from app.schemas.tools import Tool, ToolListResponse
from app.security.risk import RISK_DESCRIPTIONS
from app.tools.applications.catalog import catalog as applications_catalog

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("", response_model=ToolListResponse, summary="Herramientas registradas")
async def list_tools(registry: RegistryDep, settings: SettingsDep) -> ToolListResponse:
    return ToolListResponse(
        total=len(registry),
        confirmation_threshold=settings.confirmation_threshold.value,
        risk_levels={level.value: description for level, description in RISK_DESCRIPTIONS.items()},
        tools=[Tool.model_validate(item) for item in registry.catalog()],
        applications=applications_catalog(),
    )


@router.get("/{tool_name}", response_model=Tool, summary="Detalle de una herramienta")
async def get_tool(tool_name: str, registry: RegistryDep) -> Tool:
    tool = registry.get(tool_name)
    if tool is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "tool_not_found", "message": f"No existe la herramienta '{tool_name}'."},
        )
    return Tool.model_validate(tool.to_public())
