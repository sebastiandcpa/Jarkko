"""Validator: única puerta de entrada de los argumentos hacia los handlers.

Ningún handler recibe datos crudos de la IA o del frontend.  Aquí se comprueba
tipo, longitud, existencia, contención en raíces permitidas y esquema de URL.
Cuando algo no cuadra se lanza ``ValidationError`` y la acción nunca se ejecuta.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from app.config import Settings, get_settings
from app.security.paths import IS_WINDOWS, USER_PATHS, FOLDER_ALIASES, UserPaths
from app.tools.base import ParameterSpec, ParamType, PathKind, ToolDefinition
from app.utils.text import normalize

MAX_URL_LENGTH = 2048

_RESERVED_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CLOCK$"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)

_INVALID_WINDOWS_CHARS = set('<>:"|?*')
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9\-._]*[a-zA-Z0-9])?$")
_BARE_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-._]*\.[a-zA-Z]{2,}(/.*)?$")

#: Subrutas sensibles dentro del home que quedan fuera de alcance del asistente.
_SENSITIVE_RELATIVE_PATHS: tuple[str, ...] = (
    ".ssh",
    ".aws",
    ".gnupg",
    ".azure",
    ".kube",
    ".docker",
    "AppData/Roaming/Microsoft/Crypto",
    "AppData/Roaming/Microsoft/Protect",
    "AppData/Roaming/Microsoft/SystemCertificates",
    "AppData/Local/Microsoft/Credentials",
    "AppData/Local/Microsoft/Vault",
    "AppData/Roaming/Mozilla/Firefox/Profiles",
    "AppData/Local/Google/Chrome/User Data",
    "AppData/Local/Microsoft/Edge/User Data",
    "AppData/Roaming/Bitwarden",
    "AppData/Roaming/KeePass",
)

#: Directorios del sistema prohibidos aunque alguien los añada como raíz extra.
_SYSTEM_DENY_ENV_VARS = ("SystemRoot", "windir", "ProgramFiles", "ProgramFiles(x86)", "ProgramData")


class ValidationError(Exception):
    """Argumento inválido o ruta no permitida."""

    def __init__(self, message: str, *, code: str = "invalid_argument", field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.field = field

    def to_public(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "field": self.field}


class PathValidator:
    """Normaliza y autoriza rutas del sistema de archivos."""

    def __init__(self, settings: Settings | None = None, user_paths: UserPaths | None = None) -> None:
        self._settings = settings or get_settings()
        self.user_paths = user_paths or USER_PATHS

    # ------------------------------------------------------------------
    @property
    def allowed_roots(self) -> tuple[Path, ...]:
        roots = [self.user_paths.home, *self._settings.extra_allowed_root_paths]
        resolved: list[Path] = []
        for root in roots:
            try:
                resolved.append(root.resolve())
            except OSError:
                continue
        return tuple(resolved)

    # ------------------------------------------------------------------
    def validate(
        self,
        raw: Any,
        *,
        field: str = "path",
        must_exist: bool | None = None,
        kind: PathKind = PathKind.ANY,
    ) -> Path:
        """Devuelve una ruta absoluta, normalizada y autorizada."""

        text = self._as_text(raw, field=field)
        expanded = self._expand(text, field=field)
        self._reject_reserved_names(expanded, field=field)
        resolved = self._resolve(expanded, field=field)
        self._reject_system_paths(resolved, field=field)
        self._assert_inside_allowed_roots(resolved, field=field)
        self._reject_sensitive(resolved, field=field)
        self._check_existence(resolved, field=field, must_exist=must_exist, kind=kind)
        return resolved

    # ------------------------------------------------------------------
    def _as_text(self, raw: Any, *, field: str) -> str:
        if isinstance(raw, Path):
            raw = str(raw)
        if not isinstance(raw, str):
            raise ValidationError(f"El parámetro '{field}' debe ser una ruta en texto.", code="invalid_type", field=field)
        text = raw.strip().strip('"').strip("'")
        if not text:
            raise ValidationError(f"El parámetro '{field}' no puede estar vacío.", code="empty_path", field=field)
        if "\x00" in text:
            raise ValidationError("La ruta contiene caracteres nulos.", code="invalid_path", field=field)
        if _CONTROL_CHARS_RE.search(text):
            raise ValidationError("La ruta contiene caracteres de control.", code="invalid_path", field=field)
        if len(text) > 4096:
            raise ValidationError("La ruta es demasiado larga.", code="path_too_long", field=field)
        if text.startswith("\\\\") or text.startswith("//"):
            raise ValidationError(
                "No se permiten rutas de red ni rutas de dispositivo (UNC).", code="unc_not_allowed", field=field
            )
        return text

    def _expand(self, text: str, *, field: str) -> Path:
        candidate = self._apply_folder_alias(text)
        candidate = os.path.expandvars(candidate)
        if "%" in candidate and candidate == text:
            # Variable de entorno inexistente: se deja pasar, resolve() la tratará
            # como nombre literal, pero avisamos de caracteres sospechosos.
            pass
        path = Path(candidate).expanduser()
        if not path.is_absolute():
            path = self.user_paths.home / path
        if IS_WINDOWS:
            for part in path.parts[1:]:
                if _INVALID_WINDOWS_CHARS & set(part):
                    raise ValidationError(
                        "La ruta contiene caracteres no válidos en Windows.", code="invalid_path", field=field
                    )
        return path

    def _apply_folder_alias(self, text: str) -> str:
        """Traduce ``"Descargas/Facturas"`` a la ruta real de Descargas."""

        unified = text.replace("/", os.sep).replace("\\", os.sep)
        head, _, tail = unified.partition(os.sep)
        key = FOLDER_ALIASES.get(normalize(head))
        if key is None:
            return unified
        base = self.user_paths.get(key)
        if base is None:
            return unified
        return str(base / tail) if tail else str(base)

    def _reject_reserved_names(self, path: Path, *, field: str) -> None:
        for part in path.parts:
            stem = part.split(".")[0].strip().upper()
            if stem in _RESERVED_DEVICE_NAMES:
                raise ValidationError(
                    f"'{part}' es un nombre de dispositivo reservado en Windows.",
                    code="reserved_name",
                    field=field,
                )

    def _resolve(self, path: Path, *, field: str) -> Path:
        try:
            return path.resolve()
        except (OSError, RuntimeError) as exc:  # bucles de symlink, rutas inválidas
            raise ValidationError(f"No se pudo normalizar la ruta: {exc}", code="invalid_path", field=field) from exc

    def _reject_system_paths(self, path: Path, *, field: str) -> None:
        for var in _SYSTEM_DENY_ENV_VARS:
            value = os.environ.get(var)
            if not value:
                continue
            try:
                denied = Path(value).resolve()
            except OSError:
                continue
            if is_within(path, denied):
                raise ValidationError(
                    "La ruta pertenece a un directorio protegido del sistema.",
                    code="system_path_denied",
                    field=field,
                )

    def _assert_inside_allowed_roots(self, path: Path, *, field: str) -> None:
        roots = self.allowed_roots
        if any(is_within(path, root) for root in roots):
            return
        allowed = ", ".join(str(root) for root in roots)
        raise ValidationError(
            f"La ruta está fuera de las carpetas permitidas ({allowed}).",
            code="path_outside_allowed_roots",
            field=field,
        )

    def _reject_sensitive(self, path: Path, *, field: str) -> None:
        home = self.user_paths.home
        for relative in _SENSITIVE_RELATIVE_PATHS:
            try:
                denied = (home / relative).resolve()
            except OSError:
                continue
            if is_within(path, denied):
                raise ValidationError(
                    "La ruta contiene datos sensibles y está fuera del alcance del asistente.",
                    code="sensitive_path_denied",
                    field=field,
                )

    def _check_existence(
        self, path: Path, *, field: str, must_exist: bool | None, kind: PathKind
    ) -> None:
        exists = path.exists()
        if must_exist is True and not exists:
            raise ValidationError(f"No existe la ruta: {path}", code="path_not_found", field=field)
        if must_exist is False and exists:
            raise ValidationError(f"La ruta ya existe: {path}", code="path_already_exists", field=field)
        if not exists:
            return
        if kind is PathKind.FILE and not path.is_file():
            raise ValidationError(f"Se esperaba un archivo, no un directorio: {path}", code="not_a_file", field=field)
        if kind is PathKind.DIRECTORY and not path.is_dir():
            raise ValidationError(
                f"Se esperaba una carpeta, no un archivo: {path}", code="not_a_directory", field=field
            )


def is_within(path: Path, root: Path) -> bool:
    """``True`` si ``path`` es ``root`` o está contenida en ``root``."""

    path_text = os.path.normcase(str(path))
    root_text = os.path.normcase(str(root))
    if path_text == root_text:
        return True
    if not root_text.endswith(os.sep):
        root_text += os.sep
    return path_text.startswith(root_text)


def validate_url(raw: Any, *, field: str = "url") -> str:
    """Valida y normaliza una URL http(s).  Rechaza cualquier otro esquema."""

    if not isinstance(raw, str):
        raise ValidationError(f"El parámetro '{field}' debe ser texto.", code="invalid_type", field=field)
    text = raw.strip().strip('"').strip("'")
    if not text:
        raise ValidationError("La URL no puede estar vacía.", code="empty_url", field=field)
    if len(text) > MAX_URL_LENGTH:
        raise ValidationError("La URL es demasiado larga.", code="url_too_long", field=field)
    if _CONTROL_CHARS_RE.search(text) or any(char.isspace() for char in text):
        raise ValidationError("La URL contiene caracteres no válidos.", code="invalid_url", field=field)

    if "://" not in text and _BARE_DOMAIN_RE.match(text):
        text = f"https://{text}"

    parsed = urlparse(text)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValidationError(
            "Solo se permiten URLs http o https.", code="scheme_not_allowed", field=field
        )
    if not parsed.netloc:
        raise ValidationError("La URL no tiene dominio.", code="invalid_url", field=field)
    if "@" in parsed.netloc:
        raise ValidationError("No se permiten credenciales en la URL.", code="credentials_in_url", field=field)
    hostname = parsed.hostname or ""
    if not hostname or not _HOSTNAME_RE.match(hostname):
        raise ValidationError("El dominio de la URL no es válido.", code="invalid_hostname", field=field)
    return urlunparse(parsed._replace(scheme=parsed.scheme.lower()))


def _validate_string(raw: Any, spec: ParameterSpec) -> str:
    if not isinstance(raw, str):
        raise ValidationError(
            f"El parámetro '{spec.name}' debe ser texto.", code="invalid_type", field=spec.name
        )
    text = raw.strip()
    if not text and spec.required:
        raise ValidationError(f"El parámetro '{spec.name}' no puede estar vacío.", code="empty_value", field=spec.name)
    if len(text) > spec.max_length:
        raise ValidationError(
            f"El parámetro '{spec.name}' excede {spec.max_length} caracteres.",
            code="value_too_long",
            field=spec.name,
        )
    if "\x00" in text:
        raise ValidationError(f"El parámetro '{spec.name}' contiene caracteres nulos.", code="invalid_value", field=spec.name)
    return text


def _validate_integer(raw: Any, spec: ParameterSpec) -> int:
    if isinstance(raw, bool):
        raise ValidationError(f"El parámetro '{spec.name}' debe ser un número entero.", code="invalid_type", field=spec.name)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().lstrip("-").isdigit():
        return int(raw.strip())
    raise ValidationError(f"El parámetro '{spec.name}' debe ser un número entero.", code="invalid_type", field=spec.name)


def _validate_boolean(raw: Any, spec: ParameterSpec) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str) and raw.strip().lower() in {"true", "false", "1", "0", "si", "sí", "no"}:
        return raw.strip().lower() in {"true", "1", "si", "sí"}
    raise ValidationError(f"El parámetro '{spec.name}' debe ser booleano.", code="invalid_type", field=spec.name)


class ArgumentValidator:
    """Valida el diccionario de argumentos de una invocación contra su definición."""

    def __init__(self, path_validator: PathValidator | None = None) -> None:
        self.paths = path_validator or PathValidator()

    def validate(self, tool: ToolDefinition, raw_arguments: Mapping[str, Any] | None) -> dict[str, Any]:
        arguments = dict(raw_arguments or {})
        declared = {spec.name for spec in tool.parameters}

        unknown = sorted(set(arguments) - declared)
        if unknown:
            raise ValidationError(
                f"Parámetros no reconocidos para '{tool.name}': {', '.join(unknown)}",
                code="unknown_parameters",
            )

        validated: dict[str, Any] = {}
        for spec in tool.parameters:
            if spec.name not in arguments or arguments[spec.name] is None:
                if spec.required:
                    raise ValidationError(
                        f"Falta el parámetro obligatorio '{spec.name}'.",
                        code="missing_parameter",
                        field=spec.name,
                    )
                if spec.default is not None:
                    validated[spec.name] = spec.default
                continue
            validated[spec.name] = self._coerce(arguments[spec.name], spec)
        return validated

    def _coerce(self, raw: Any, spec: ParameterSpec) -> Any:
        match spec.type:
            case ParamType.STRING:
                return _validate_string(raw, spec)
            case ParamType.INTEGER:
                return _validate_integer(raw, spec)
            case ParamType.BOOLEAN:
                return _validate_boolean(raw, spec)
            case ParamType.URL:
                return validate_url(raw, field=spec.name)
            case ParamType.PATH:
                return self.paths.validate(
                    raw, field=spec.name, must_exist=spec.must_exist, kind=spec.kind
                )
        raise ValidationError(f"Tipo de parámetro no soportado: {spec.type}", code="unsupported_type", field=spec.name)
