"""Herramienta de aplicaciones: ``open_application``.

No existe ni existirá una herramienta genérica tipo ``run_command``.  El handler
solo puede lanzar ejecutables que estén en el Application Registry, sin shell y
sin argumentos provenientes del modelo.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Mapping
from typing import Any

from app.security.risk import RiskLevel
from app.tools.applications.catalog import APPLICATIONS, app_names, find_app
from app.tools.base import (
    ParameterSpec,
    ParamType,
    ToolCategory,
    ToolDefinition,
    ToolResult,
)
from app.tools.registry import ToolRegistry

IS_WINDOWS = sys.platform == "win32"


def _launch(executable: str) -> subprocess.Popen[bytes]:
    """Lanza un proceso desacoplado, sin shell y sin argumentos externos."""

    kwargs: dict[str, Any] = {"close_fds": True}
    if IS_WINDOWS:
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP: la app sobrevive al backend.
        kwargs["creationflags"] = 0x00000008 | 0x00000200
    return subprocess.Popen([executable], shell=False, **kwargs)  # noqa: S603 - ruta del catálogo


def open_application(arguments: Mapping[str, Any]) -> ToolResult:
    requested: str = arguments["app_name"]
    spec = find_app(requested)
    if spec is None:
        return ToolResult.error(
            f"No conozco la aplicación «{requested}». Disponibles: {', '.join(app_names())}.",
            requested=requested,
            available=list(app_names()),
            reason="app_not_in_registry",
        )

    executable = spec.resolve()
    if executable is None:
        return ToolResult.error(
            f"{spec.display_name} no parece estar instalada en este equipo.",
            app=spec.key,
            reason="app_not_installed",
        )

    try:
        process = _launch(str(executable))
    except OSError as exc:
        return ToolResult.error(
            f"No se pudo iniciar {spec.display_name}: {exc}",
            app=spec.key,
            reason="launch_failed",
        )

    return ToolResult.ok(
        f"Abrí {spec.display_name}.",
        app=spec.key,
        display_name=spec.display_name,
        executable=str(executable),
        pid=process.pid,
        note=spec.note,
    )


def _escalate_by_app(arguments: Mapping[str, Any]) -> RiskLevel:
    """Abrir una shell exige confirmación; abrir la calculadora no."""

    spec = find_app(str(arguments.get("app_name", "")))
    return spec.risk_level if spec else RiskLevel.LOW


def register(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="open_application",
            description=(
                "Abre una aplicación del catálogo permitido ("
                + ", ".join(spec.display_name for spec in APPLICATIONS)
                + ")."
            ),
            category=ToolCategory.APPLICATIONS,
            risk_level=RiskLevel.LOW,
            handler=open_application,
            escalator=_escalate_by_app,
            parameters=(
                ParameterSpec(
                    name="app_name",
                    type=ParamType.STRING,
                    description="Nombre lógico o alias de la aplicación.",
                    max_length=120,
                ),
            ),
            examples=("Abre el bloc de notas", "Abre Chrome"),
        )
    )
