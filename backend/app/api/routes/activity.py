"""``GET /api/activity`` — historial reciente de acciones."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import ActivityDep, SettingsDep
from app.schemas.activity import ActivityEntry, ActivityListResponse, ActivityStatsResponse

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("", response_model=ActivityListResponse, summary="Últimas acciones registradas")
async def recent_activity(
    activity: ActivityDep,
    settings: SettingsDep,
    limit: int | None = Query(default=None, ge=1, le=500, description="Máximo de entradas."),
    tool: str | None = Query(default=None, max_length=64, description="Filtrar por herramienta."),
    action_status: str | None = Query(
        default=None, alias="status", max_length=32, description="Filtrar por estado."
    ),
) -> ActivityListResponse:
    effective_limit = min(limit or settings.activity_default_limit, settings.activity_max_limit)
    records = await activity.recent(limit=effective_limit, tool=tool, status=action_status)
    entries = [ActivityEntry.model_validate(record.to_public()) for record in records]
    return ActivityListResponse(total=len(entries), limit=effective_limit, entries=entries)


@router.get("/stats", response_model=ActivityStatsResponse, summary="Resumen de actividad")
async def activity_stats(activity: ActivityDep) -> ActivityStatsResponse:
    return ActivityStatsResponse.model_validate(await activity.stats())
