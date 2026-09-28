"""Tests de la escucha por voz.

No se abre el micrófono: se comprueba la lógica de la palabra clave, el despacho
de órdenes y las protecciones (eco de los altavoces, coincidencias dudosas).
El reconocedor se valida con audio sintetizado por JARKKO, no con una persona.
"""

from __future__ import annotations

import asyncio
import io
import wave
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.voice.base import SpeechPlan
from app.voice.listener import ListenerService
from app.voice.microphone import Microphone, _downsample
from app.voice.recognizer import SpeechRecognizer, wake_word_match
from app.voice.service import VoiceService
from tests.conftest import run


# ----------------------------------------------------------------------
# palabra clave
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("heard", "expected_command"),
    [
        ("jarkko abre youtube", "abre youtube"),
        ("arco abre youtube", "abre youtube"),          # cómo lo oye el modelo de verdad
        ("zarco crear una carpeta", "crear una carpeta"),
        ("oye jarco abre chrome", "abre chrome"),        # relleno inicial
        ("JARKKO Abre Chrome", "abre chrome"),
    ],
)
def test_wake_word_variants_are_recognized(heard: str, expected_command: str) -> None:
    match = wake_word_match(heard)
    assert match.matched
    assert match.command == expected_command


def test_without_the_wake_word_nothing_matches() -> None:
    match = wake_word_match("abre youtube")
    assert not match.matched
    assert match.command == "abre youtube"


def test_exact_and_fuzzy_matches_are_distinguished() -> None:
    assert wake_word_match("jarkko hola").exact is True
    assert wake_word_match("zarco hola").exact is True
    # «marco» es una palabra normal: coincide, pero no de forma inequívoca.
    fuzzy = wake_word_match("marco polo")
    assert fuzzy.matched is True
    assert fuzzy.exact is False


def test_empty_input() -> None:
    assert wake_word_match("").matched is False


# ----------------------------------------------------------------------
# despacho de órdenes
# ----------------------------------------------------------------------
class _Recorder:
    """Sustituto del motor: registra las órdenes en lugar de ejecutarlas."""

    def __init__(self) -> None:
        self.orders: list[str] = []

    async def __call__(self, order: str) -> None:
        self.orders.append(order)


def _listener_with(dispatch: _Recorder, voice: VoiceService) -> ListenerService:
    listener = ListenerService(voice=voice)
    listener._dispatch = dispatch  # noqa: SLF001 - se evita abrir el micrófono
    listener._loop = asyncio.new_event_loop()  # noqa: SLF001
    return listener


def _drain(listener: ListenerService) -> None:
    """Deja que el bucle procese lo que el oyente despachó desde su hilo."""

    loop = listener._loop  # noqa: SLF001
    assert loop is not None
    loop.run_until_complete(asyncio.sleep(0.05))
    loop.close()


def test_command_with_wake_word_is_dispatched() -> None:
    recorder = _Recorder()
    listener = _listener_with(recorder, VoiceService())

    listener._on_utterance("arco abre la carpeta descargas")  # noqa: SLF001
    _drain(listener)

    assert recorder.orders == ["abre la carpeta descargas"]
    assert listener.status()["stats"]["commands"] == 1


def test_speech_without_wake_word_is_ignored() -> None:
    recorder = _Recorder()
    listener = _listener_with(recorder, VoiceService())

    listener._on_utterance("abre la carpeta descargas")  # noqa: SLF001

    assert recorder.orders == []
    status = listener.status()
    assert status["stats"]["ignored"] == 1
    assert status["recent"][0]["reason"] == "no_wake_word"


def test_hands_free_mode_dispatches_plain_speech(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con la palabra clave desactivada, hablar normal ya es una orden."""

    from app.config import get_settings

    monkeypatch.setenv("JARVIS_WAKE_WORD_REQUIRED", "false")
    get_settings.cache_clear()

    recorder = _Recorder()
    listener = _listener_with(recorder, VoiceService())

    listener._on_utterance("abre la carpeta descargas")  # noqa: SLF001
    _drain(listener)

    assert recorder.orders == ["abre la carpeta descargas"]
    assert listener.status()["stats"]["commands"] == 1
    get_settings.cache_clear()


def test_fuzzy_wake_word_without_a_clear_order_stays_quiet() -> None:
    """«marco polo» no debe provocar un «no te entendí» en voz alta."""

    recorder = _Recorder()
    listener = _listener_with(recorder, VoiceService())

    listener._on_utterance("marco polo")  # noqa: SLF001

    assert recorder.orders == []
    assert listener.status()["recent"][0]["reason"] == "fuzzy_wake_word_without_clear_order"


def test_fuzzy_wake_word_with_a_clear_order_is_obeyed() -> None:
    recorder = _Recorder()
    listener = _listener_with(recorder, VoiceService())

    listener._on_utterance("marco abre youtube")  # noqa: SLF001
    _drain(listener)

    assert recorder.orders == ["abre youtube"]


def test_the_voice_command_path_is_the_same_as_the_written_one() -> None:
    """Hablar no da privilegios: la orden pasa por el motor completo."""

    from app.agent.engine import AgentEngine

    engine = AgentEngine()
    recorder = _Recorder()
    listener = _listener_with(recorder, engine.voice)
    listener._on_utterance("arco abre powershell")  # noqa: SLF001
    _drain(listener)

    # El oyente solo transcribe y despacha; la decisión de pedir confirmación es
    # del Permission Manager, igual que por texto.
    assert recorder.orders == ["abre powershell"]
    outcome = run(engine.chat("abre powershell"))
    assert outcome.requires_confirmation is True
    assert outcome.actions[0].status.value == "awaiting_confirmation"


# ----------------------------------------------------------------------
# protección contra el eco de los altavoces
# ----------------------------------------------------------------------
class _SilentPlayer:
    """Reproductor de mentira: tarda lo mismo pero no suena (tests silenciosos)."""

    def __init__(self) -> None:
        self.played = 0

    def play(self, data: bytes, media_type: str, *, path: str | None = None) -> bool:
        import time

        self.played += 1
        time.sleep(0.2)
        return True


def test_voice_service_reports_when_it_is_speaking() -> None:
    """La bandera que evita que JARKKO se oiga a sí mismo por los altavoces."""

    player = _SilentPlayer()
    voice = VoiceService(player=player)  # type: ignore[arg-type]
    assert voice.speaking is False

    async def speak_and_watch() -> bool:
        task = asyncio.create_task(
            voice.say(SpeechPlan(text="Una prueba.", phrase_key=None), play=True)
        )
        seen_speaking = False
        for _ in range(60):  # hasta ~3 s: la síntesis tarda unos ms
            await asyncio.sleep(0.05)
            if voice.speaking:
                seen_speaking = True
                break
        await task
        return seen_speaking

    assert run(speak_and_watch()) is True
    assert player.played == 1
    assert voice.speaking is False  # y se apaga al terminar


# ----------------------------------------------------------------------
# reconocedor y micrófono
# ----------------------------------------------------------------------
def test_recognizer_transcribes_jarkkos_own_voice() -> None:
    """Prueba de extremo a extremo del reconocedor sin necesidad de una persona."""

    recognizer = SpeechRecognizer()
    if not recognizer.describe()["available"]:
        pytest.skip("modelo de reconocimiento no instalado")

    voice = VoiceService()
    audio = run(voice.synthesize(SpeechPlan(text="abre la carpeta descargas", phrase_key=None)))
    assert audio is not None

    with wave.open(io.BytesIO(audio.data)) as reader:
        assert reader.getframerate() == recognizer.sample_rate
        pcm = reader.readframes(reader.getnframes())

    text = recognizer.transcribe(pcm)
    assert "carpeta" in text and "descargas" in text


def test_downsampling_halves_the_samples() -> None:
    pcm = b"".join(int(value).to_bytes(2, "little", signed=True) for value in range(100))
    assert len(_downsample(pcm, 32000, 16000)) == pytest.approx(len(pcm) / 2, abs=4)
    assert _downsample(pcm, 16000, 16000) == pcm


def test_microphone_describes_the_available_inputs() -> None:
    info = Microphone().describe()
    assert "available" in info
    if info["available"]:
        assert info["target_rate"] == 16000
        assert info["inputs"]


# ----------------------------------------------------------------------
# API
# ----------------------------------------------------------------------
def test_listen_status_endpoint(client: TestClient) -> None:
    body = client.get("/api/voice/listen/status").json()
    assert body["enabled"] is True
    assert body["running"] is False  # no arranca en tests
    assert body["wake_word"] == "jarkko"
    assert body["wake_word_required"] is True
    assert body["recognizer"]["engine"] == "vosk"


def test_listening_does_not_start_by_itself_in_tests(client: TestClient) -> None:
    assert client.get("/api/voice/listen/status").json()["running"] is False


def test_stopping_when_not_listening_is_harmless(client: TestClient) -> None:
    body = client.post("/api/voice/listen/stop").json()
    assert body["running"] is False
    assert body["stopped"] is True


def test_health_and_status_expose_the_listening_state(client: TestClient) -> None:
    status = client.get("/api/voice/listen/status").json()
    assert set(status) >= {"enabled", "running", "available", "recognizer", "microphone", "stats"}


def test_listen_once_requires_no_wake_word_when_not_executing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No se abre el micrófono de verdad: se sustituye la grabación."""

    from app.voice import listener as listener_module

    def fake_record(self: ListenerService, seconds: float) -> str:
        return "arco cuanta memoria estoy usando"

    monkeypatch.setattr(listener_module.ListenerService, "_record_and_transcribe", fake_record)

    body = client.post("/api/voice/listen", json={"seconds": 2}).json()
    assert body["heard"] is True
    assert body["wake_word"] is True
    assert body["command"] == "cuanta memoria estoy usando"
    assert body["executed"] is False


def test_listen_once_can_execute_the_order(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.voice import listener as listener_module

    def fake_record(self: ListenerService, seconds: float) -> str:
        return "jarkko cuanta memoria estoy usando"

    monkeypatch.setattr(listener_module.ListenerService, "_record_and_transcribe", fake_record)

    body = client.post("/api/voice/listen", json={"execute": True}).json()
    assert body["executed"] is True
    assert body["chat"]["actions"][0]["tool"] == "get_memory_usage"
    assert body["chat"]["actions"][0]["status"] == "success"


def test_listen_once_refuses_to_execute_without_the_wake_word(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.voice import listener as listener_module

    def fake_record(self: ListenerService, seconds: float) -> str:
        return "cuanta memoria estoy usando"

    monkeypatch.setattr(listener_module.ListenerService, "_record_and_transcribe", fake_record)

    body = client.post("/api/voice/listen", json={"execute": True}).json()
    assert body["executed"] is False
    assert body["reason"] == "no_wake_word"


def test_websocket_reports_what_it_heard(client: TestClient) -> None:
    from app.voice.listener import get_listener

    with client.websocket_connect("/ws/events") as websocket:
        websocket.receive_json()  # assistant.status
        websocket.receive_json()  # system.status

        listener = get_listener()
        listener._on_utterance("hablando de otra cosa")  # noqa: SLF001

        heard = websocket.receive_json()
        assert heard["type"] == "speech.heard"
        assert heard["data"]["wake_word"] is False
        assert heard["data"]["acted"] is False


def test_microphone_level_test_endpoint(client: TestClient) -> None:
    """El diagnóstico distingue «no hay código» de «micrófono silenciado»."""

    body = client.get("/api/voice/microphone/test", params={"seconds": 0.5}).json()
    assert "level" in body and "ok" in body
    assert isinstance(body["level"], (int, float))
    if not body["ok"]:
        # En este equipo el micrófono entrega silencio: el mensaje debe explicarlo.
        assert "silenci" in body.get("diagnosis", "") or body.get("reason")


# ----------------------------------------------------------------------
# recuperación automática del micrófono
# ----------------------------------------------------------------------
def test_digital_silence_is_distinguished_from_a_quiet_room() -> None:
    """La diferencia entre un micro mudo y una habitación callada."""

    import array as _array

    from app.voice.listener import _is_digital_silence

    mudo = _array.array("h", [0] * 4000).tobytes()
    ruido_de_sala = _array.array("h", [(i % 11) * 40 - 200 for i in range(4000)]).tobytes()
    voz = _array.array("h", [(i % 97) * 300 - 14000 for i in range(4000)]).tobytes()

    assert _is_digital_silence(mudo) is True
    assert _is_digital_silence(b"") is True
    assert _is_digital_silence(ruido_de_sala) is False
    assert _is_digital_silence(voz) is False


def test_the_listener_reopens_the_microphone_after_prolonged_silence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si el micro entrega silencio digital, se reabre en vez de quedarse sordo.

    Pasa de verdad cuando el micrófono estaba silenciado al abrir el flujo o
    cuando Windows cambia de dispositivo (unos auriculares Bluetooth).
    """

    import array as _array
    from contextlib import contextmanager

    from app.config import get_settings

    monkeypatch.setenv("JARVIS_STT_SILENCE_WATCHDOG_SECONDS", "0.5")
    get_settings.cache_clear()

    aperturas = {"n": 0}
    mudo = _array.array("h", [0] * 4000).tobytes()

    class _MicroMudo:
        def refresh(self) -> None:
            aperturas["refrescos"] = aperturas.get("refrescos", 0) + 1

        @contextmanager
        def stream(self):
            aperturas["n"] += 1
            if aperturas["n"] >= 3:
                raise MicrophoneUnavailable("fin de la prueba")

            class _Lector:
                def read(self, frames: int | None = None) -> bytes:
                    return mudo

            yield _Lector()

        def describe(self) -> dict[str, object]:
            return {"available": True}

    listener = ListenerService(microphone=_MicroMudo(), voice=VoiceService())
    listener._run()  # noqa: SLF001 - se ejecuta el cuerpo del hilo directamente

    # Reabrió en lugar de rendirse en la primera sesión muda.
    assert aperturas["n"] >= 2
    assert aperturas.get("refrescos", 0) >= 1
    assert listener.status()["stats"]["reopens"] >= 1
