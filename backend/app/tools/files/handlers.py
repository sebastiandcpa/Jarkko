"""Herramientas de sistema de archivos.

Reglas que aplican a todos los handlers de este módulo:

* las rutas llegan ya normalizadas, resueltas y contenidas en las raíces permitidas
  (el Validator lo garantiza antes de llamar al handler);
* nunca se sobrescribe un destino existente: se devuelve ``CONFLICT``;
* las operaciones que modifican el disco se verifican después (ver
  ``app.services.verification``).
"""

from __future__ import annotations

import fnmatch
import os
import shutil
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.security.risk import RiskLevel
from app.security.validator import ValidationError, is_within
from app.tools.base import (
    ParameterSpec,
    ParamType,
    PathKind,
    ToolCategory,
    ToolDefinition,
    ToolResult,
)
from app.tools.registry import ToolRegistry

#: Carpetas que nunca se recorren al buscar (ruido, privacidad y rendimiento).
PRUNED_DIRECTORY_NAMES = frozenset(
    {
        "appdata",
        "application data",
        "node_modules",
        ".git",
        ".svn",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        "$recycle.bin",
        "system volume information",
        "onedrivetemp",
        ".cache",
        ".gradle",
        ".nuget",
        "site-packages",
    }
)

_INVALID_NAME_CHARS = set('<>:"/\\|?*')


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec="seconds")


def _entry_info(path: Path, *, stat_result: os.stat_result | None = None, is_dir: bool | None = None) -> dict[str, Any]:
    try:
        stat_result = stat_result or path.stat()
        size = stat_result.st_size
        modified = _iso(stat_result.st_mtime)
    except OSError:
        size, modified = None, None
    if is_dir is None:
        try:
            is_dir = path.is_dir()
        except OSError:
            is_dir = False
    return {
        "name": path.name,
        "path": str(path),
        "type": "directory" if is_dir else "file",
        "size": None if is_dir else size,
        "modified": modified,
    }


def _validate_file_name(raw: Any, *, field: str = "new_name") -> str:
    if not isinstance(raw, str):
        raise ValidationError(f"'{field}' debe ser texto.", code="invalid_type", field=field)
    name = raw.strip().strip('"').strip("'")
    if not name:
        raise ValidationError("El nuevo nombre no puede estar vacío.", code="empty_value", field=field)
    if len(name) > 255:
        raise ValidationError("El nuevo nombre es demasiado largo.", code="value_too_long", field=field)
    if name in {".", ".."} or _INVALID_NAME_CHARS & set(name) or "\x00" in name:
        raise ValidationError(
            "El nuevo nombre debe ser un nombre de archivo simple, sin rutas ni caracteres especiales.",
            code="invalid_file_name",
            field=field,
        )
    if name != name.rstrip(" ."):
        raise ValidationError(
            "El nuevo nombre no puede terminar en espacio ni en punto.", code="invalid_file_name", field=field
        )
    return name


def _resolve_target(source: Path, destination: Path) -> Path:
    """Si el destino es una carpeta existente, el objetivo real va dentro de ella."""

    if destination.is_dir():
        return destination / source.name
    return destination


def _pre_transfer_checks(source: Path, target: Path, *, verb: str) -> ToolResult | None:
    if os.path.normcase(str(source)) == os.path.normcase(str(target)):
        return ToolResult.error(
            f"El origen y el destino son la misma ruta; no hay nada que {verb}.",
            source=str(source),
            destination=str(target),
            reason="same_path",
        )
    if not target.parent.exists():
        return ToolResult.error(
            f"La carpeta de destino no existe: {target.parent}",
            destination=str(target),
            reason="destination_parent_missing",
        )
    if target.exists():
        return ToolResult.conflict(
            f"El destino ya existe: {target}. No se sobrescribe nada de forma automática.",
            source=str(source),
            destination=str(target),
            reason="destination_exists",
        )
    if source.is_dir() and is_within(target, source):
        return ToolResult.error(
            "No se puede copiar o mover una carpeta dentro de sí misma.",
            source=str(source),
            destination=str(target),
            reason="recursive_destination",
        )
    return None


# ----------------------------------------------------------------------
# handlers
# ----------------------------------------------------------------------
def list_files(arguments: Mapping[str, Any]) -> ToolResult:
    path: Path = arguments["path"]
    limit: int = int(arguments.get("limit") or 200)
    limit = max(1, min(limit, 1000))

    entries: list[dict[str, Any]] = []
    truncated = False
    try:
        with os.scandir(path) as iterator:
            for entry in iterator:
                if len(entries) >= limit:
                    truncated = True
                    break
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                    stat_result = entry.stat(follow_symlinks=False)
                except OSError:
                    is_dir, stat_result = False, None
                entries.append(_entry_info(Path(entry.path), stat_result=stat_result, is_dir=is_dir))
    except PermissionError:
        return ToolResult.error(
            f"Sin permisos para leer {path}.", path=str(path), reason="permission_denied"
        )
    except OSError as exc:
        return ToolResult.error(f"No se pudo leer {path}: {exc}", path=str(path), reason="os_error")

    entries.sort(key=lambda item: (item["type"] != "directory", item["name"].lower()))
    folders = sum(1 for item in entries if item["type"] == "directory")
    return ToolResult.ok(
        f"{len(entries)} elementos en {path}" + (" (lista recortada)" if truncated else ""),
        path=str(path),
        entries=entries,
        total=len(entries),
        directories=folders,
        files=len(entries) - folders,
        truncated=truncated,
    )


def search_files(arguments: Mapping[str, Any]) -> ToolResult:
    from app.security.paths import USER_PATHS

    settings = get_settings()
    query: str = arguments["query"]
    root: Path = arguments.get("root_path") or USER_PATHS.home
    if len(query) < 2:
        return ToolResult.error(
            "La búsqueda necesita al menos 2 caracteres.", query=query, reason="query_too_short"
        )

    use_glob = any(char in query for char in "*?")
    pattern = query.lower() if use_glob else None
    needle = query.lower()

    matches: list[dict[str, Any]] = []
    scanned = 0
    truncated = False

    for current_root, dir_names, file_names in os.walk(root, topdown=True, onerror=None):
        dir_names[:] = [name for name in dir_names if name.lower() not in PRUNED_DIRECTORY_NAMES]
        for name in (*dir_names, *file_names):
            scanned += 1
            if scanned > settings.search_max_scanned_entries:
                truncated = True
                break
            lowered = name.lower()
            hit = fnmatch.fnmatch(lowered, pattern) if use_glob else needle in lowered
            if not hit:
                continue
            found = Path(current_root) / name
            matches.append(_entry_info(found))
            if len(matches) >= settings.max_search_results:
                truncated = True
                break
        if truncated:
            break

    message = (
        f"Encontré {len(matches)} resultados para «{query}» en {root}."
        if matches
        else f"No encontré nada que coincida con «{query}» en {root}."
    )
    return ToolResult.ok(
        message + (" Búsqueda parcial: se alcanzó el límite." if truncated else ""),
        query=query,
        root_path=str(root),
        results=matches,
        total=len(matches),
        scanned=scanned,
        truncated=truncated,
    )


def open_file(arguments: Mapping[str, Any]) -> ToolResult:
    path: Path = arguments["path"]
    blocked = get_settings().blocked_open_extension_set
    if path.suffix.lower() in blocked:
        return ToolResult.denied(
            f"No abro archivos con extensión '{path.suffix}': abrirlos equivale a ejecutar código.",
            path=str(path),
            reason="executable_extension_blocked",
        )
    try:
        os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606 - solo Windows, ruta validada
    except AttributeError:
        return ToolResult.error(
            "Abrir archivos con la aplicación asociada solo está soportado en Windows.",
            path=str(path),
            reason="unsupported_platform",
        )
    except OSError as exc:
        return ToolResult.error(f"No se pudo abrir {path}: {exc}", path=str(path), reason="os_error")
    return ToolResult.ok(f"Abrí {path.name} con su aplicación predeterminada.", path=str(path))


def open_folder(arguments: Mapping[str, Any]) -> ToolResult:
    path: Path = arguments["path"]
    try:
        os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606 - solo Windows, ruta validada
    except AttributeError:
        return ToolResult.error(
            "Abrir el explorador solo está soportado en Windows.", path=str(path), reason="unsupported_platform"
        )
    except OSError as exc:
        return ToolResult.error(f"No se pudo abrir {path}: {exc}", path=str(path), reason="os_error")
    return ToolResult.ok(f"Abrí la carpeta {path}.", path=str(path))


def create_folder(arguments: Mapping[str, Any]) -> ToolResult:
    path: Path = arguments["path"]
    if path.exists():
        return ToolResult.conflict(
            f"Ya existe algo en {path}.", path=str(path), reason="destination_exists"
        )
    try:
        path.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        return ToolResult.conflict(f"Ya existe algo en {path}.", path=str(path), reason="destination_exists")
    except PermissionError:
        return ToolResult.error(
            f"Sin permisos para crear {path}.", path=str(path), reason="permission_denied"
        )
    except OSError as exc:
        return ToolResult.error(f"No se pudo crear {path}: {exc}", path=str(path), reason="os_error")
    return ToolResult.ok(f"Creé la carpeta {path}.", path=str(path))


def move_file(arguments: Mapping[str, Any]) -> ToolResult:
    source: Path = arguments["source"]
    target = _resolve_target(source, arguments["destination"])
    if (problem := _pre_transfer_checks(source, target, verb="mover")) is not None:
        return problem
    try:
        shutil.move(str(source), str(target))
    except PermissionError:
        return ToolResult.error(
            f"Sin permisos para mover {source}.", source=str(source), reason="permission_denied"
        )
    except OSError as exc:
        return ToolResult.error(f"No se pudo mover {source}: {exc}", source=str(source), reason="os_error")
    return ToolResult.ok(
        f"Moví {source.name} a {target}.", source=str(source), destination=str(target)
    )


def copy_file(arguments: Mapping[str, Any]) -> ToolResult:
    source: Path = arguments["source"]
    target = _resolve_target(source, arguments["destination"])
    if (problem := _pre_transfer_checks(source, target, verb="copiar")) is not None:
        return problem
    try:
        if source.is_dir():
            shutil.copytree(str(source), str(target))
        else:
            shutil.copy2(str(source), str(target))
    except PermissionError:
        return ToolResult.error(
            f"Sin permisos para copiar {source}.", source=str(source), reason="permission_denied"
        )
    except OSError as exc:
        return ToolResult.error(f"No se pudo copiar {source}: {exc}", source=str(source), reason="os_error")
    return ToolResult.ok(
        f"Copié {source.name} a {target}.", source=str(source), destination=str(target)
    )


def rename_file(arguments: Mapping[str, Any]) -> ToolResult:
    source: Path = arguments["source"]
    new_name = _validate_file_name(arguments["new_name"])
    target = source.parent / new_name
    if (problem := _pre_transfer_checks(source, target, verb="renombrar")) is not None:
        return problem
    try:
        source.rename(target)
    except PermissionError:
        return ToolResult.error(
            f"Sin permisos para renombrar {source}.", source=str(source), reason="permission_denied"
        )
    except OSError as exc:
        return ToolResult.error(f"No se pudo renombrar {source}: {exc}", source=str(source), reason="os_error")
    return ToolResult.ok(
        f"Renombré {source.name} a {new_name}.",
        source=str(source),
        destination=str(target),
        new_name=new_name,
    )


def delete_file(arguments: Mapping[str, Any]) -> ToolResult:
    """Borrado permanente de un archivo.  Riesgo CRITICAL, deshabilitado por defecto."""

    path: Path = arguments["path"]
    if path.is_dir():
        return ToolResult.denied(
            "Esta herramienta no borra carpetas.", path=str(path), reason="directories_not_supported"
        )
    try:
        path.unlink()
    except PermissionError:
        return ToolResult.error(
            f"Sin permisos para eliminar {path}.", path=str(path), reason="permission_denied"
        )
    except OSError as exc:
        return ToolResult.error(f"No se pudo eliminar {path}: {exc}", path=str(path), reason="os_error")
    return ToolResult.ok(f"Eliminé {path}.", path=str(path))


# ----------------------------------------------------------------------
# registro
# ----------------------------------------------------------------------
def register(registry: ToolRegistry) -> None:
    settings = get_settings()

    registry.register(
        ToolDefinition(
            name="list_files",
            description="Lista el contenido de una carpeta (archivos y subcarpetas).",
            category=ToolCategory.FILES,
            risk_level=RiskLevel.LOW,
            handler=list_files,
            parameters=(
                ParameterSpec(
                    name="path",
                    type=ParamType.PATH,
                    description="Carpeta a listar. Admite alias como 'Descargas' o 'Documentos'.",
                    must_exist=True,
                    kind=PathKind.DIRECTORY,
                ),
                ParameterSpec(
                    name="limit",
                    type=ParamType.INTEGER,
                    description="Máximo de elementos a devolver (1-1000).",
                    required=False,
                    default=200,
                ),
            ),
            examples=("Lista los archivos de Descargas",),
        )
    )

    registry.register(
        ToolDefinition(
            name="search_files",
            description="Busca archivos y carpetas por nombre (admite comodines * y ?).",
            category=ToolCategory.FILES,
            risk_level=RiskLevel.LOW,
            handler=search_files,
            parameters=(
                ParameterSpec(
                    name="query",
                    type=ParamType.STRING,
                    description="Texto o patrón a buscar en el nombre.",
                    max_length=256,
                ),
                ParameterSpec(
                    name="root_path",
                    type=ParamType.PATH,
                    description="Carpeta donde buscar. Por defecto, el home del usuario.",
                    required=False,
                    must_exist=True,
                    kind=PathKind.DIRECTORY,
                ),
            ),
            examples=("Busca el archivo factura.pdf", "Busca *.png en Imágenes"),
        )
    )

    registry.register(
        ToolDefinition(
            name="open_file",
            description="Abre un archivo con su aplicación predeterminada (no abre ejecutables ni scripts).",
            category=ToolCategory.FILES,
            risk_level=RiskLevel.LOW,
            handler=open_file,
            parameters=(
                ParameterSpec(
                    name="path",
                    type=ParamType.PATH,
                    description="Archivo a abrir.",
                    must_exist=True,
                    kind=PathKind.FILE,
                ),
            ),
            examples=("Abre el archivo Documentos/notas.txt",),
        )
    )

    registry.register(
        ToolDefinition(
            name="open_folder",
            description="Abre una carpeta en el Explorador de Windows.",
            category=ToolCategory.FILES,
            risk_level=RiskLevel.LOW,
            handler=open_folder,
            parameters=(
                ParameterSpec(
                    name="path",
                    type=ParamType.PATH,
                    description="Carpeta a abrir. Admite alias como 'Descargas'.",
                    must_exist=True,
                    kind=PathKind.DIRECTORY,
                ),
            ),
            examples=("Abre la carpeta Descargas",),
        )
    )

    registry.register(
        ToolDefinition(
            name="create_folder",
            description="Crea una carpeta nueva (incluyendo carpetas intermedias).",
            category=ToolCategory.FILES,
            risk_level=RiskLevel.MEDIUM,
            handler=create_folder,
            verify=True,
            parameters=(
                ParameterSpec(
                    name="path",
                    type=ParamType.PATH,
                    description="Ruta completa de la carpeta a crear.",
                    must_exist=False,
                ),
            ),
            examples=("Crea una carpeta llamada Jarvis Test en Documentos",),
        )
    )

    registry.register(
        ToolDefinition(
            name="move_file",
            description="Mueve un archivo o carpeta a otra ubicación. No sobrescribe el destino.",
            category=ToolCategory.FILES,
            risk_level=RiskLevel.MEDIUM,
            handler=move_file,
            verify=True,
            parameters=(
                ParameterSpec(
                    name="source",
                    type=ParamType.PATH,
                    description="Archivo o carpeta de origen.",
                    must_exist=True,
                ),
                ParameterSpec(
                    name="destination",
                    type=ParamType.PATH,
                    description="Ruta destino, o carpeta existente donde colocarlo.",
                ),
            ),
            examples=("Mueve Descargas/foto.png a Imágenes",),
        )
    )

    registry.register(
        ToolDefinition(
            name="copy_file",
            description="Copia un archivo o carpeta a otra ubicación. No sobrescribe el destino.",
            category=ToolCategory.FILES,
            risk_level=RiskLevel.MEDIUM,
            handler=copy_file,
            verify=True,
            parameters=(
                ParameterSpec(
                    name="source",
                    type=ParamType.PATH,
                    description="Archivo o carpeta de origen.",
                    must_exist=True,
                ),
                ParameterSpec(
                    name="destination",
                    type=ParamType.PATH,
                    description="Ruta destino, o carpeta existente donde colocarlo.",
                ),
            ),
            examples=("Copia Documentos/cv.pdf a Escritorio",),
        )
    )

    registry.register(
        ToolDefinition(
            name="rename_file",
            description="Renombra un archivo o carpeta dentro de su misma ubicación.",
            category=ToolCategory.FILES,
            risk_level=RiskLevel.MEDIUM,
            handler=rename_file,
            verify=True,
            parameters=(
                ParameterSpec(
                    name="source",
                    type=ParamType.PATH,
                    description="Archivo o carpeta a renombrar.",
                    must_exist=True,
                ),
                ParameterSpec(
                    name="new_name",
                    type=ParamType.STRING,
                    description="Nuevo nombre simple, sin rutas.",
                    max_length=255,
                ),
            ),
            examples=("Renombra Descargas/doc.txt a notas.txt",),
        )
    )

    # Definida pero bloqueada: exige nivel CRITICAL + confirmación explícita.
    registry.register(
        ToolDefinition(
            name="delete_file",
            description=(
                "Elimina permanentemente un archivo. Riesgo crítico: deshabilitada salvo que se "
                "active JARVIS_ENABLE_CRITICAL_TOOLS y el usuario confirme la acción."
            ),
            category=ToolCategory.FILES,
            risk_level=RiskLevel.CRITICAL,
            handler=delete_file,
            enabled=settings.enable_critical_tools,
            verify=True,
            parameters=(
                ParameterSpec(
                    name="path",
                    type=ParamType.PATH,
                    description="Archivo a eliminar.",
                    must_exist=True,
                    kind=PathKind.FILE,
                ),
            ),
        )
    )
