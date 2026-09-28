"""Modelos de ``/api/health`` y ``/api/system/*``."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    assistant: str = "jarvis-ekko"
    """Nombre del backend. La identidad del asistente es JARKKO (ver 'assistants')."""
    version: str
    assistants: list[dict[str, Any]] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    voice: dict[str, Any] = Field(default_factory=dict)
    ai_provider: dict[str, Any] = Field(default_factory=dict)
    tools_registered: int = 0
    confirmation_threshold: str = "high"
    critical_tools_enabled: bool = False
    websocket: str = "/ws/events"
    uptime_seconds: int = 0


class SystemStatusResponse(BaseModel):
    system: str = "operational"
    memory_percent: float
    disk_percent: float
    running_processes: int
    cpu_percent: float = 0.0
    uptime_seconds: int = 0
    timestamp: str


class SystemInfoResponse(BaseModel):
    info: dict[str, Any] = Field(default_factory=dict)
    memory: dict[str, Any] = Field(default_factory=dict)
    disk: dict[str, Any] = Field(default_factory=dict)
    user_paths: dict[str, str] = Field(default_factory=dict)
