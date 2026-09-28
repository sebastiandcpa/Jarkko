"""Modelos de ``GET /api/tools``."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    name: str
    type: str
    description: str = ""
    required: bool = True
    default: Any = None
    must_exist: bool | None = None
    kind: str | None = None


class Tool(BaseModel):
    name: str
    description: str
    category: str
    risk_level: str
    enabled: bool = True
    parameters: list[ToolParameter] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


class ToolListResponse(BaseModel):
    total: int
    confirmation_threshold: str
    risk_levels: dict[str, str] = Field(default_factory=dict)
    tools: list[Tool] = Field(default_factory=list)
    applications: list[dict[str, Any]] = Field(default_factory=list)
