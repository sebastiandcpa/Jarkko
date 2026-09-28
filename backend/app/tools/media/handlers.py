"""Poner música o vídeo en un servicio autorizado.

Mismo principio que el resto: la IA dice **qué** quiere oír y **dónde**, nunca una
dirección.  Aquí dentro cada servicio tiene su plantilla fija y lo que llega del
usuario viaja codificado como parámetro de búsqueda, jamás como parte de la ruta.

Hoy abre la búsqueda del servicio, que es lo que se puede hacer sin ninguna clave
ni cuenta. Reproducir el primer resultado directamente exige la API de datos de
YouTube (gratuita, con clave) y, en Spotify, una cuenta Premium: ninguna de las dos
hace falta para que esto sirva.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, quote_plus

from app.security.risk import RiskLevel
from app.tools.base import (
    ParameterSpec,
    ParamType,
    ToolCategory,
    ToolDefinition,
    ToolResult,
)
from app.tools.browser.handlers import _open_in_browser
from app.tools.registry import ToolRegistry
from app.utils.text import normalize

#: Servicio -> (nombre visible, plantilla de búsqueda, cómo se codifica la consulta).
SERVICES: dict[str, tuple[str, str, str]] = {
    "spotify": ("Spotify", "https://open.spotify.com/search/{query}", "path"),
    "youtube": ("YouTube", "https://www.youtube.com/results?search_query={query}", "param"),
    "youtube_music": ("YouTube Music", "https://music.youtube.com/search?q={query}", "param"),
}

#: Sinónimos que puede decir el usuario.
ALIASES: dict[str, str] = {
    "spotify": "spotify",
    "spoti": "spotify",
    "youtube": "youtube",
    "yt": "youtube",
    "you tube": "youtube",
    "youtube music": "youtube_music",
    "music youtube": "youtube_music",
    "musica de youtube": "youtube_music",
}

DEFAULT_SERVICE = "spotify"


def _build_url(service: str, query: str) -> str:
    _, template, encoding = SERVICES[service]
    encoded = quote(query, safe="") if encoding == "path" else quote_plus(query)
    return template.format(query=encoded)


def play_media(arguments: Mapping[str, Any]) -> ToolResult:
    query = str(arguments.get("query") or "").strip()
    if len(query) < 2:
        return ToolResult.error(
            "Dime qué quieres escuchar: un artista, una canción o una lista.",
            reason="empty_query",
        )

    requested = normalize(str(arguments.get("service") or ""))
    service = ALIASES.get(requested, requested) or DEFAULT_SERVICE
    if service not in SERVICES:
        return ToolResult.error(
            f"No conozco el servicio «{requested}». Puedo usar: "
            + ", ".join(sorted(SERVICES))
            + ".",
            service=requested,
            allowed=sorted(SERVICES),
        )

    display_name = SERVICES[service][0]
    url = _build_url(service, query[:200])
    if not _open_in_browser(url):
        return ToolResult.error(
            "No se pudo abrir el navegador del sistema.", url=url, reason="browser_unavailable"
        )
    return ToolResult.ok(
        f"Abrí «{query}» en {display_name}.",
        url=url,
        query=query,
        service=service,
        service_name=display_name,
    )


def register(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="play_media",
            description=(
                "Abre música o vídeo en Spotify, YouTube o YouTube Music buscando lo que "
                "el usuario pide (artista, canción o lista)."
            ),
            category=ToolCategory.BROWSER,
            risk_level=RiskLevel.LOW,
            handler=play_media,
            parameters=(
                ParameterSpec(
                    name="query",
                    type=ParamType.STRING,
                    description="Qué poner: artista, canción, álbum o lista.",
                    required=True,
                    max_length=200,
                ),
                ParameterSpec(
                    name="service",
                    type=ParamType.STRING,
                    description="spotify (por defecto), youtube o youtube_music.",
                    required=False,
                    max_length=20,
                ),
            ),
            examples=("Reproduce Dominick Fike en Spotify", "Pon Bad Bunny en YouTube"),
        )
    )
