"""``POST /api/chat`` — entrada principal en lenguaje natural."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import EngineDep
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse, summary="Hablar con el asistente")
async def chat(payload: ChatRequest, engine: EngineDep) -> ChatResponse:
    outcome = await engine.chat(
        payload.message,
        assistant=payload.assistant,
        conversation_id=payload.conversation_id,
    )
    return ChatResponse.model_validate(outcome.to_public())
