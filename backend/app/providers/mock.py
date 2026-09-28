"""MockAIProvider: inteligencia local, determinista y sin dependencias externas.

Permite que el MVP funcione al 100 % sin configurar ninguna API de IA.  Interpreta
el mensaje con ``RuleBasedIntentParser`` y redacta la respuesta final a partir de
los resultados reales de las herramientas.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.providers.base import AIProvider, ChatTurn, IntentResult
from app.tools.registry import ToolRegistry


class MockAIProvider(AIProvider):
    """Proveedor por defecto: reglas locales, cero llamadas de red."""

    name = "mock"
    requires_api_key = False

    def __init__(self, *, fallback_for: str | None = None) -> None:
        # Importación local para evitar un ciclo: el parser tipa contra providers.base.
        from app.agent.intent_parser import RuleBasedIntentParser

        self._parser = RuleBasedIntentParser()
        self.fallback_for = fallback_for

    # ------------------------------------------------------------------
    async def parse_intent(
        self,
        message: str,
        *,
        assistant: str,
        registry: ToolRegistry,
        history: Sequence[ChatTurn] = (),
    ) -> IntentResult:
        intent = self._parser.parse(message)
        intent.source = "mock"
        return intent

    async def compose_reply(
        self,
        message: str,
        intent: IntentResult,
        outcomes: Sequence[dict[str, Any]],
        *,
        assistant: str,
    ) -> str | None:
        if not outcomes:
            return intent.reply or None

        pending = [item for item in outcomes if item.get("status") == "awaiting_confirmation"]
        if pending:
            names = ", ".join(str(item.get("tool")) for item in pending)
            return (
                f"Antes de continuar necesito tu confirmación para: {names}. "
                "Confírmalo y lo ejecuto."
            )

        parts: list[str] = []
        for outcome in outcomes:
            text = str(outcome.get("message") or "").strip()
            if not text:
                continue
            detail = self._detail(outcome)
            parts.append(f"{text} {detail}".strip() if detail else text)
        return " ".join(parts) if parts else None

    # ------------------------------------------------------------------
    @staticmethod
    def _detail(outcome: dict[str, Any]) -> str:
        """Añade un resumen corto con los datos más útiles del resultado."""

        tool = outcome.get("tool")
        data = outcome.get("data") or {}
        if tool == "list_files":
            entries = data.get("entries") or []
            names = ", ".join(str(entry.get("name")) for entry in entries[:5])
            return f"Primeros elementos: {names}." if names else ""
        if tool == "search_files":
            results = data.get("results") or []
            if not results:
                return ""
            names = "; ".join(str(entry.get("path")) for entry in results[:5])
            extra = f" (+{len(results) - 5} más)" if len(results) > 5 else ""
            return f"Coincidencias: {names}{extra}."
        if tool == "get_running_processes":
            processes = data.get("processes") or []
            top = ", ".join(
                f"{item.get('name')} ({item.get('memory_mb')} MB)" for item in processes[:3]
            )
            return f"Los que más consumen: {top}." if top else ""
        return ""

    def describe(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "name": self.name,
            "requires_api_key": False,
            "available": True,
            "mode": "rule_based",
        }
        if self.fallback_for:
            info["fallback_for"] = self.fallback_for
            info["note"] = (
                f"Se seleccionó '{self.fallback_for}' pero no está configurado; "
                "se usa el proveedor mock."
            )
        return info
