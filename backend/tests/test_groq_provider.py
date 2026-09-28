"""Tests del cerebro (Groq).  Ninguno sale a internet: se sustituye el POST."""

from __future__ import annotations

from typing import Any

import pytest

from app.agent.intent_parser import IntentParser
from app.providers.base import AIProviderError, ChatTurn
from app.providers.groq import GroqProvider
from app.tools.bootstrap import build_registry
from tests.conftest import run

registry = build_registry()


def _answer(content: str) -> dict[str, Any]:
    return {"choices": [{"message": {"content": content}}]}


def _provider(monkeypatch: pytest.MonkeyPatch, *answers: Any) -> tuple[GroqProvider, list[dict]]:
    """Proveedor con clave falsa y un POST que devuelve respuestas preparadas."""

    enviados: list[dict] = []
    pendientes = list(answers)

    async def fake_post(self: GroqProvider, payload: dict[str, Any]) -> dict[str, Any]:
        enviados.append(payload)
        siguiente = pendientes.pop(0) if pendientes else _answer('{"reply":"vale"}')
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente

    monkeypatch.setattr(GroqProvider, "_post", fake_post)
    return GroqProvider(api_key="gsk_de_mentira", model="modelo-de-prueba"), enviados


# ----------------------------------------------------------------------
def test_known_orders_never_leave_the_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Una orden que las reglas entienden no gasta cuota ni sale a la nube."""

    provider, enviados = _provider(monkeypatch)

    intent = run(provider.parse_intent("abre youtube", assistant="jarkko", registry=registry))

    assert enviados == []
    assert intent.source == "rules"
    assert intent.actions[0].tool == "open_url"


def test_conversation_goes_to_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, enviados = _provider(
        monkeypatch,
        _answer('{"reply":"Yo usaría la primera opción, es más simple.","actions":[],"confidence":0.7}'),
    )

    intent = run(
        provider.parse_intent(
            "¿qué opción te parece mejor?", assistant="jarkko", registry=registry
        )
    )

    assert len(enviados) == 1
    assert intent.source == "groq"
    assert "primera opción" in intent.reply
    assert intent.actions == []


def test_the_catalog_of_tools_travels_in_the_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, enviados = _provider(monkeypatch, _answer('{"reply":"ya"}'))

    run(provider.parse_intent("cuéntame un chiste", assistant="jarkko", registry=registry))

    system = enviados[0]["messages"][0]["content"]
    assert "get_news" in system and "open_url" in system
    # Y la prohibición, explícita en el prompt:
    assert "PowerShell" in system


def test_history_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, enviados = _provider(monkeypatch, _answer('{"reply":"ok"}'))
    historia = [ChatTurn(role="user", content=f"mensaje {index}") for index in range(20)]

    run(
        provider.parse_intent(
            "y entonces?", assistant="jarkko", registry=registry, history=historia
        )
    )

    # sistema + 6 de historia + el mensaje actual
    assert len(enviados[0]["messages"]) == 8


def test_actions_proposed_by_the_model_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _ = _provider(
        monkeypatch,
        _answer('{"reply":"","actions":[{"tool":"get_news","arguments":{"topic":"sismo"},"reason":"pidio noticias"}],"confidence":0.9}'),
    )

    intent = run(provider.parse_intent("y del sismo qué se sabe", assistant="jarkko", registry=registry))

    assert intent.actions[0].tool == "get_news"
    assert intent.actions[0].arguments == {"topic": "sismo"}


def test_invented_tools_are_dropped_before_the_planner(monkeypatch: pytest.MonkeyPatch) -> None:
    """La defensa de siempre: si el modelo inventa una herramienta, no existe."""

    provider, _ = _provider(
        monkeypatch,
        _answer('{"reply":"","actions":[{"tool":"run_command","arguments":{"cmd":"format c:"}},{"tool":"get_datetime","arguments":{}}]}'),
    )
    facade = IntentParser(provider, registry)

    intent = run(facade.parse("haz lo que quieras", assistant="jarkko"))

    assert [action.tool for action in intent.actions] == ["get_datetime"]


def test_text_instead_of_json_is_still_an_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _ = _provider(monkeypatch, _answer("Pues yo creo que sí, adelante."))

    intent = run(provider.parse_intent("¿tú qué harías?", assistant="jarkko", registry=registry))

    assert intent.matched_rule == "llm:text"
    assert "adelante" in intent.reply


def test_a_failure_falls_back_to_the_local_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin cuota o sin internet, JARKKO sigue funcionando con sus reglas."""

    provider, enviados = _provider(
        monkeypatch, AIProviderError("Se agotó la cuota gratuita de Groq por hoy.")
    )
    facade = IntentParser(provider, registry)

    # Una orden normal ni siquiera intenta salir: la resuelven las reglas.
    orden = run(facade.parse("qué hora es", assistant="jarkko"))
    assert enviados == []
    assert orden.actions[0].tool == "get_datetime"

    # Y lo que sí necesitaba al modelo cae en las reglas, que responden con criterio.
    charla = run(facade.parse("¿tú qué opinas de todo esto?", assistant="jarkko"))
    assert len(enviados) == 1
    assert charla.source.endswith("fallback")
    assert charla.reply and "no te entend" not in charla.reply.lower()


def test_compose_reply_uses_the_real_results(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, enviados = _provider(monkeypatch, _answer("Hay temblor en Chile y el Congreso debate la ley."))
    outcomes = [
        {
            "tool": "get_news",
            "status": "success",
            "message": "Titulares...",
            "data": {"headlines": [{"title": "Temblor en Chile", "source": "RPP"}]},
        }
    ]

    texto = run(provider.compose_reply("noticias", None, outcomes, assistant="jarkko"))  # type: ignore[arg-type]

    assert "temblor" in texto.lower()
    assert "Temblor en Chile" in enviados[0]["messages"][1]["content"]


def test_compose_reply_returns_none_when_the_model_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _ = _provider(monkeypatch, AIProviderError("sin red"))

    assert run(provider.compose_reply("hola", None, [{"tool": "x"}], assistant="jarkko")) is None  # type: ignore[arg-type]


def test_the_api_key_is_never_in_an_error_message() -> None:
    provider = GroqProvider(api_key="gsk_super_secreta_123", model="m")

    descripcion = str(provider.describe())
    assert "gsk_super_secreta_123" not in descripcion
    assert provider.describe()["available"] is True
