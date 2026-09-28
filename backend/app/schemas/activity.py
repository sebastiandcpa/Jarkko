"""Modelos de ``GET /api/activity``."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ActivityEntry(BaseModel):
    id: int
    timestamp: str
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk_level: str
    status: str
    message: str | None = None
    assistant: str | None = None
    conversation_id: str | None = None
    duration_ms: int | None = None
    verified: bool | None = None


class ActivityListResponse(BaseModel):
    total: int
    limit: int
    entries: list[ActivityEntry] = Field(default_factory=list)


class ActivityStatsResponse(BaseModel):
    total: int
    by_status: dict[str, int] = Field(default_factory=dict)
    top_tools: list[dict[str, Any]] = Field(default_factory=list)
