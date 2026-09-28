"""``/api/files/*`` — búsqueda y listado para el frontend.

Aunque sean endpoints de lectura, las rutas vienen del cliente: pasan por el Tool
Engine completo (Validator + Permission Manager) en lugar de tocar el disco
directamente.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.agent.executor import ActionOutcome, ActionStatus
from app.api.deps import EngineDep
from app.schemas.files import (
    FileEntry,
    FileListResponse,
    FileSearchResponse,
    KnownFoldersResponse,
)
from app.security.paths import USER_PATHS

router = APIRouter(prefix="/api/files", tags=["files"])

_HTTP_STATUS_BY_ACTION = {
    ActionStatus.REJECTED: status.HTTP_400_BAD_REQUEST,
    ActionStatus.DENIED: status.HTTP_403_FORBIDDEN,
    ActionStatus.CONFLICT: status.HTTP_409_CONFLICT,
    ActionStatus.AWAITING_CONFIRMATION: status.HTTP_202_ACCEPTED,
}


def _require_success(outcome: ActionOutcome) -> ActionOutcome:
    if outcome.succeeded:
        return outcome
    code = (outcome.error or {}).get("code") or outcome.status.value
    raise HTTPException(
        status_code=_HTTP_STATUS_BY_ACTION.get(outcome.status, status.HTTP_400_BAD_REQUEST),
        detail={"code": code, "message": outcome.message},
    )


@router.get("/search", response_model=FileSearchResponse, summary="Buscar archivos por nombre")
async def search_files(
    engine: EngineDep,
    q: str = Query(min_length=2, max_length=256, description="Texto o patrón (* y ?)."),
    path: str | None = Query(
        default=None, max_length=4096, description="Carpeta donde buscar. Admite alias como 'Descargas'."
    ),
) -> FileSearchResponse:
    arguments: dict[str, object] = {"query": q}
    if path:
        arguments["root_path"] = path
    outcome = _require_success(await engine.execute_action("search_files", arguments, speak=False))
    data = outcome.data
    return FileSearchResponse(
        query=str(data.get("query", q)),
        root_path=str(data.get("root_path", "")),
        total=int(data.get("total", 0)),
        truncated=bool(data.get("truncated", False)),
        scanned=int(data.get("scanned", 0)),
        results=[FileEntry.model_validate(item) for item in data.get("results", [])],
    )


@router.get("/list", response_model=FileListResponse, summary="Listar el contenido de una carpeta")
async def list_files(
    engine: EngineDep,
    path: str = Query(min_length=1, max_length=4096, description="Carpeta a listar."),
    limit: int = Query(default=200, ge=1, le=1000),
) -> FileListResponse:
    outcome = _require_success(
        await engine.execute_action("list_files", {"path": path, "limit": limit}, speak=False)
    )
    data = outcome.data
    return FileListResponse(
        path=str(data.get("path", path)),
        total=int(data.get("total", 0)),
        directories=int(data.get("directories", 0)),
        files=int(data.get("files", 0)),
        truncated=bool(data.get("truncated", False)),
        entries=[FileEntry.model_validate(item) for item in data.get("entries", [])],
    )


@router.get(
    "/known-folders",
    response_model=KnownFoldersResponse,
    summary="Carpetas del usuario (Escritorio, Documentos, Descargas…)",
)
async def known_folders() -> KnownFoldersResponse:
    return KnownFoldersResponse(folders=USER_PATHS.as_dict())
