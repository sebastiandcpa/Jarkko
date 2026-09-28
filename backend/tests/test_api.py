"""Tests de la API HTTP.

Ninguna prueba abre ventanas, navegadores ni procesos: las acciones de riesgo se
comprueban hasta el punto de la confirmación y después se cancelan.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


# ----------------------------------------------------------------------
# health / tools / system
# ----------------------------------------------------------------------
def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["assistant"] == "jarvis-ekko"
    assert body["version"] == "0.1.0"
    assert body["tools_registered"] >= 15
    assert body["ai_provider"]["name"] == "mock"
    assert [item["key"] for item in body["assistants"]] == ["jarkko"]
    assert {"jarvis", "ekko"} <= set(body["aliases"])
    assert body["voice"]["enabled"] is True


def test_root_endpoint(client: TestClient) -> None:
    body = client.get("/").json()
    assert body["identity"] == "jarkko"
    assert body["aliases"] == ["jarvis", "ekko"]
    assert body["websocket"] == "/ws/events"


def test_system_status(client: TestClient) -> None:
    body = client.get("/api/system/status").json()
    assert body["system"] == "operational"
    assert 0 <= body["memory_percent"] <= 100
    assert 0 <= body["disk_percent"] <= 100
    assert body["running_processes"] > 0


def test_tools_catalog(client: TestClient) -> None:
    body = client.get("/api/tools").json()
    names = {tool["name"] for tool in body["tools"]}
    assert {"open_url", "create_folder", "get_system_info"} <= names
    assert body["confirmation_threshold"] == "high"
    assert "run_command" not in names

    delete_file = next(tool for tool in body["tools"] if tool["name"] == "delete_file")
    assert delete_file["risk_level"] == "critical"
    assert delete_file["enabled"] is False


def test_tool_detail_and_404(client: TestClient) -> None:
    assert client.get("/api/tools/open_url").json()["name"] == "open_url"
    assert client.get("/api/tools/no_existe").status_code == 404


# ----------------------------------------------------------------------
# chat
# ----------------------------------------------------------------------
def test_chat_with_a_read_only_action(client: TestClient) -> None:
    response = client.post("/api/chat", json={"message": "¿cuánta memoria estoy usando?"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["requires_confirmation"] is False
    assert body["actions"][0]["tool"] == "get_memory_usage"
    assert body["actions"][0]["status"] == "success"
    assert body["conversation_id"]
    assert body["message"].startswith("Hecho.")
    assert body["assistant"] == "jarkko"


def test_legacy_identities_resolve_to_jarkko(client: TestClient) -> None:
    """JARVIS y EKKO son el mismo asistente: un solo motor, una sola personalidad."""

    jarvis = client.post("/api/chat", json={"message": "hola", "assistant": "jarvis"}).json()
    ekko = client.post("/api/chat", json={"message": "hola", "assistant": "ekko"}).json()
    jarkko = client.post("/api/chat", json={"message": "hola", "assistant": "jarkko"}).json()
    assert jarvis["assistant"] == ekko["assistant"] == jarkko["assistant"] == "jarkko"
    assert jarvis["message"] == ekko["message"] == jarkko["message"]
    assert jarvis["status"] == "no_action"


def test_unknown_assistant_falls_back_to_jarkko(client: TestClient) -> None:
    body = client.post("/api/chat", json={"message": "hola", "assistant": "ultron"}).json()
    assert body["assistant"] == "jarkko"


def test_chat_keeps_the_conversation_id(client: TestClient) -> None:
    first = client.post("/api/chat", json={"message": "hola"}).json()
    second = client.post(
        "/api/chat", json={"message": "hola", "conversation_id": first["conversation_id"]}
    ).json()
    assert second["conversation_id"] == first["conversation_id"]


def test_chat_rejects_an_empty_message(client: TestClient) -> None:
    assert client.post("/api/chat", json={"message": ""}).status_code == 422


def test_chat_does_not_understand_gibberish(client: TestClient) -> None:
    body = client.post("/api/chat", json={"message": "asdfgh qwerty zxcvbn"}).json()
    assert body["status"] == "no_action"
    assert body["actions"] == []


# ----------------------------------------------------------------------
# confirmaciones (sin ejecutar nada)
# ----------------------------------------------------------------------
def test_high_risk_action_requires_confirmation_and_can_be_cancelled(client: TestClient) -> None:
    body = client.post("/api/chat", json={"message": "abre powershell"}).json()
    assert body["status"] == "awaiting_confirmation"
    assert body["requires_confirmation"] is True

    confirmation = body["confirmations"][0]
    assert confirmation["tool"] == "open_application"
    assert confirmation["risk_level"] == "high"

    pending = client.get("/api/actions/pending").json()
    assert pending["total"] == 1

    cancelled = client.post(
        "/api/actions/confirm",
        json={"confirmation_id": confirmation["confirmation_id"], "approved": False},
    ).json()
    assert cancelled["status"] == "cancelled"

    assert client.get("/api/actions/pending").json()["total"] == 0


def test_confirmations_are_single_use(client: TestClient) -> None:
    body = client.post(
        "/api/actions/execute",
        json={"tool": "open_application", "arguments": {"app_name": "powershell"}},
    ).json()
    assert body["status"] == "awaiting_confirmation"
    confirmation_id = body["confirmation_id"]

    first = client.post(
        "/api/actions/confirm", json={"confirmation_id": confirmation_id, "approved": False}
    )
    assert first.status_code == 200

    second = client.post(
        "/api/actions/confirm", json={"confirmation_id": confirmation_id, "approved": False}
    )
    assert second.status_code == 404
    assert second.json()["detail"]["code"] == "confirmation_not_found"


def test_unknown_confirmation_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/actions/confirm", json={"confirmation_id": "inexistente-000000", "approved": True}
    )
    assert response.status_code == 404


# ----------------------------------------------------------------------
# acciones directas
# ----------------------------------------------------------------------
def test_execute_rejects_unknown_tools(client: TestClient) -> None:
    body = client.post("/api/actions/execute", json={"tool": "run_command", "arguments": {"cmd": "dir"}}).json()
    assert body["status"] == "rejected"
    assert body["error"]["code"] == "tool_not_found"


def test_execute_rejects_a_malicious_url(client: TestClient) -> None:
    body = client.post(
        "/api/actions/execute",
        json={"tool": "open_url", "arguments": {"url": "file:///C:/Windows/System32/cmd.exe"}},
    ).json()
    assert body["status"] == "rejected"
    assert body["error"]["code"] == "scheme_not_allowed"


def test_execute_creates_a_folder_and_logs_it(client: TestClient, workspace: Path) -> None:
    target = workspace / "desde-api"
    body = client.post(
        "/api/actions/execute",
        json={"tool": "create_folder", "arguments": {"path": str(target)}},
    ).json()
    assert body["status"] == "success"
    assert body["verified"] is True
    assert target.is_dir()

    activity = client.get("/api/activity", params={"limit": 5}).json()
    assert activity["entries"][0]["tool"] == "create_folder"
    assert activity["entries"][0]["status"] == "success"
    assert activity["entries"][0]["risk_level"] == "medium"


# ----------------------------------------------------------------------
# archivos
# ----------------------------------------------------------------------
def test_files_search_endpoint(client: TestClient, workspace: Path) -> None:
    (workspace / "informe-anual.txt").write_text("x", encoding="utf-8")
    body = client.get("/api/files/search", params={"q": "informe", "path": str(workspace)}).json()
    assert body["total"] == 1
    assert body["results"][0]["name"] == "informe-anual.txt"


def test_files_list_endpoint(client: TestClient, workspace: Path) -> None:
    (workspace / "sub").mkdir()
    body = client.get("/api/files/list", params={"path": str(workspace)}).json()
    assert body["total"] == 1
    assert body["entries"][0]["type"] == "directory"


def test_files_endpoints_reject_paths_outside_allowed_roots(client: TestClient) -> None:
    response = client.get("/api/files/list", params={"path": "C:\\Windows\\System32"})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] in {
        "system_path_denied",
        "path_outside_allowed_roots",
    }


def test_known_folders_are_exposed(client: TestClient) -> None:
    folders = client.get("/api/files/known-folders").json()["folders"]
    assert {"home", "desktop", "documents", "downloads"} <= set(folders)
    assert all(value for value in folders.values())


# ----------------------------------------------------------------------
# actividad
# ----------------------------------------------------------------------
def test_activity_is_empty_at_the_start_and_grows(client: TestClient) -> None:
    assert client.get("/api/activity").json()["total"] == 0
    client.post("/api/chat", json={"message": "dame información del sistema"})
    body = client.get("/api/activity").json()
    assert body["total"] >= 1
    assert body["entries"][0]["tool"] == "get_system_info"


def test_activity_never_stores_sensitive_arguments(client: TestClient) -> None:
    client.post(
        "/api/actions/execute",
        json={"tool": "web_search", "arguments": {"query": "x", "api_key": "secreto"}},
    )
    entries = client.get("/api/activity").json()["entries"]
    serialized = str(entries)
    assert "secreto" not in serialized


def test_activity_stats(client: TestClient) -> None:
    client.post("/api/chat", json={"message": "dame información del sistema"})
    body = client.get("/api/activity/stats").json()
    assert body["total"] >= 1
    assert "success" in body["by_status"]


# ----------------------------------------------------------------------
# websocket
# ----------------------------------------------------------------------
def test_websocket_sends_the_initial_state(client: TestClient) -> None:
    with client.websocket_connect("/ws/events") as websocket:
        first = websocket.receive_json()
        assert first["type"] == "assistant.status"
        assert first["data"]["status"] == "idle"

        second = websocket.receive_json()
        assert second["type"] == "system.status"
        assert "memory_percent" in second["data"]


def test_websocket_streams_action_events(client: TestClient) -> None:
    with client.websocket_connect("/ws/events") as websocket:
        websocket.receive_json()  # assistant.status inicial
        websocket.receive_json()  # system.status inicial

        client.post("/api/chat", json={"message": "dame información del sistema"})

        types: list[str] = []
        for _ in range(8):
            message = websocket.receive_json()
            types.append(message["type"])
            if message["type"] == "action.completed":
                break
        assert "action.planning" in types
        assert "action.started" in types
        assert "action.completed" in types
