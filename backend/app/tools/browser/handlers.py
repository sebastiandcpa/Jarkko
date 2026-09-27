"""Herramientas de navegador: abrir URLs y lanzar búsquedas web.

Se usa ``webbrowser.open`` (navegador por defecto del usuario).  La URL ya llega
validada por el Validator: solo http/https, sin credenciales embebidas.
"""

from __future__ import annotations

import webbrowser
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote_plus

from app.config import get_settings
from app.security.risk import RiskLevel
from app.tools.base import (
    ParameterSpec,
    ParamType,
    ToolCategory,
    ToolDefinition,
    ToolResult,
)
from app.tools.registry import ToolRegistry

SEARCH_ENGINES: dict[str, str] = {
    "google": "https://www.google.com/search?q={query}",
    "duckduckgo": "https://duckduckgo.com/?q={query}",
    "bing": "https://www.bing.com/search?q={query}",
}


def _open_in_browser(url: str) -> bool:
    return webbrowser.open(url, new=2, autoraise=True)


def open_url(arguments: Mapping[str, Any]) -> ToolResult:
    url: str = arguments["url"]
    if not _open_in_browser(url):
        return ToolResult.error(
            "No se pudo abrir el navegador del sistema.", url=url, reason="browser_unavailable"
        )
    return ToolResult.ok(f"Abrí {url} en el navegador.", url=url)


def web_search(arguments: Mapping[str, Any]) -> ToolResult:
    query: str = arguments["query"]
    settings = get_settings()
    engine = settings.search_engine.strip().lower()
    template = SEARCH_ENGINES.get(engine, SEARCH_ENGINES["google"])
    url = template.format(query=quote_plus(query))
    if not _open_in_browser(url):
        return ToolResult.error(
            "No se pudo abrir el navegador del sistema.", url=url, reason="browser_unavailable"
        )
    return ToolResult.ok(
        f"Busqué «{query}» en {engine}.", url=url, query=query, engine=engine
    )


def register(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="open_url",
            description="Abre una URL http/https en el navegador por defecto.",
            category=ToolCategory.BROWSER,
            risk_level=RiskLevel.LOW,
            handler=open_url,
            parameters=(
                ParameterSpec(
                    name="url",
                    type=ParamType.URL,
                    description="Dirección web a abrir (http o https).",
                ),
            ),
            examples=("Abre YouTube", "Abre github.com"),
        )
    )

    registry.register(
        ToolDefinition(
            name="web_search",
            description="Realiza una búsqueda en el buscador configurado y la abre en el navegador.",
            category=ToolCategory.BROWSER,
            risk_level=RiskLevel.LOW,
            handler=web_search,
            parameters=(
                ParameterSpec(
                    name="query",
                    type=ParamType.STRING,
                    description="Texto a buscar.",
                    max_length=512,
                ),
            ),
            examples=("Busca en internet recetas de pan", "Búscame documentación de FastAPI"),
        )
    )
