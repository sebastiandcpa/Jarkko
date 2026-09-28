"""Tests de operaciones de archivos, siempre en directorios temporales.

Se ejecutan a través del motor completo (validación → permisos → handler →
verificación), que es lo que hace la API.
"""

from __future__ import annotations

from pathlib import Path

from app.agent.engine import AgentEngine
from tests.conftest import run


def _execute(engine: AgentEngine, tool: str, **arguments: object):
    return run(engine.execute_action(tool, arguments))


# ----------------------------------------------------------------------
# create_folder
# ----------------------------------------------------------------------
def test_create_folder_creates_and_verifies(engine: AgentEngine, workspace: Path) -> None:
    target = workspace / "Jarvis Test"
    outcome = _execute(engine, "create_folder", path=str(target))
    assert outcome.status.value == "success", outcome.message
    assert outcome.verified is True
    assert target.is_dir()


def test_create_folder_reports_conflict_when_it_already_exists(
    engine: AgentEngine, workspace: Path
) -> None:
    target = workspace / "existente"
    target.mkdir()
    outcome = _execute(engine, "create_folder", path=str(target))
    assert outcome.status.value == "rejected"
    assert outcome.error is not None
    assert outcome.error["code"] == "path_already_exists"


# ----------------------------------------------------------------------
# copy / move / rename
# ----------------------------------------------------------------------
def test_copy_file_copies_and_verifies(engine: AgentEngine, workspace: Path, sample_file: Path) -> None:
    destination = workspace / "copia.txt"
    outcome = _execute(engine, "copy_file", source=str(sample_file), destination=str(destination))
    assert outcome.status.value == "success", outcome.message
    assert outcome.verified is True
    assert destination.read_text(encoding="utf-8") == "contenido de prueba"
    assert sample_file.exists()


def test_copy_into_existing_directory_uses_the_source_name(
    engine: AgentEngine, workspace: Path, sample_file: Path
) -> None:
    folder = workspace / "destino"
    folder.mkdir()
    outcome = _execute(engine, "copy_file", source=str(sample_file), destination=str(folder))
    assert outcome.status.value == "success"
    assert (folder / sample_file.name).is_file()


def test_existing_destination_is_never_overwritten(
    engine: AgentEngine, workspace: Path, sample_file: Path
) -> None:
    destination = workspace / "ocupado.txt"
    destination.write_text("no me toques", encoding="utf-8")

    outcome = _execute(engine, "copy_file", source=str(sample_file), destination=str(destination))
    assert outcome.status.value == "conflict"
    assert destination.read_text(encoding="utf-8") == "no me toques"

    outcome = _execute(engine, "move_file", source=str(sample_file), destination=str(destination))
    assert outcome.status.value == "conflict"
    assert destination.read_text(encoding="utf-8") == "no me toques"
    assert sample_file.exists()


def test_move_file_moves_and_verifies(engine: AgentEngine, workspace: Path, sample_file: Path) -> None:
    destination = workspace / "movido.txt"
    outcome = _execute(engine, "move_file", source=str(sample_file), destination=str(destination))
    assert outcome.status.value == "success", outcome.message
    assert outcome.verified is True
    assert destination.is_file()
    assert not sample_file.exists()


def test_rename_file_renames_and_verifies(engine: AgentEngine, sample_file: Path) -> None:
    outcome = _execute(engine, "rename_file", source=str(sample_file), new_name="renombrado.txt")
    assert outcome.status.value == "success", outcome.message
    assert outcome.verified is True
    assert (sample_file.parent / "renombrado.txt").is_file()
    assert not sample_file.exists()


def test_rename_rejects_names_that_contain_paths(engine: AgentEngine, sample_file: Path) -> None:
    outcome = _execute(engine, "rename_file", source=str(sample_file), new_name="..\\fuera.txt")
    assert outcome.status.value == "denied"
    assert sample_file.exists()


def test_move_outside_allowed_roots_is_rejected(engine: AgentEngine, sample_file: Path) -> None:
    outcome = _execute(engine, "move_file", source=str(sample_file), destination="C:\\Windows\\jarvis.txt")
    assert outcome.status.value == "rejected"
    assert sample_file.exists()


# ----------------------------------------------------------------------
# lectura
# ----------------------------------------------------------------------
def test_list_files_lists_directories_first(engine: AgentEngine, workspace: Path) -> None:
    (workspace / "carpeta").mkdir()
    (workspace / "zeta.txt").write_text("z", encoding="utf-8")
    (workspace / "alfa.txt").write_text("a", encoding="utf-8")

    outcome = _execute(engine, "list_files", path=str(workspace))
    assert outcome.status.value == "success"
    names = [entry["name"] for entry in outcome.data["entries"]]
    assert names == ["carpeta", "alfa.txt", "zeta.txt"]
    assert outcome.data["directories"] == 1


def test_search_files_finds_by_substring_and_wildcard(engine: AgentEngine, workspace: Path) -> None:
    nested = workspace / "facturas" / "2026"
    nested.mkdir(parents=True)
    (nested / "factura-enero.pdf").write_text("x", encoding="utf-8")

    outcome = _execute(engine, "search_files", query="factura-enero", root_path=str(workspace))
    assert outcome.status.value == "success"
    assert any(item["name"] == "factura-enero.pdf" for item in outcome.data["results"])

    outcome = _execute(engine, "search_files", query="*.pdf", root_path=str(workspace))
    assert outcome.data["total"] == 1


def test_open_file_refuses_executable_extensions(engine: AgentEngine, workspace: Path) -> None:
    script = workspace / "peligro.bat"
    script.write_text("@echo off", encoding="utf-8")
    outcome = _execute(engine, "open_file", path=str(script))
    assert outcome.status.value == "denied"
    assert "extensión" in outcome.message


def test_delete_file_is_blocked_by_default(engine: AgentEngine, sample_file: Path) -> None:
    outcome = _execute(engine, "delete_file", path=str(sample_file))
    assert outcome.status.value == "rejected"
    assert outcome.error is not None
    assert outcome.error["code"] in {"tool_disabled", "critical_tools_disabled"}
    assert sample_file.exists()


def test_there_is_no_generic_command_tool(engine: AgentEngine) -> None:
    for name in ("run_command", "execute_command", "shell", "powershell"):
        assert engine.registry.get(name) is None
        outcome = _execute(engine, name, command="dir")
        assert outcome.status.value == "rejected"
