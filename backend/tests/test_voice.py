"""Tests de la voz de JARKKO.

Los tests sintetizan de verdad con la voz local de Windows, pero con la
reproducción desactivada: no suena nada y no se gasta ninguna cuota.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agent.executor import ActionOutcome, ActionStatus
from app.config import get_settings
from app.services.assistants import JARKKO, resolve_assistant
from app.voice.base import CacheMiss, SpeechPlan, TTSUnavailable
from app.voice.elevenlabs import ElevenLabsTTS
from app.voice.phrases import PHRASES, phrase_for_action, total_characters
from app.voice.service import VoiceService
from app.voice.windows_tts import WindowsTTS
from tests.conftest import run


@pytest.fixture
def voice() -> VoiceService:
    return VoiceService()


# ----------------------------------------------------------------------
# identidad
# ----------------------------------------------------------------------
def test_jarkko_is_the_only_identity() -> None:
    assert resolve_assistant("jarvis") is JARKKO
    assert resolve_assistant("ekko") is JARKKO
    assert resolve_assistant("JARKKO") is JARKKO
    assert resolve_assistant("cualquier cosa") is JARKKO
    assert JARKKO.voice_id == "WEXRePkZGpmcFLvCOaB1"


# ----------------------------------------------------------------------
# catálogo de frases
# ----------------------------------------------------------------------
def test_phrase_catalog_has_no_placeholders() -> None:
    """Las frases cacheadas no pueden llevar variables: por eso son reutilizables."""

    for key, text in PHRASES.items():
        assert text.strip(), key
        assert "{" not in text and "%s" not in text, key


def test_catalog_fits_comfortably_in_the_free_monthly_quota() -> None:
    # El plan gratuito de ElevenLabs son ~10.000 créditos al mes y el caché se
    # genera una sola vez: si esto crece demasiado, hay que enterarse.
    assert total_characters() < 4000


def test_phrase_for_action_maps_tools_and_statuses() -> None:
    assert phrase_for_action("open_url", ActionStatus.SUCCESS) == "ack.url"
    assert phrase_for_action("create_folder", ActionStatus.SUCCESS) == "ack.folder_created"
    assert phrase_for_action("move_file", ActionStatus.CONFLICT) == "error.conflict"
    assert phrase_for_action("open_file", ActionStatus.DENIED) == "error.denied"
    assert phrase_for_action("search_files", ActionStatus.SUCCESS, found_results=True) == "ack.found"
    assert phrase_for_action("search_files", ActionStatus.SUCCESS, found_results=False) == "ack.not_found"
    # Las herramientas informativas se leen con texto dinámico.
    assert phrase_for_action("get_memory_usage", ActionStatus.SUCCESS) is None


# ----------------------------------------------------------------------
# qué se dice en voz alta
# ----------------------------------------------------------------------
def _outcome(tool: str, status: ActionStatus = ActionStatus.SUCCESS, **data: object) -> ActionOutcome:
    return ActionOutcome(tool=tool, status=status, message=f"mensaje de {tool}", data=dict(data))


def test_confirmation_uses_the_fixed_phrase(voice: VoiceService) -> None:
    plan = voice.plan_for_chat(chat_status="awaiting_confirmation", reply="lo que sea")
    assert plan is not None
    assert plan.phrase_key == "confirm.required"
    assert plan.cacheable


def test_action_success_uses_a_short_fixed_line_not_the_full_path(voice: VoiceService) -> None:
    outcome = _outcome("create_folder")
    plan = voice.plan_for_chat(
        chat_status="success",
        reply="Hecho. Creé la carpeta C:\\Users\\Usuario\\Documents\\Una Ruta Larguísima",
        actions=[outcome],
    )
    assert plan is not None
    assert plan.phrase_key == "ack.folder_created"
    assert "C:\\" not in plan.text  # la ruta se ve en pantalla, no se dicta


def test_informational_tools_speak_the_actual_data(voice: VoiceService) -> None:
    plan = voice.plan_for_chat(
        chat_status="success",
        reply="Hecho. RAM al 42% (6.6 GB de 15.7 GB en uso).",
        actions=[_outcome("get_memory_usage")],
    )
    assert plan is not None
    assert plan.phrase_key is None
    assert "42%" in plan.text


def test_clarification_and_smalltalk(voice: VoiceService) -> None:
    unclear = voice.plan_for_chat(chat_status="no_action", reply="…", needs_clarification=True)
    assert unclear is not None and unclear.phrase_key == "no_understand"

    hello = voice.plan_for_chat(chat_status="no_action", reply="…", intent_rule="smalltalk")
    assert hello is not None and hello.phrase_key == "capabilities"


def test_a_concrete_explanation_is_spoken_as_is(voice: VoiceService) -> None:
    """Si el motor sabe POR QUE fallo, se dice eso y no la frase generica."""

    plan = voice.plan_for_chat(
        chat_status="no_action",
        reply="No encuentro la carpeta «Facturas».",
        needs_clarification=True,
        intent_rule="unresolved:folder",
    )
    assert plan is not None
    assert plan.phrase_key is None
    assert "Facturas" in plan.text


def test_several_actions_collapse_into_one_line(voice: VoiceService) -> None:
    plan = voice.plan_for_chat(
        chat_status="success",
        reply="dos cosas",
        actions=[_outcome("open_url"), _outcome("open_url")],
    )
    assert plan is not None and plan.phrase_key == "ack.generic"

    failed = voice.plan_for_chat(
        chat_status="error",
        reply="algo falló",
        actions=[_outcome("open_url"), _outcome("open_url", ActionStatus.ERROR)],
    )
    assert failed is not None and failed.phrase_key == "error.generic"


# ----------------------------------------------------------------------
# motores
# ----------------------------------------------------------------------
def test_windows_voice_is_available_and_speaks_spanish() -> None:
    info = WindowsTTS().describe()
    assert info["available"] is True, info
    assert info["voice"]


def test_windows_engine_produces_real_wav_audio(voice: VoiceService) -> None:
    audio = run(voice.synthesize(SpeechPlan(text="Prueba de voz.", phrase_key=None)))
    assert audio is not None
    assert audio.engine == "windows"
    assert audio.media_type == "audio/wav"
    assert audio.data.startswith(b"RIFF")
    assert len(audio.data) > 1000


def test_fixed_phrases_are_cached_after_the_first_synthesis(voice: VoiceService) -> None:
    plan = SpeechPlan(text=PHRASES["ack.generic"], phrase_key="ack.generic")
    first = run(voice.synthesize(plan))
    assert first is not None and first.cached is True  # se guarda al generarse
    assert voice.cache.stats()["entries"] == 1

    second = run(voice.synthesize(plan))
    assert second is not None and second.cached is True
    assert voice.cache.stats()["entries"] == 1  # no se duplica


def test_engine_chain_without_api_key_is_only_windows(voice: VoiceService) -> None:
    assert [engine.name for engine in voice.engines] == ["windows"]


def test_elevenlabs_never_spends_credits_without_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    """La protección de cuota: sin caché y sin permiso explícito, no hay red."""

    monkeypatch.setenv("JARVIS_ELEVENLABS_API_KEY", "clave-de-prueba-no-real")
    monkeypatch.setenv("JARVIS_ELEVENLABS_ALLOW_LIVE", "false")
    get_settings.cache_clear()

    engine = ElevenLabsTTS()
    assert engine.configured

    def _boom(*args: object, **kwargs: object) -> None:  # pragma: no cover
        raise AssertionError("¡No debería haber llamado a la API!")

    monkeypatch.setattr("app.voice.elevenlabs.httpx.AsyncClient", _boom)
    with pytest.raises(CacheMiss):
        run(engine.synthesize(SpeechPlan(text="hola", phrase_key="greeting")))


def test_elevenlabs_without_key_is_unavailable() -> None:
    engine = ElevenLabsTTS()
    assert engine.configured is False
    with pytest.raises(TTSUnavailable):
        run(engine.synthesize(SpeechPlan(text="hola", phrase_key="greeting")))


def test_cache_build_reports_missing_key(voice: VoiceService) -> None:
    report = run(voice.build_phrase_cache())
    assert report["ok"] is False
    assert report["reason"] == "elevenlabs_not_configured"


# ----------------------------------------------------------------------
# API
# ----------------------------------------------------------------------
def test_voice_status_endpoint(client: TestClient) -> None:
    body = client.get("/api/voice/status").json()
    assert body["enabled"] is True
    assert body["playback"] is False  # en tests
    assert [item["name"] for item in body["engines"]] == ["windows"]
    assert body["cache"]["catalog_phrases"] == len(PHRASES)
    assert body["identity_voice"]["configured"] is False


def test_phrases_endpoint(client: TestClient) -> None:
    body = client.get("/api/voice/phrases").json()
    assert body["total"] == len(PHRASES)
    assert any(item["key"] == "greeting" for item in body["phrases"])


def test_speak_endpoint_with_a_fixed_phrase_and_download(client: TestClient) -> None:
    body = client.post("/api/voice/speak", json={"phrase_key": "greeting", "play": False}).json()
    assert body["spoken"] is True
    assert body["engine"] == "windows"
    assert body["phrase_key"] == "greeting"
    assert body["bytes"] > 1000
    assert body["audio_url"]

    audio = client.get(body["audio_url"])
    assert audio.status_code == 200
    assert audio.headers["content-type"] == "audio/wav"
    assert audio.content.startswith(b"RIFF")


def test_speak_endpoint_with_free_text(client: TestClient) -> None:
    body = client.post("/api/voice/speak", json={"text": "Hola, una prueba.", "play": False}).json()
    assert body["spoken"] is True
    assert body["cached"] is False  # el texto libre no se cachea
    assert body["audio_url"] is None


def test_speak_endpoint_validates_input(client: TestClient) -> None:
    assert client.post("/api/voice/speak", json={"phrase_key": "no_existe"}).status_code == 404
    assert client.post("/api/voice/speak", json={}).status_code == 422


def test_audio_endpoint_rejects_bad_keys(client: TestClient) -> None:
    assert client.get("/api/voice/audio/..%2Fmanifest.json").status_code in {400, 404}
    assert client.get("/api/voice/audio/deadbeef").status_code == 404


def test_cache_build_endpoint_without_key(client: TestClient) -> None:
    body = client.post("/api/voice/cache/build").json()
    assert body["ok"] is False
    assert body["reason"] == "elevenlabs_not_configured"


def test_health_reports_the_voice(client: TestClient) -> None:
    voice = client.get("/api/health").json()["voice"]
    assert voice["enabled"] is True
    assert voice["engines"] == ["windows"]
    assert voice["identity_voice_configured"] is False


def test_websocket_announces_speech(client: TestClient) -> None:
    with client.websocket_connect("/ws/events") as websocket:
        websocket.receive_json()  # assistant.status inicial
        websocket.receive_json()  # system.status inicial

        client.post("/api/voice/speak", json={"phrase_key": "presence", "play": False})

        speaking = websocket.receive_json()
        assert speaking["type"] == "assistant.speaking"
        assert speaking["data"]["phrase_key"] == "presence"
        assert speaking["data"]["engine"] == "windows"

        spoken = websocket.receive_json()
        assert spoken["type"] == "assistant.spoken"
        assert spoken["data"]["played"] is False
