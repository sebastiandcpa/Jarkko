"""Modelos de ``/api/actions/*``."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ActionResult, Confirmation


class ExecuteActionRequest(BaseModel):
    tool: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)
    assistant: str = Field(default="jarkko", max_length=32)
    conversation_id: str | None = Field(default=None, max_length=64)

    model_config = {
        "json_schema_extra": {
            "examples": [{"tool": "open_url", "arguments": {"url": "https://youtube.com"}}]
        }
    }


class ConfirmActionRequest(BaseModel):
    confirmation_id: str = Field(min_length=8, max_length=128)
    approved: bool = Field(default=True, description="false cancela la acción pendiente.")
    assistant: str | None = Field(default=None, max_length=32)


class ActionResponse(ActionResult):
    """Igual que ``ActionResult``: se expone como respuesta directa."""


class PendingConfirmationsResponse(BaseModel):
    total: int
    confirmations: list[Confirmation] = Field(default_factory=list)
