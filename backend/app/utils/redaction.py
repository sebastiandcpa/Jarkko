"""Saneado de datos antes de persistirlos o emitirlos.

El registro de actividad no debe contener contraseñas, tokens ni API keys, ni
volcados enormes de datos.  Todo lo que se guarda pasa por aquí.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REDACTED = "[redactado]"
MAX_STRING_LENGTH = 600
MAX_SEQUENCE_ITEMS = 20
MAX_DEPTH = 4

_SENSITIVE_KEY_RE = re.compile(
    r"(pass|pwd|secret|token|api[_-]?key|apikey|credential|clave|contrasena|contraseña|"
    r"auth|bearer|cookie|session|private[_-]?key)",
    re.IGNORECASE,
)


def is_sensitive_key(key: str) -> bool:
    return bool(_SENSITIVE_KEY_RE.search(key))


def sanitize_value(value: Any, *, depth: int = 0) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return value if len(value) <= MAX_STRING_LENGTH else f"{value[:MAX_STRING_LENGTH]}…"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if depth >= MAX_DEPTH:
        return REDACTED
    if isinstance(value, Mapping):
        return sanitize_arguments(value, depth=depth + 1)
    if isinstance(value, Sequence):
        items = [sanitize_value(item, depth=depth + 1) for item in list(value)[:MAX_SEQUENCE_ITEMS]]
        if len(value) > MAX_SEQUENCE_ITEMS:
            items.append(f"… (+{len(value) - MAX_SEQUENCE_ITEMS} elementos)")
        return items
    return str(value)[:MAX_STRING_LENGTH]


def sanitize_arguments(arguments: Mapping[str, Any] | None, *, depth: int = 0) -> dict[str, Any]:
    """Copia saneada de un diccionario: claves sensibles redactadas, valores acotados."""

    if not arguments:
        return {}
    clean: dict[str, Any] = {}
    for key, value in arguments.items():
        name = str(key)
        clean[name] = REDACTED if is_sensitive_key(name) else sanitize_value(value, depth=depth)
    return clean


def redact_structure(value: Any, *, depth: int = 0) -> Any:
    """Redacta claves sensibles y convierte ``Path`` a texto, **sin recortar**.

    Se usa para los datos que viajan al frontend (listados de archivos, procesos):
    ahí el recorte de ``sanitize_value`` falsearía la respuesta.  El registro de
    actividad sigue usando ``sanitize_arguments``, que sí acota tamaños.
    """

    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if depth >= MAX_DEPTH + 2:
        return REDACTED
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if is_sensitive_key(str(key)) else redact_structure(item, depth=depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, Sequence):
        return [redact_structure(item, depth=depth + 1) for item in value]
    return str(value)
