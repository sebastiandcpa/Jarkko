"""Fixtures compartidas.

Los tests nunca ejecutan acciones peligrosas: trabajan en directorios temporales,
con una base de datos temporal, y de las herramientas que abren ventanas o el
navegador solo comprueban los caminos de rechazo.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Iterator
from pathlib import Path
from typing import Any, TypeVar

import pytest
from fastapi.testclient import TestClient

from app.agent.engine import AgentEngine, reset_engine
from app.config import get_settings
from app.database.db import reset_database_for_tests
from app.main import app as fastapi_app
from app.providers.factory import get_provider
from app.services.confirmations import confirmation_store
from app.tools.bootstrap import get_registry
from app.voice.listener import reset_listener
from app.voice.service import reset_voice_service

T = TypeVar("T")


def run(awaitable: Awaitable[T]) -> T:
    """Ejecuta una corrutina en un bucle nuevo (evita depender de pytest-asyncio)."""

    return asyncio.run(awaitable)  # type: ignore[arg-type]


def _clear_caches() -> None:
    get_settings.cache_clear()
    get_registry.cache_clear()
    get_provider.cache_clear()
    reset_engine()
    reset_voice_service()
    reset_listener()
    confirmation_store.clear()


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Aísla configuración, base de datos y raíz de archivos permitida."""

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    database = tmp_path / "jarvis-test.db"

    monkeypatch.setenv("JARVIS_EXTRA_ALLOWED_ROOTS", str(workspace))
    monkeypatch.setenv("JARVIS_DATABASE_PATH", str(database))
    monkeypatch.setenv("JARVIS_AI_PROVIDER", "mock")
    monkeypatch.setenv("JARVIS_AI_API_KEY", "")
    monkeypatch.setenv("JARVIS_ENABLE_CRITICAL_TOOLS", "false")
    monkeypatch.setenv("JARVIS_CONFIRMATION_THRESHOLD", "high")
    # La voz se sintetiza de verdad, pero NO se reproduce: los tests son silenciosos.
    monkeypatch.setenv("JARVIS_TTS_PLAYBACK", "false")
    monkeypatch.setenv("JARVIS_TTS_AUTOSPEAK", "false")
    monkeypatch.setenv("JARVIS_TTS_CACHE_DIR", str(tmp_path / "voice"))
    monkeypatch.setenv("JARVIS_ELEVENLABS_API_KEY", "")
    # El micrófono no se abre en los tests.
    monkeypatch.setenv("JARVIS_STT_AUTOSTART", "false")
    monkeypatch.setenv("JARVIS_STT_DEVICE_NAME", "")
    # La escucha se prueba en su modo estricto, independientemente de cómo esté
    # configurada la máquina: un .env del usuario no debe cambiar el resultado.
    monkeypatch.setenv("JARVIS_WAKE_WORD_REQUIRED", "true")

    _clear_caches()
    reset_database_for_tests(database)
    try:
        yield workspace
    finally:
        _clear_caches()


@pytest.fixture
def workspace(isolated_environment: Path) -> Path:
    return isolated_environment


@pytest.fixture
def engine() -> AgentEngine:
    return AgentEngine()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(fastapi_app) as test_client:
        yield test_client


@pytest.fixture
def sample_file(workspace: Path) -> Path:
    path = workspace / "origen.txt"
    path.write_text("contenido de prueba", encoding="utf-8")
    return path


def action_payload(client: TestClient, tool: str, **arguments: Any) -> dict[str, Any]:
    response = client.post("/api/actions/execute", json={"tool": tool, "arguments": arguments})
    assert response.status_code == 200, response.text
    return response.json()
