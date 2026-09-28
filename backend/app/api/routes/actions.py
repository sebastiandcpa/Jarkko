"""``/api/actions/*`` — ejecución directa y confirmaciones.

``POST /api/actions/execute`` no ejecuta nada de riesgo alto: devuelve
``status: awaiting_confirmation`` junto a un ``confirmation_id`` que el frontend
debe confirmar en ``POST /api/actions/confirm``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import ConfirmationsDep, EngineDep
from app.schemas.actions import (
    ActionResponse,
    ConfirmActionRequest,
    ExecuteActionRequest,
    PendingConfirmationsResponse,
)
from app.services.confirmations import ConfirmationError

router = APIRouter(prefix="/api/actions", tags=["actions"])


@router.post("/execute", response_model=ActionResponse, summary="Ejecutar una herramienta")
async def execute_action(payload: ExecuteActionRequest, engine: EngineDep) -> ActionResponse:
    outcome = await engine.execute_action(
        payload.tool,
        payload.arguments,
        assistant=payload.assistant,
        conversation_id=payload.conversation_id,
    )
    return ActionResponse.model_validate(outcome.to_public())


@router.post("/confirm", response_model=ActionResponse, summary="Confirmar o cancelar una acción")
async def confirm_action(payload: ConfirmActionRequest, engine: EngineDep) -> ActionResponse:
    try:
        outcome = await engine.confirm(
            payload.confirmation_id, approved=payload.approved, assistant=payload.assistant
        )
    except ConfirmationError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return ActionResponse.model_validate(outcome.to_public())


@router.get("/pending", response_model=PendingConfirmationsResponse, summary="Confirmaciones pendientes")
async def pending_confirmations(confirmations: ConfirmationsDep) -> PendingConfirmationsResponse:
    items = [item.to_public() for item in confirmations.pending()]
    return PendingConfirmationsResponse(total=len(items), confirmations=items)
