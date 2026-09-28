"""Reconocimiento de voz offline con Vosk.

Gratis, en CPU y sin enviar audio a ningún servidor: la voz del usuario no sale
del equipo.  Modelo: ``vosk-model-small-es-0.42`` (Apache 2.0, 39 MB).

El audio siempre es PCM 16 bits mono al ``sample_rate`` configurado (16 kHz), que
es justo lo que produce la voz de Windows y lo que espera el modelo.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from app.config import Settings, get_settings
from app.utils.text import fold

logger = logging.getLogger(__name__)

#: Cómo suele transcribir el modelo la palabra «Jarkko»: no está en su léxico,
#: así que cae en palabras españolas parecidas.  Verificado en pruebas reales.
WAKE_VARIANTS: frozenset[str] = frozenset(
    {
        "jarkko", "jarko", "jarco", "jarcos", "yarko", "yarco", "harko", "harco",
        "arco", "arcos", "zarco", "sarco", "charco", "barco", "marco", "carlos",
        "árco", "jaro", "jarro",
    }
)

#: Palabras de cortesía que pueden preceder a la palabra clave.
_LEADING_FILLERS: frozenset[str] = frozenset({"oye", "hey", "ok", "okay", "eh", "ey", "hola"})

_SIMILARITY_THRESHOLD = 0.62

#: Transcripciones que solo se explican si alguien llamó a JARKKO a propósito.
_UNAMBIGUOUS: frozenset[str] = frozenset(
    {"jarkko", "jarko", "jarco", "jarcos", "yarko", "yarco", "harko", "harco", "zarco", "sarco"}
)


class RecognizerUnavailable(RuntimeError):
    """No hay modelo de reconocimiento disponible."""


@dataclass(frozen=True, slots=True)
class WakeMatch:
    """Resultado de buscar la palabra clave al principio de una frase."""

    matched: bool
    command: str
    exact: bool = False
    """``True`` si la transcripción solo se explica llamando a JARKKO a propósito.

    Con una coincidencia aproximada («marco polo» → «marco») conviene exigir que la
    orden sea reconocible antes de contestar, para no meterse en una conversación
    ajena.
    """

    def __bool__(self) -> bool:
        return self.matched


def wake_word_match(text: str, wake_word: str = "jarkko") -> WakeMatch:
    """¿Empieza la frase por la palabra clave?

    Tolera las deformaciones del reconocedor («arco», «zarco»…) y un relleno
    inicial («oye Jarkko, abre YouTube»).
    """

    tokens = fold(text).split()
    if not tokens:
        return WakeMatch(False, "")

    index = 0
    if len(tokens) > 1 and tokens[0] in _LEADING_FILLERS:
        index = 1

    candidate = tokens[index] if index < len(tokens) else ""
    if not candidate:
        return WakeMatch(False, text.strip())

    target = fold(wake_word)
    exact = candidate == target or candidate in _UNAMBIGUOUS
    matched = (
        exact
        or candidate in WAKE_VARIANTS
        or SequenceMatcher(None, candidate, target).ratio() >= _SIMILARITY_THRESHOLD
    )
    if not matched:
        return WakeMatch(False, text.strip())
    return WakeMatch(True, " ".join(tokens[index + 1 :]).strip(), exact)


class SpeechRecognizer:
    """Envoltorio sobre Vosk: carga perezosa y reutilización del modelo."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._model: Any = None
        self._lock = threading.Lock()
        self._error: str | None = None

    # ------------------------------------------------------------------
    @property
    def sample_rate(self) -> int:
        return self._settings.stt_sample_rate

    @property
    def model_available(self) -> bool:
        return self._settings.stt_model_dir.is_dir()

    def load(self) -> Any:
        """Carga el modelo (~1-2 s la primera vez) y lo deja en memoria."""

        with self._lock:
            if self._model is not None:
                return self._model
            if not self.model_available:
                raise RecognizerUnavailable(
                    f"No encuentro el modelo de voz en {self._settings.stt_model_dir}. "
                    "Descárgalo de https://alphacephei.com/vosk/models "
                    "(vosk-model-small-es-0.42) y descomprímelo ahí."
                )
            try:
                from vosk import Model, SetLogLevel

                SetLogLevel(-1)  # Vosk es muy verboso por defecto
                self._model = Model(str(self._settings.stt_model_dir))
            except ImportError as exc:
                raise RecognizerUnavailable(
                    "El paquete 'vosk' no está instalado: no hay reconocimiento de voz."
                ) from exc
            except Exception as exc:  # noqa: BLE001 - modelo corrupto, permisos…
                raise RecognizerUnavailable(f"No pude cargar el modelo de voz: {exc}") from exc
            logger.info("Modelo de reconocimiento cargado: %s", self._settings.stt_model_dir.name)
            return self._model

    # ------------------------------------------------------------------
    def create_stream(self) -> Any:
        """Reconocedor incremental para escucha continua."""

        from vosk import KaldiRecognizer

        recognizer = KaldiRecognizer(self.load(), float(self.sample_rate))
        recognizer.SetWords(False)
        return recognizer

    def transcribe(self, pcm: bytes) -> str:
        """Transcribe un bloque completo de audio PCM 16 bits mono."""

        recognizer = self.create_stream()
        recognizer.AcceptWaveform(pcm)
        return str(json.loads(recognizer.FinalResult()).get("text", "")).strip()

    @staticmethod
    def result_text(payload: str) -> str:
        try:
            return str(json.loads(payload).get("text", "")).strip()
        except (json.JSONDecodeError, TypeError):
            return ""

    @staticmethod
    def partial_text(payload: str) -> str:
        try:
            return str(json.loads(payload).get("partial", "")).strip()
        except (json.JSONDecodeError, TypeError):
            return ""

    # ------------------------------------------------------------------
    def describe(self) -> dict[str, Any]:
        available = self.model_available
        if available and self._error is None and self._model is None:
            try:
                self.load()
            except RecognizerUnavailable as exc:
                self._error = str(exc)
                available = False
        return {
            "engine": "vosk",
            "available": available and self._error is None,
            "model": self._settings.stt_model_dir.name,
            "model_path": str(self._settings.stt_model_dir),
            "sample_rate": self.sample_rate,
            "loaded": self._model is not None,
            "cost": "gratis, offline, sin GPU",
            "error": self._error,
        }
