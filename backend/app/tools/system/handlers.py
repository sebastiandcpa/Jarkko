"""Herramientas de información del sistema (solo lectura, vía psutil)."""

from __future__ import annotations

import platform
import socket
import sys
from collections.abc import Mapping
from datetime import datetime
from typing import Any

import psutil

from app.config import get_settings
from app.security.paths import USER_PATHS
from app.security.risk import RiskLevel
from app.tools.base import (
    ParameterSpec,
    ParamType,
    ToolCategory,
    ToolDefinition,
    ToolResult,
)
from app.tools.registry import ToolRegistry

_BYTES_IN_GB = 1024**3
_BYTES_IN_MB = 1024**2

PROCESS_SORT_KEYS = ("memory", "cpu", "name", "pid")

_WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def _gb(value: int | float) -> float:
    return round(value / _BYTES_IN_GB, 2)


def _mb(value: int | float) -> float:
    return round(value / _BYTES_IN_MB, 1)


def _primary_disk() -> psutil._common.sdiskusage:
    root = "C:\\" if sys.platform == "win32" else "/"
    try:
        return psutil.disk_usage(root)
    except OSError:
        return psutil.disk_usage(str(USER_PATHS.home))


def snapshot() -> dict[str, Any]:
    """Resumen ligero usado por ``GET /api/system/status`` y el evento ``system.status``."""

    memory = psutil.virtual_memory()
    disk = _primary_disk()
    return {
        "system": "operational",
        "memory_percent": round(memory.percent, 1),
        "disk_percent": round(disk.percent, 1),
        "running_processes": len(psutil.pids()),
        "cpu_percent": round(psutil.cpu_percent(interval=None), 1),
        "uptime_seconds": int(datetime.now().timestamp() - psutil.boot_time()),
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def get_system_info(_: Mapping[str, Any]) -> ToolResult:
    settings = get_settings()
    memory = psutil.virtual_memory()
    boot = datetime.fromtimestamp(psutil.boot_time()).astimezone()
    data = {
        "assistant_version": settings.version,
        "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor() or "desconocido",
        "python_version": platform.python_version(),
        "cpu_cores_physical": psutil.cpu_count(logical=False),
        "cpu_cores_logical": psutil.cpu_count(logical=True),
        "cpu_percent": round(psutil.cpu_percent(interval=0.1), 1),
        "memory_total_gb": _gb(memory.total),
        "memory_used_percent": round(memory.percent, 1),
        "boot_time": boot.isoformat(timespec="seconds"),
        "uptime_seconds": int(datetime.now().timestamp() - psutil.boot_time()),
        "user_paths": USER_PATHS.as_dict(),
    }
    return ToolResult.ok(
        f"{data['os']} · {data['cpu_cores_logical']} núcleos lógicos · {data['memory_total_gb']} GB de RAM.",
        **data,
    )


def get_memory_usage(_: Mapping[str, Any]) -> ToolResult:
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    data = {
        "total_gb": _gb(memory.total),
        "available_gb": _gb(memory.available),
        "used_gb": _gb(memory.used),
        "percent": round(memory.percent, 1),
        "swap_total_gb": _gb(swap.total),
        "swap_percent": round(swap.percent, 1),
    }
    return ToolResult.ok(
        f"RAM al {data['percent']}% ({data['used_gb']} GB de {data['total_gb']} GB en uso).",
        **data,
    )


def get_datetime(_: Mapping[str, Any]) -> ToolResult:
    """Fecha y hora locales.

    Los nombres de día y mes van escritos a mano en español: el locale de Windows
    puede estar en cualquier idioma y la respuesta tiene que sonar siempre igual.
    """

    now = datetime.now().astimezone()
    weekday = _WEEKDAYS[now.weekday()]
    month = _MONTHS[now.month - 1]
    data = {
        "iso": now.isoformat(timespec="seconds"),
        "date": now.strftime("%d/%m/%Y"),
        "time": now.strftime("%H:%M"),
        "weekday": weekday,
        "day": now.day,
        "month": month,
        "year": now.year,
        "timezone": now.tzname() or "",
    }
    return ToolResult.ok(
        f"{weekday.capitalize()} {now.day} de {month} de {now.year}, {data['time']}.",
        **data,
    )


def get_disk_usage(_: Mapping[str, Any]) -> ToolResult:
    partitions: list[dict[str, Any]] = []
    for partition in psutil.disk_partitions(all=False):
        if "cdrom" in partition.opts.lower() or not partition.fstype:
            continue
        try:
            usage = psutil.disk_usage(partition.mountpoint)
        except OSError:
            continue
        partitions.append(
            {
                "device": partition.device,
                "mountpoint": partition.mountpoint,
                "filesystem": partition.fstype,
                "total_gb": _gb(usage.total),
                "used_gb": _gb(usage.used),
                "free_gb": _gb(usage.free),
                "percent": round(usage.percent, 1),
            }
        )

    primary = _primary_disk()
    summary = {
        "partitions": partitions,
        "primary_percent": round(primary.percent, 1),
        "primary_free_gb": _gb(primary.free),
        "primary_total_gb": _gb(primary.total),
    }
    return ToolResult.ok(
        f"Disco principal al {summary['primary_percent']}% "
        f"({summary['primary_free_gb']} GB libres de {summary['primary_total_gb']} GB).",
        **summary,
    )


def get_running_processes(arguments: Mapping[str, Any]) -> ToolResult:
    limit = int(arguments.get("limit") or 25)
    limit = max(1, min(limit, 500))
    sort_by = str(arguments.get("sort_by") or "memory").lower()
    if sort_by not in PROCESS_SORT_KEYS:
        sort_by = "memory"

    processes: list[dict[str, Any]] = []
    for process in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent", "username"]):
        try:
            info = process.info
            memory_info = info.get("memory_info")
            processes.append(
                {
                    "pid": info.get("pid"),
                    "name": info.get("name") or "desconocido",
                    "memory_mb": _mb(memory_info.rss) if memory_info else None,
                    "cpu_percent": round(info.get("cpu_percent") or 0.0, 1),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    total = len(processes)
    match sort_by:
        case "memory":
            processes.sort(key=lambda item: item["memory_mb"] or 0.0, reverse=True)
        case "cpu":
            processes.sort(key=lambda item: item["cpu_percent"] or 0.0, reverse=True)
        case "name":
            processes.sort(key=lambda item: item["name"].lower())
        case "pid":
            processes.sort(key=lambda item: item["pid"] or 0)

    top = processes[:limit]
    return ToolResult.ok(
        f"{total} procesos en ejecución (mostrando {len(top)} por {sort_by}).",
        total=total,
        sort_by=sort_by,
        processes=top,
    )


def register(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="get_system_info",
            description="Devuelve información general del equipo: SO, CPU, RAM total y tiempo encendido.",
            category=ToolCategory.SYSTEM,
            risk_level=RiskLevel.LOW,
            handler=get_system_info,
            examples=("Dame información del sistema",),
        )
    )
    registry.register(
        ToolDefinition(
            name="get_datetime",
            description="Devuelve la fecha y la hora locales del equipo.",
            category=ToolCategory.SYSTEM,
            risk_level=RiskLevel.LOW,
            handler=get_datetime,
            examples=("¿Qué hora es?", "¿Qué día es hoy?"),
        )
    )
    registry.register(
        ToolDefinition(
            name="get_memory_usage",
            description="Devuelve el uso actual de memoria RAM y swap.",
            category=ToolCategory.SYSTEM,
            risk_level=RiskLevel.LOW,
            handler=get_memory_usage,
            examples=("¿Cuánta memoria estoy usando?",),
        )
    )
    registry.register(
        ToolDefinition(
            name="get_disk_usage",
            description="Devuelve el espacio usado y libre de cada disco montado.",
            category=ToolCategory.SYSTEM,
            risk_level=RiskLevel.LOW,
            handler=get_disk_usage,
            examples=("¿Cuánto espacio libre tengo en disco?",),
        )
    )
    registry.register(
        ToolDefinition(
            name="get_running_processes",
            description="Lista los procesos en ejecución ordenados por memoria, CPU, nombre o PID.",
            category=ToolCategory.SYSTEM,
            risk_level=RiskLevel.LOW,
            handler=get_running_processes,
            parameters=(
                ParameterSpec(
                    name="limit",
                    type=ParamType.INTEGER,
                    description="Número de procesos a devolver (1-500).",
                    required=False,
                    default=25,
                ),
                ParameterSpec(
                    name="sort_by",
                    type=ParamType.STRING,
                    description="Criterio de orden: memory, cpu, name o pid.",
                    required=False,
                    default="memory",
                    max_length=16,
                ),
            ),
            examples=("Muéstrame los procesos que más memoria consumen",),
        )
    )
