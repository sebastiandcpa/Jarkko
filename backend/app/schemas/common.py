"""Modelos compartidos por varios endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str | None = None
    message: str | None = None
    field: str | None = None


class ActionResult(BaseModel):
    """Resultado de una acción, tal y como lo consume el frontend."""

    tool: str
    status: str = Field(
        description=(
            "success | error | conflict | denied | rejected | awaiting_confirmation | "
            "skipped | cancelled"
        )
    )
    message: str = ""
    risk_level: str = "low"
    arguments: dict[str, Any] = Field(default_factory=dict)
    data: dict[str, Any] = Field(default_factory=dict)
    verified: bool | None = None
    verification_detail: str | None = None
    confirmation_id: str | None = None
    duration_ms: int | None = None
    error: ErrorDetail | None = None


class Confirmation(BaseModel):
    """Acción pendiente de confirmación explícita del usuario."""

    confirmation_id: str
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk_level: str
    description: str = ""
    assistant: str = "jarkko"
    conversation_id: str | None = None
    created_at: str
    expires_at: str
