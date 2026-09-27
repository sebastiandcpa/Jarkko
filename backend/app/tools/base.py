"""Contratos base del Tool Engine.

Una herramienta es un dato, no código disperso: se declara una ``ToolDefinition``
con su nombre, descripción, parámetros, nivel de riesgo y handler.  Nadie fuera
del registry conoce los handlers, y la IA solo puede pedir herramientas que estén
declaradas aquí.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.security.risk import RiskLevel


class ParamType(str, Enum):
    """Tipos admitidos para los parámetros de una herramienta."""

    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    PATH = "path"
    URL = "url"


class PathKind(str, Enum):
    """Qué se espera encontrar en una ruta."""

    ANY = "any"
    FILE = "file"
    DIRECTORY = "directory"


class ToolCategory(str, Enum):
    BROWSER = "browser"
    APPLICATIONS = "applications"
    FILES = "files"
    SYSTEM = "system"


class ToolStatus(str, Enum):
    """Resultado de ejecutar una herramienta."""

    SUCCESS = "success"
    ERROR = "error"
    CONFLICT = "conflict"
    DENIED = "denied"


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    """Declaración de un parámetro, usada por el Validator y por el frontend."""

    name: str
    type: ParamType = ParamType.STRING
    description: str = ""
    required: bool = True
    default: Any = None
    max_length: int = 4096
    # --- solo para ParamType.PATH ---
    must_exist: bool | None = None
    """``True`` exige que exista, ``False`` exige que NO exista, ``None`` indiferente."""
    kind: PathKind = PathKind.ANY

    def to_public(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type.value,
            "description": self.description,
            "required": self.required,
        }
        if self.default is not None:
            data["default"] = self.default
        if self.type is ParamType.PATH:
            data["must_exist"] = self.must_exist
            data["kind"] = self.kind.value
        return data


@dataclass(slots=True)
class ToolResult:
    """Resultado normalizado de un handler."""

    status: ToolStatus
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    verified: bool | None = None
    verification_detail: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status is ToolStatus.SUCCESS

    @classmethod
    def ok(cls, message: str, **data: Any) -> "ToolResult":
        return cls(status=ToolStatus.SUCCESS, message=message, data=data)

    @classmethod
    def error(cls, message: str, **data: Any) -> "ToolResult":
        return cls(status=ToolStatus.ERROR, message=message, data=data)

    @classmethod
    def conflict(cls, message: str, **data: Any) -> "ToolResult":
        return cls(status=ToolStatus.CONFLICT, message=message, data=data)

    @classmethod
    def denied(cls, message: str, **data: Any) -> "ToolResult":
        return cls(status=ToolStatus.DENIED, message=message, data=data)


#: Firma de un handler: recibe los argumentos ya validados y devuelve un resultado.
ToolHandler = Callable[[Mapping[str, Any]], ToolResult]

#: Permite elevar el riesgo según los argumentos concretos (p.ej. abrir PowerShell).
RiskEscalator = Callable[[Mapping[str, Any]], RiskLevel]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Herramienta registrada y ejecutable."""

    name: str
    description: str
    category: ToolCategory
    risk_level: RiskLevel
    handler: ToolHandler
    parameters: tuple[ParameterSpec, ...] = ()
    enabled: bool = True
    """Una herramienta deshabilitada se publica en la API pero nunca se ejecuta."""
    escalator: RiskEscalator | None = None
    verify: bool = False
    """Si ``True``, el VerificationService comprueba el efecto real tras ejecutar."""
    examples: tuple[str, ...] = ()

    def risk_for(self, arguments: Mapping[str, Any]) -> RiskLevel:
        """Riesgo efectivo de una invocación concreta."""

        if self.escalator is None:
            return self.risk_level
        return RiskLevel.max(self.risk_level, self.escalator(arguments))

    def parameter(self, name: str) -> ParameterSpec | None:
        for spec in self.parameters:
            if spec.name == name:
                return spec
        return None

    def to_public(self) -> dict[str, Any]:
        """Representación serializable para ``GET /api/tools``."""

        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "risk_level": self.risk_level.value,
            "enabled": self.enabled,
            "parameters": [spec.to_public() for spec in self.parameters],
            "examples": list(self.examples),
        }


def required_parameter_names(parameters: Sequence[ParameterSpec]) -> tuple[str, ...]:
    return tuple(spec.name for spec in parameters if spec.required)
