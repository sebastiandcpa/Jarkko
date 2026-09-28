"""Escucha manos libres: «Jarkko, abre YouTube».

Un hilo dedicado lee el micrófono y alimenta al reconocedor.  Cuando una frase
termina y empieza por la palabra clave, el resto se despacha al agente **por el
mismo camino que el texto escrito** (`/api/chat`): intención → plan → Validator →
Permission Manager → ejecución.  Hablar no da ningún privilegio extra: una orden
de riesgo alto sigue pidiendo confirmación.

Dos cuidados importantes:

* mientras JARKKO habla, el audio se descarta (si no, se oiría a sí mismo por los
  altavoces y se respondería solo);
* la voz nunca se guarda en disco ni se envía a ningún servidor: se transcribe en
  memoria, en local.
"""

from __future__ import annotations

import array
import asyncio
import logging
import math
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.config import Settings, get_settings
from app.services.events import AssistantStatus, EventBus, EventType, event_bus
from app.voice.microphone import Microphone, MicrophoneUnavailable
from app.agent.intent_parser import RuleBasedIntentParser
from app.voice.recognizer import (
    RecognizerUnavailable,
    SpeechRecognizer,
    wake_word_match,
)
from app.voice.service import VoiceService, get_voice_service

logger = logging.getLogger(__name__)

#: Despachador de una orden ya transcrita (normalmente ``engine.chat``).
Dispatch = Callable[[str], Awaitable[Any]]

#: Por debajo de esto el bloque es silencio digital, no una habitación callada:
#: un micrófono vivo siempre trae algo de ruido de fondo.
_SILENCE_RMS = 3.0


def _is_digital_silence(pcm: bytes) -> bool:
    """``True`` si el bloque no trae señal alguna (micro mudo o desconectado)."""

    samples = array.array("h")
    samples.frombytes(pcm)
    if not samples:
        return True
    total = 0
    # Muestreo cada 8: basta para distinguir silencio absoluto de ruido de sala.
    subset = samples[::8] or samples
    for value in subset:
        total += value * value
    return math.sqrt(total / len(subset)) < _SILENCE_RMS


class ListenerService:
    """Bucle de escucha continua con palabra clave."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        recognizer: SpeechRecognizer | None = None,
        microphone: Microphone | None = None,
        voice: VoiceService | None = None,
        events: EventBus | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self.recognizer = recognizer or SpeechRecognizer(self._settings)
        self.microphone = microphone or Microphone(self._settings)
        self._voice = voice or get_voice_service()
        self._events = events or event_bus

        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._dispatch: Dispatch | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._error: str | None = None
        self._heard: list[dict[str, Any]] = []
        self._stats = {"utterances": 0, "commands": 0, "ignored": 0, "reopens": 0}
        self._last_silence_seconds = 0.0
        # Pre-lectura local (sin red) para decidir si merece la pena contestar.
        self._preview = RuleBasedIntentParser()

    # ------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def available(self) -> bool:
        return (
            self._settings.stt_enabled
            and self.recognizer.describe()["available"]
            and self.microphone.describe()["available"]
        )

    # ------------------------------------------------------------------
    def start(self, dispatch: Dispatch) -> dict[str, Any]:
        """Arranca la escucha.  Idempotente."""

        if not self._settings.stt_enabled:
            return {"started": False, "reason": "stt_disabled"}
        if self.running:
            return {"started": True, "already_running": True}

        try:
            self.recognizer.load()
        except RecognizerUnavailable as exc:
            self._error = str(exc)
            return {"started": False, "reason": "recognizer_unavailable", "message": str(exc)}

        microphone = self.microphone.describe()
        if not microphone["available"]:
            self._error = microphone.get("error") or "sin micrófono"
            return {"started": False, "reason": "microphone_unavailable", "message": self._error}

        self._dispatch = dispatch
        self._loop = asyncio.get_running_loop()
        self._stop.clear()
        self._error = None
        self._thread = threading.Thread(target=self._run, name="jarkko-listener", daemon=True)
        self._thread.start()

        self._events.publish_status(AssistantStatus.LISTENING, assistant="jarkko")
        logger.info("Escucha activada (palabra clave: %s)", self._settings.wake_word)
        return {"started": True, "wake_word": self._settings.wake_word}

    def stop(self) -> dict[str, Any]:
        if not self.running:
            return {"stopped": True, "already_stopped": True}
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=5)
        self._events.publish_status(AssistantStatus.IDLE, assistant="jarkko")
        logger.info("Escucha detenida")
        return {"stopped": True}

    # ------------------------------------------------------------------
    def _run(self) -> None:
        """Hilo de escucha: mantiene el micrófono abierto y se recupera solo.

        El micrófono se reabre cuando lleva demasiado tiempo entregando silencio
        digital.  Pasa de verdad: si el micro estaba silenciado al abrir el flujo,
        o si Windows cambia de dispositivo predeterminado (unos auriculares
        Bluetooth que se conectan), el flujo antiguo se queda mudo para siempre y
        JARKKO parecería sordo sin dar ningún error.
        """

        while not self._stop.is_set():
            try:
                self._listen_session()
            except (MicrophoneUnavailable, RecognizerUnavailable) as exc:
                self._error = str(exc)
                logger.warning("Escucha detenida: %s", exc)
                break
            except Exception as exc:  # noqa: BLE001 - el hilo no debe morir en silencio
                self._error = str(exc)
                logger.exception("Fallo en el bucle de escucha")
                break

            if self._stop.is_set():
                break
            # Se reabre con la lista de dispositivos recién consultada.
            logger.info("Reabriendo el micrófono (silencio prolongado)")
            self._stats["reopens"] += 1
            self.microphone.refresh()
            time.sleep(1.0)

        self._stop.set()

    def _listen_session(self) -> None:
        """Una sesión con el micrófono abierto.  Vuelve si el audio se queda mudo."""

        silence_limit = self._settings.stt_silence_watchdog_seconds
        block_seconds = self._settings.stt_block_ms / 1000
        recognizer = self.recognizer.create_stream()

        with self.microphone.stream() as microphone:
            last_partial = ""
            silent_for = 0.0
            while not self._stop.is_set():
                chunk = microphone.read()

                if self._voice.speaking:
                    # JARKKO está hablando: se tira el audio y se reinicia el
                    # reconocedor para no arrastrar su propia voz.
                    recognizer.Reset()
                    last_partial = ""
                    silent_for = 0.0
                    continue

                if _is_digital_silence(chunk):
                    silent_for += block_seconds
                    if silence_limit and silent_for >= silence_limit:
                        self._last_silence_seconds = silent_for
                        return
                else:
                    silent_for = 0.0

                if recognizer.AcceptWaveform(chunk):
                    text = self.recognizer.result_text(recognizer.Result())
                    last_partial = ""
                    if text:
                        self._on_utterance(text)
                    continue

                partial = self.recognizer.partial_text(recognizer.PartialResult())
                if partial and partial != last_partial:
                    last_partial = partial
                    self._events.publish(EventType.SPEECH_PARTIAL, {"text": partial})

    # ------------------------------------------------------------------
    def _on_utterance(self, text: str) -> None:
        wake = wake_word_match(text, self._settings.wake_word)
        self._stats["utterances"] += 1

        entry: dict[str, Any] = {
            "text": text,
            "wake_word": wake.matched,
            "command": wake.command,
            "at": time.strftime("%H:%M:%S"),
        }

        if self._settings.wake_word_required and not wake.matched:
            self._stats["ignored"] += 1
            self._remember(entry | {"acted": False, "reason": "no_wake_word"})
            return

        order = wake.command if wake.matched else text
        if not order:
            # «Jarkko» a secas: saluda, no se inventa una orden.
            self._remember(entry | {"acted": True, "reason": "presence"})
            self._speak_presence()
            return

        # Coincidencia aproximada («marco polo» → «marco»): se calla solo si además
        # lo que sigue es una palabra suelta. Si alguien le habló con una frase
        # entera, JARKKO contesta aunque no la entienda: quedarse mudo después de
        # reconocer tu llamada es el peor resultado posible, mucho peor que un
        # «no te entendí» de más.
        if not wake.exact and len(order.split()) < 2:
            preview = self._preview.parse(order)
            if not preview.actions and preview.matched_rule != "smalltalk":
                self._stats["ignored"] += 1
                self._remember(
                    entry | {"acted": False, "reason": "fuzzy_wake_word_without_clear_order"}
                )
                logger.debug("Ignorado (palabra clave dudosa): %s", text)
                return

        self._stats["commands"] += 1
        self._remember(entry | {"acted": True, "reason": "command"})
        logger.info("Orden por voz: %s", order)
        self._submit(order)

    def _remember(self, entry: dict[str, Any]) -> None:
        self._heard.append(entry)
        del self._heard[:-20]
        self._events.publish(EventType.SPEECH_HEARD, entry)

    def _submit(self, order: str) -> None:
        if self._dispatch is None or self._loop is None:  # pragma: no cover
            return
        try:
            asyncio.run_coroutine_threadsafe(self._dispatch(order), self._loop)
        except RuntimeError:  # pragma: no cover - bucle cerrándose
            logger.debug("No se pudo despachar la orden: el bucle ya no está activo")

    def _speak_presence(self) -> None:
        if self._loop is None:  # pragma: no cover
            return
        presence = self._voice.phrase_plan("presence")
        if presence is None:
            return
        asyncio.run_coroutine_threadsafe(self._voice.say(presence), self._loop)

    # ------------------------------------------------------------------
    async def listen_once(self, seconds: float | None = None) -> dict[str, Any]:
        """Graba una sola vez y devuelve lo que entendió (sin ejecutar nada)."""

        from starlette.concurrency import run_in_threadpool

        limit = seconds or self._settings.stt_listen_seconds
        try:
            self.recognizer.load()
        except RecognizerUnavailable as exc:
            return {"heard": False, "reason": "recognizer_unavailable", "message": str(exc)}

        self._events.publish_status(AssistantStatus.LISTENING, assistant="jarkko")
        try:
            text = await run_in_threadpool(self._record_and_transcribe, limit)
        except MicrophoneUnavailable as exc:
            return {"heard": False, "reason": "microphone_unavailable", "message": str(exc)}
        finally:
            self._events.publish_status(AssistantStatus.IDLE, assistant="jarkko")

        wake = wake_word_match(text, self._settings.wake_word)
        return {
            "heard": bool(text),
            "text": text,
            "wake_word": wake.matched,
            "command": wake.command or text,
            "seconds": limit,
        }

    def _record_and_transcribe(self, seconds: float) -> str:
        """Graba hasta que hay silencio o se agota el tiempo, y transcribe."""

        recognizer = self.recognizer.create_stream()
        silence_needed = self._settings.stt_silence_seconds
        block_seconds = self._settings.stt_block_ms / 1000
        deadline = time.monotonic() + seconds
        silence = 0.0
        heard_something = False
        pieces: list[str] = []

        with self.microphone.stream() as microphone:
            while time.monotonic() < deadline:
                chunk = microphone.read()
                if recognizer.AcceptWaveform(chunk):
                    piece = self.recognizer.result_text(recognizer.Result())
                    if piece:
                        pieces.append(piece)
                        heard_something = True
                partial = self.recognizer.partial_text(recognizer.PartialResult())
                if partial:
                    heard_something = True
                    silence = 0.0
                    self._events.publish(EventType.SPEECH_PARTIAL, {"text": partial})
                elif heard_something:
                    silence += block_seconds
                    if silence >= silence_needed:
                        break

        final = self.recognizer.result_text(recognizer.FinalResult())
        if final:
            pieces.append(final)
        return " ".join(piece for piece in pieces if piece).strip()

    # ------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        return {
            "enabled": self._settings.stt_enabled,
            "running": self.running,
            "available": self.available,
            "wake_word": self._settings.wake_word,
            "wake_word_required": self._settings.wake_word_required,
            "recognizer": self.recognizer.describe(),
            "microphone": self.microphone.describe(),
            "stats": dict(self._stats),
            "recent": list(reversed(self._heard[-10:])),
            "error": self._error,
        }


_listener: ListenerService | None = None


def get_listener() -> ListenerService:
    global _listener
    if _listener is None:
        _listener = ListenerService()
    return _listener


def reset_listener() -> None:
    """Detiene y descarta el oyente.  Uso en tests y al recargar configuración."""

    global _listener
    if _listener is not None and _listener.running:
        _listener.stop()
    _listener = None
