"""VerificationService: comprobar que la acción ocurrió de verdad.

Una herramienta que no lanza excepción **no** es una herramienta que funcionó.
Para las operaciones que modifican el disco se vuelve a mirar el sistema de
archivos y se compara con el efecto esperado.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.tools.base import ToolDefinition, ToolResult


@dataclass(frozen=True, slots=True)
class VerificationOutcome:
    verified: bool
    detail: str

    def to_public(self) -> dict[str, Any]:
        return {"verified": self.verified, "detail": self.detail}


def _as_path(value: Any) -> Path | None:
    if isinstance(value, Path):
        return value
    if isinstance(value, str) and value:
        return Path(value)
    return None


def _result_path(result: ToolResult, key: str) -> Path | None:
    """Prefiere la ruta real devuelta por el handler sobre la pedida por el usuario."""

    return _as_path(result.data.get(key))


class VerificationService:
    """Verificadores por herramienta.  Ampliable sin tocar los handlers."""

    def verify(
        self,
        tool: ToolDefinition,
        arguments: Mapping[str, Any],
        result: ToolResult,
    ) -> VerificationOutcome | None:
        if not tool.verify or not result.succeeded:
            return None
        checker = getattr(self, f"_verify_{tool.name}", None)
        if checker is None:
            return None
        return checker(arguments, result)

    # ------------------------------------------------------------------
    def _verify_create_folder(
        self, arguments: Mapping[str, Any], result: ToolResult
    ) -> VerificationOutcome:
        path = _result_path(result, "path") or _as_path(arguments.get("path"))
        if path is None:
            return VerificationOutcome(False, "No se pudo determinar la carpeta creada.")
        if path.is_dir():
            return VerificationOutcome(True, f"La carpeta existe en disco: {path}")
        return VerificationOutcome(False, f"La carpeta no aparece en disco: {path}")

    def _verify_move_file(
        self, arguments: Mapping[str, Any], result: ToolResult
    ) -> VerificationOutcome:
        source = _as_path(arguments.get("source"))
        destination = _result_path(result, "destination")
        if destination is None or source is None:
            return VerificationOutcome(False, "Faltan rutas para verificar el movimiento.")
        if destination.exists() and not source.exists():
            return VerificationOutcome(True, f"El origen ya no existe y el destino sí: {destination}")
        if destination.exists() and source.exists():
            return VerificationOutcome(
                False, "El destino existe pero el origen sigue presente: el movimiento quedó a medias."
            )
        return VerificationOutcome(False, f"El destino no existe: {destination}")

    def _verify_copy_file(
        self, arguments: Mapping[str, Any], result: ToolResult
    ) -> VerificationOutcome:
        source = _as_path(arguments.get("source"))
        destination = _result_path(result, "destination")
        if destination is None or source is None:
            return VerificationOutcome(False, "Faltan rutas para verificar la copia.")
        if not destination.exists():
            return VerificationOutcome(False, f"La copia no existe: {destination}")
        if not source.exists():
            return VerificationOutcome(False, "El origen desapareció: no fue una copia.")
        if source.is_file() and destination.is_file():
            try:
                same_size = source.stat().st_size == destination.stat().st_size
            except OSError:
                same_size = False
            if not same_size:
                return VerificationOutcome(False, "La copia existe pero su tamaño no coincide con el origen.")
            return VerificationOutcome(True, f"Copia verificada ({destination.stat().st_size} bytes).")
        return VerificationOutcome(True, f"Copia verificada: {destination}")

    def _verify_rename_file(
        self, arguments: Mapping[str, Any], result: ToolResult
    ) -> VerificationOutcome:
        source = _as_path(arguments.get("source"))
        destination = _result_path(result, "destination")
        if destination is None or source is None:
            return VerificationOutcome(False, "Faltan rutas para verificar el renombrado.")
        if destination.exists() and not source.exists():
            return VerificationOutcome(True, f"El nuevo nombre existe: {destination}")
        return VerificationOutcome(False, f"El renombrado no se refleja en disco: {destination}")

    def _verify_delete_file(
        self, arguments: Mapping[str, Any], result: ToolResult
    ) -> VerificationOutcome:
        path = _result_path(result, "path") or _as_path(arguments.get("path"))
        if path is None:
            return VerificationOutcome(False, "No se pudo determinar el archivo eliminado.")
        if not path.exists():
            return VerificationOutcome(True, f"El archivo ya no existe: {path}")
        return VerificationOutcome(False, f"El archivo sigue existiendo: {path}")


#: Servicio compartido.
verification_service = VerificationService()
