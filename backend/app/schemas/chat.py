"""Modelos de ``POST /api/chat``."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ActionResult, Confirmation


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000, description="Mensaje del usuario.")
    assistant: str = Field(
        default="jarkko",
        max_length=32,
        description="Identidad: 'jarkko'. Se aceptan los alias 'jarvis' y 'ekko'.",
    )
    conversation_id: str | None = Field(
        default=None, max_length=64, description="Para continuar una conversación existente."
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{"message": "Abre YouTube", "assistant": "jarkko"}]
        }
    }


class ChatResponse(BaseModel):
    conversation_id: str
    assistant: str
    message: str
    status: str = Field(description="success | error | awaiting_confirmation | no_action")
    actions: list[ActionResult] = Field(default_factory=list)
    requires_confirmation: bool = False
    confirmations: list[Confirmation] = Field(default_factory=list)
    intent: dict[str, Any] | None = None
