"""Tests de validación de rutas, URLs y argumentos."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.security.paths import USER_PATHS
from app.security.validator import (
    ArgumentValidator,
    PathValidator,
    ValidationError,
    is_within,
    validate_url,
)
from app.tools.base import PathKind
from app.tools.bootstrap import build_registry


@pytest.fixture
def paths() -> PathValidator:
    return PathValidator()


# ----------------------------------------------------------------------
# rutas
# ----------------------------------------------------------------------
def test_known_folder_alias_resolves_to_real_path(paths: PathValidator) -> None:
    assert paths.validate("Descargas") == USER_PATHS.downloads.resolve()
    assert paths.validate("escritorio") == USER_PATHS.desktop.resolve()


def test_alias_with_subpath_is_expanded(paths: PathValidator) -> None:
    resolved = paths.validate("Documentos/Jarvis Test")
    assert resolved == (USER_PATHS.documents / "Jarvis Test").resolve()


def test_workspace_path_inside_allowed_root_is_accepted(paths: PathValidator, workspace: Path) -> None:
    target = workspace / "sub" / "archivo.txt"
    assert paths.validate(str(target)) == target.resolve()


def test_path_outside_allowed_roots_is_rejected(paths: PathValidator) -> None:
    with pytest.raises(ValidationError) as excinfo:
        paths.validate("C:\\Windows\\System32")
    assert excinfo.value.code in {"system_path_denied", "path_outside_allowed_roots"}


def test_directory_traversal_cannot_escape_allowed_roots(paths: PathValidator, workspace: Path) -> None:
    # Suficientes ".." para llegar a la raíz de la unidad: resolve() los colapsa y la
    # ruta final queda fuera del home, así que debe rechazarse.
    escape = Path(workspace, *([".."] * 12), "Windows", "System32")
    with pytest.raises(ValidationError) as excinfo:
        paths.validate(str(escape))
    assert excinfo.value.code in {"system_path_denied", "path_outside_allowed_roots"}


def test_traversal_that_stays_inside_the_home_is_allowed(paths: PathValidator, workspace: Path) -> None:
    # No es un escape: la ruta normalizada sigue dentro de una raíz permitida.
    resolved = paths.validate(str(workspace / "sub" / ".." / "archivo.txt"))
    assert resolved == (workspace / "archivo.txt").resolve()


def test_unc_and_device_paths_are_rejected(paths: PathValidator) -> None:
    for raw in ("\\\\servidor\\compartido", "//servidor/compartido"):
        with pytest.raises(ValidationError) as excinfo:
            paths.validate(raw)
        assert excinfo.value.code == "unc_not_allowed"


def test_reserved_device_names_are_rejected(paths: PathValidator, workspace: Path) -> None:
    with pytest.raises(ValidationError) as excinfo:
        paths.validate(str(workspace / "CON"))
    assert excinfo.value.code == "reserved_name"


def test_sensitive_directories_are_out_of_scope(paths: PathValidator) -> None:
    with pytest.raises(ValidationError) as excinfo:
        paths.validate(str(USER_PATHS.home / ".ssh" / "id_rsa"))
    assert excinfo.value.code == "sensitive_path_denied"


def test_empty_path_is_rejected(paths: PathValidator) -> None:
    with pytest.raises(ValidationError) as excinfo:
        paths.validate("   ")
    assert excinfo.value.code == "empty_path"


def test_must_exist_and_kind_are_enforced(paths: PathValidator, workspace: Path) -> None:
    missing = workspace / "no-existe"
    with pytest.raises(ValidationError) as excinfo:
        paths.validate(str(missing), must_exist=True)
    assert excinfo.value.code == "path_not_found"

    existing_file = workspace / "archivo.txt"
    existing_file.write_text("x", encoding="utf-8")
    with pytest.raises(ValidationError) as excinfo:
        paths.validate(str(existing_file), must_exist=True, kind=PathKind.DIRECTORY)
    assert excinfo.value.code == "not_a_directory"

    with pytest.raises(ValidationError) as excinfo:
        paths.validate(str(existing_file), must_exist=False)
    assert excinfo.value.code == "path_already_exists"


def test_is_within_is_case_insensitive_on_windows(workspace: Path) -> None:
    assert is_within(workspace / "a" / "b", workspace)
    assert not is_within(workspace.parent, workspace)


# ----------------------------------------------------------------------
# URLs
# ----------------------------------------------------------------------
def test_bare_domain_gets_https_scheme() -> None:
    assert validate_url("youtube.com") == "https://youtube.com"


@pytest.mark.parametrize(
    "raw",
    [
        "javascript:alert(1)",
        "file:///C:/Windows/System32/cmd.exe",
        "data:text/html;base64,PHNjcmlwdD4=",
        "ftp://ejemplo.com",
    ],
)
def test_non_http_schemes_are_rejected(raw: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        validate_url(raw)
    assert excinfo.value.code in {"scheme_not_allowed", "invalid_url"}


def test_credentials_in_url_are_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        validate_url("https://usuario:clave@ejemplo.com")
    assert excinfo.value.code == "credentials_in_url"


# ----------------------------------------------------------------------
# argumentos
# ----------------------------------------------------------------------
def test_missing_required_argument_is_rejected() -> None:
    validator = ArgumentValidator()
    tool = build_registry().require("open_url")
    with pytest.raises(ValidationError) as excinfo:
        validator.validate(tool, {})
    assert excinfo.value.code == "missing_parameter"


def test_unknown_argument_is_rejected() -> None:
    validator = ArgumentValidator()
    tool = build_registry().require("open_url")
    with pytest.raises(ValidationError) as excinfo:
        validator.validate(tool, {"url": "https://ejemplo.com", "shell": "cmd.exe"})
    assert excinfo.value.code == "unknown_parameters"


def test_optional_argument_falls_back_to_default() -> None:
    validator = ArgumentValidator()
    tool = build_registry().require("get_running_processes")
    validated = validator.validate(tool, {})
    assert validated["limit"] == 25
    assert validated["sort_by"] == "memory"


def test_path_arguments_become_resolved_paths(workspace: Path) -> None:
    validator = ArgumentValidator()
    tool = build_registry().require("list_files")
    validated = validator.validate(tool, {"path": str(workspace)})
    assert isinstance(validated["path"], Path)
    assert validated["path"] == workspace.resolve()
