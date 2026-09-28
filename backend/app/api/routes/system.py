"""``/api/system/*`` — estado del equipo.

Estos endpoints son de solo lectura y no reciben ningún dato del usuario, así que
consultan psutil directamente sin pasar por el Tool Engine (evita inundar el
registro de actividad con los sondeos periódicos del frontend).
"""

from __future__ import annotations

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from app.schemas.system import SystemInfoResponse, SystemStatusResponse
from app.security.paths import USER_PATHS
from app.tools.system.handlers import (
    get_disk_usage,
    get_memory_usage,
    get_system_info,
    snapshot,
)

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status", response_model=SystemStatusResponse, summary="Resumen rápido del sistema")
async def system_status() -> SystemStatusResponse:
    data = await run_in_threadpool(snapshot)
    return SystemStatusResponse(**data)


@router.get("/info", response_model=SystemInfoResponse, summary="Información detallada del equipo")
async def system_info() -> SystemInfoResponse:
    info = await run_in_threadpool(get_system_info, {})
    memory = await run_in_threadpool(get_memory_usage, {})
    disk = await run_in_threadpool(get_disk_usage, {})
    return SystemInfoResponse(
        info=info.data,
        memory=memory.data,
        disk=disk.data,
        user_paths=USER_PATHS.as_dict(),
    )
