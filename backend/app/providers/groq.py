"""Cerebro de JARKKO: un modelo de lenguaje servido por Groq.

Por qué Groq: su plan gratuito da 1.000 peticiones al día y 30 por minuto sin
tarjeta, que es de sobra para un asistente personal.  La alternativa de Google se
recortó a unas 20 al día en diciembre de 2025.

**Híbrido a propósito.** Antes de preguntar a la nube se intentan las reglas
locales.  Si la frase es una orden del sistema («abre la carpeta Facturas»), se
resuelve aquí, gratis, al instante y sin que salga del equipo; a la nube solo va lo
que hace falta pensar: opiniones, resúmenes, conversación.  Menos cuota, más
privacidad y ningún cambio de comportamiento cuando internet falla.

**La seguridad no cambia por tener cerebro.**  El modelo únicamente puede *nombrar*
herramientas del registro; no ve rutas, no ejecuta nada y no hay ninguna forma de
que pida un comando.  Lo que proponga sigue pasando por el Validator, el gestor de
permisos y la verificación, igual que si lo hubiera propuesto una regla.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

from app.agent.intent_parser import RuleBasedIntentParser
from app.providers.base import (
    AIProvider,
    AIProviderError,
    ChatTurn,
    IntentResult,
    ToolCall,
)
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

#: Modelos del plan gratuito de Groq (septiembre de 2026).  Se puede cambiar con
#: ``JARVIS_AI_MODEL`` sin tocar código.
DEFAULT_MODEL = "openai/gpt-oss-120b"

_MAX_MESSAGE = 2000
_MAX_HISTORY = 6
_TIMEOUT_SECONDS = 20.0

_SYSTEM_PROMPT = """Eres JARKKO, un asistente de escritorio para Windows que habla español peruano.
Eres directo y breve: respondes en dos o tres frases como mucho, porque lo que digas se lee en voz alta.

Puedes pedir que se ejecuten estas herramientas, y NINGUNA otra:
{tools}

Reglas que no puedes romper:
- No tienes acceso a la consola, ni a PowerShell, ni a CMD, ni al sistema de archivos. Solo puedes nombrar herramientas de la lista.
- Si inventas una herramienta que no está en la lista, se descarta y el usuario se queda sin respuesta.
- Si lo que te piden no necesita ninguna herramienta (una opinión, una duda, una charla), responde tú mismo y deja "actions" vacío.
- Si te piden algo que ninguna herramienta cubre, dilo claramente y explica qué sí puedes hacer. No prometas lo que no puedes.
- Nunca inventes datos del equipo (memoria, archivos, fecha): para eso pide la herramienta correspondiente.

Responde SIEMPRE con un único objeto JSON con esta forma exacta:
{{"reply": "lo que le dices al usuario", "actions": [{{"tool": "nombre", "arguments": {{}}, "reason": "por qué"}}], "confidence": 0.0}}
Si vas a ejecutar herramientas, deja "reply" vacío: el sistema redacta la respuesta con el resultado real."""

_COMPOSE_PROMPT = """Eres JARKKO. Acabas de ejecutar unas herramientas para el usuario y tienes sus resultados.
Redacta la respuesta final en español, en una o dos frases, para leerla en voz alta.
Usa solo los datos de los resultados; no inventes nada ni añadas rutas largas.
Si algo falló, dilo con naturalidad y explica el motivo que viene en el resultado."""


class GroqProvider(AIProvider):
    """Proveedor real sobre la API de Groq (compatible con el formato de OpenAI)."""

    name = "groq"
    requires_api_key = True
    default_model = DEFAULT_MODEL
    vendor = "Groq"

    def __init__(self, *, api_key: str = "", model: str = "") -> None:
        self._api_key = api_key.strip()
        self._model = (model or DEFAULT_MODEL).strip()
        self._rules = RuleBasedIntentParser()

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    # ------------------------------------------------------------------
    async def parse_intent(
        self,
        message: str,
        *,
        assistant: str,
        registry: ToolRegistry,
        history: Sequence[ChatTurn] = (),
    ) -> IntentResult:
        # 1) Lo que las reglas entienden no sale del equipo ni gasta cuota.
        local = self._rules.parse(message)
        if local.actions:
            local.source = "rules"
            return local

        # 2) Lo demás sí necesita pensar.
        payload = {
            "model": self._model,
            "temperature": 0.3,
            "max_tokens": 700,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT.format(tools=registry.describe_for_prompt())},
                *self._history_messages(history),
                {"role": "user", "content": message[:_MAX_MESSAGE]},
            ],
        }
        data = await self._post(payload)
        return self._to_intent(data, registry)

    async def compose_reply(
        self,
        message: str,
        intent: IntentResult,
        outcomes: Sequence[dict[str, Any]],
        *,
        assistant: str,
    ) -> str | None:
        """Redacta la respuesta a partir de los resultados reales.

        Sin esto, cinco titulares suenan a lista de la compra.  Con esto, JARKKO
        los cuenta.  Si falla, el motor usa su plantilla y no se nota.
        """

        if not outcomes:
            return None
        resumen = json.dumps(self._trim_outcomes(outcomes), ensure_ascii=False)[:4000]
        payload = {
            "model": self._model,
            "temperature": 0.4,
            "max_tokens": 320,
            "messages": [
                {"role": "system", "content": _COMPOSE_PROMPT},
                {
                    "role": "user",
                    "content": f"El usuario dijo: {message[:_MAX_MESSAGE]}\nResultados: {resumen}",
                },
            ],
        }
        try:
            data = await self._post(payload)
        except AIProviderError as exc:
            logger.info("No pude redactar con el modelo (%s); uso la plantilla.", exc)
            return None
        texto = self._content(data).strip()
        return texto or None

    # ------------------------------------------------------------------
    @staticmethod
    def _history_messages(history: Sequence[ChatTurn]) -> list[dict[str, str]]:
        turnos = [turn for turn in history if turn.content][-_MAX_HISTORY:]
        return [
            {"role": "assistant" if turn.role == "assistant" else "user", "content": turn.content[:_MAX_MESSAGE]}
            for turn in turnos
        ]

    @staticmethod
    def _trim_outcomes(outcomes: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        """Solo lo que hace falta para redactar: nada de volcar el `data` entero."""

        recortados: list[dict[str, Any]] = []
        for outcome in outcomes[:6]:
            item = {
                "tool": outcome.get("tool"),
                "status": outcome.get("status"),
                "message": str(outcome.get("message") or "")[:600],
            }
            data = outcome.get("data")
            if isinstance(data, dict):
                titulares = data.get("headlines")
                if isinstance(titulares, list):
                    item["headlines"] = [
                        {"title": str(h.get("title", ""))[:160], "source": str(h.get("source", ""))[:60]}
                        for h in titulares[:8]
                        if isinstance(h, dict)
                    ]
            recortados.append(item)
        return recortados

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            raise AIProviderError("Falta la clave de Groq (JARVIS_AI_API_KEY).")
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - httpx está en requirements
            raise AIProviderError("Falta el paquete 'httpx'.") from exc

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    ENDPOINT,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except Exception as exc:  # noqa: BLE001 - red: timeout, DNS, TLS…
            raise AIProviderError(f"No pude hablar con Groq: {type(exc).__name__}") from exc

        if response.status_code == 429:
            raise AIProviderError("Se agotó la cuota gratuita de Groq por hoy.")
        if response.status_code in (401, 403):
            raise AIProviderError("Groq rechazó la clave: revísala en backend/.env.")
        if response.status_code >= 400:
            # El cuerpo puede traer la clave de vuelta en un eco: solo el código.
            raise AIProviderError(f"Groq respondió {response.status_code} (modelo: {self._model}).")
        try:
            return response.json()
        except ValueError as exc:
            raise AIProviderError("Groq devolvió algo que no es JSON.") from exc

    @staticmethod
    def _content(data: dict[str, Any]) -> str:
        try:
            return str(data["choices"][0]["message"]["content"] or "")
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError("Respuesta de Groq sin contenido.") from exc

    def _to_intent(self, data: dict[str, Any], registry: ToolRegistry) -> IntentResult:
        crudo = self._content(data)
        try:
            parsed = json.loads(crudo)
        except ValueError:
            # El modelo se fue por las ramas: al menos se aprovecha como respuesta.
            texto = crudo.strip()
            if not texto:
                raise AIProviderError("El modelo no devolvió nada utilizable.") from None
            return IntentResult(reply=texto[:1200], confidence=0.4, source=self.name, matched_rule="llm:text")
        if not isinstance(parsed, dict):
            raise AIProviderError("El modelo no devolvió un objeto JSON.")

        acciones: list[ToolCall] = []
        for item in parsed.get("actions") or []:
            if not isinstance(item, dict):
                continue
            nombre = str(item.get("tool") or "").strip()
            if not nombre:
                continue
            argumentos = item.get("arguments")
            acciones.append(
                ToolCall(
                    tool=nombre,
                    arguments=argumentos if isinstance(argumentos, dict) else {},
                    reason=str(item.get("reason") or "")[:300],
                )
            )

        try:
            confianza = float(parsed.get("confidence") or (0.8 if acciones else 0.6))
        except (TypeError, ValueError):
            confianza = 0.7

        return IntentResult(
            reply=str(parsed.get("reply") or "")[:1200],
            actions=acciones,
            confidence=max(0.0, min(confianza, 1.0)),
            source=self.name,
            matched_rule="llm",
        )

    # ------------------------------------------------------------------
    async def check(self) -> dict[str, Any]:
        """Prueba la clave y el modelo sin gastar casi nada.  Para el script de alta."""

        if not self.configured:
            return {"ok": False, "reason": "missing_api_key", "model": self._model}
        payload = {
            "model": self._model,
            "max_tokens": 5,
            "messages": [{"role": "user", "content": "di: listo"}],
        }
        try:
            data = await self._post(payload)
        except AIProviderError as exc:
            return {"ok": False, "reason": str(exc), "model": self._model}
        return {"ok": True, "model": self._model, "answer": self._content(data).strip()[:60]}

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "vendor": self.vendor,
            "model": self._model,
            "requires_api_key": True,
            "available": self.configured,
            "hybrid": "las órdenes conocidas se resuelven con reglas locales; solo lo demás va a la nube",
        }
