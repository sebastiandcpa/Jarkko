"""Titulares de prensa, leídos de fuentes RSS previamente autorizadas.

La IA **no** elige a qué dirección se conecta JARKKO: solo puede nombrar una fuente
del catálogo de abajo o pasar un tema, que se codifica como parámetro de búsqueda
de Google News.  Es el mismo principio que el resto del sistema: nombres lógicos
aquí dentro, direcciones reales solo en este archivo.

Sin claves, sin cuotas y sin coste: RSS es texto público.
"""

from __future__ import annotations

import logging
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

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
from app.utils.text import normalize

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 12
_USER_AGENT = "JARKKO/0.1 (asistente personal local)"

#: Espacios de nombres que aparecen en estos feeds.
_ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass(frozen=True, slots=True)
class NewsSource:
    """Una fuente permitida.  `url` puede llevar `{country}` y `{language}`."""

    key: str
    display_name: str
    url: str
    description: str = ""


SOURCES: tuple[NewsSource, ...] = (
    NewsSource(
        key="general",
        display_name="Google News",
        url="https://news.google.com/rss?hl={language}&gl={country}&ceid={country}:{language}",
        description="Portada del país: lo más relevante de todos los medios.",
    ),
    NewsSource(
        key="rpp",
        display_name="RPP Noticias",
        url="https://rpp.pe/feed",
        description="Actualidad peruana, radio RPP.",
    ),
    NewsSource(
        key="comercio",
        display_name="El Comercio",
        url="https://elcomercio.pe/arcio/rss/",
        description="Diario El Comercio (Perú).",
    ),
    NewsSource(
        key="gestion",
        display_name="Gestión",
        url="https://gestion.pe/arcio/rss/",
        description="Economía y negocios (Perú).",
    ),
)

_INDEX = {source.key: source for source in SOURCES}

#: Búsqueda por tema.  El tema viaja codificado como parámetro, nunca como ruta.
_SEARCH_URL = "https://news.google.com/rss/search?q={query}&hl={language}&gl={country}&ceid={country}:{language}"


def _feed_url(source: NewsSource) -> str:
    settings = get_settings()
    return source.url.format(country=settings.news_country, language=settings.news_language)


def _search_url(topic: str) -> str:
    settings = get_settings()
    return _SEARCH_URL.format(
        query=urllib.parse.quote_plus(topic),
        country=settings.news_country,
        language=settings.news_language,
    )


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
        return response.read()


def _text(element: Any, *names: str) -> str:
    for name in names:
        value = element.findtext(name)
        if value:
            return value.strip()
    return ""


def _split_source(title: str) -> tuple[str, str]:
    """Google News titula «Titular - Medio»: se separa para no leerlo en voz alta."""

    match = re.match(r"^(?P<title>.+?)\s+-\s+(?P<source>[^-]{2,40})$", title)
    if match is None:
        return title, ""
    return match.group("title").strip(), match.group("source").strip()


def _parse(raw: bytes, fallback_source: str) -> list[dict[str, Any]]:
    root = ElementTree.fromstring(raw)
    entries = root.findall(".//item") or root.findall(f".//{_ATOM}entry")
    headlines: list[dict[str, Any]] = []
    for entry in entries:
        title = _text(entry, "title", f"{_ATOM}title")
        if not title:
            continue
        clean_title, embedded_source = _split_source(title)
        link = _text(entry, "link", f"{_ATOM}id")
        if not link:
            anchor = entry.find(f"{_ATOM}link")
            link = anchor.get("href", "") if anchor is not None else ""
        headlines.append(
            {
                "title": clean_title,
                "source": _text(entry, "source") or embedded_source or fallback_source,
                "link": link,
                "published": _text(entry, "pubDate", f"{_ATOM}updated"),
            }
        )
    return headlines


def get_news(arguments: Mapping[str, Any]) -> ToolResult:
    topic = str(arguments.get("topic") or "").strip()
    source_name = normalize(str(arguments.get("source") or "")) or "general"
    try:
        limit = int(arguments.get("limit") or 5)
    except (TypeError, ValueError):
        limit = 5
    limit = max(1, min(limit, 15))

    if topic:
        url = _search_url(topic[:120])
        origin = f"Google News · {topic}"
    else:
        source = _INDEX.get(source_name)
        if source is None:
            return ToolResult.error(
                f"No conozco la fuente «{source_name}». Tengo: "
                + ", ".join(item.key for item in SOURCES)
                + ".",
                source=source_name,
                allowed=[item.key for item in SOURCES],
            )
        url = _feed_url(source)
        origin = source.display_name

    try:
        raw = _fetch(url)
    except urllib.error.HTTPError as exc:
        return ToolResult.error(
            f"{origin} respondió con un error {exc.code}. Prueba con otra fuente.",
            source=source_name,
            status_code=exc.code,
        )
    except Exception as exc:  # noqa: BLE001 - red: timeouts, DNS, TLS…
        logger.info("No pude leer %s: %s", origin, exc)
        return ToolResult.error(
            "No pude conectarme para leer las noticias. ¿Tienes internet ahora mismo?",
            source=source_name,
        )

    try:
        headlines = _parse(raw, origin)
    except ElementTree.ParseError:
        return ToolResult.error(f"{origin} devolvió algo que no supe leer.", source=source_name)

    if not headlines:
        return ToolResult.ok(
            f"{origin} no trae titulares en este momento.", source=source_name, total=0, headlines=[]
        )

    shown = headlines[:limit]
    cabecera = f"Titulares de {origin}" if topic else f"Titulares de {origin}"
    hablado = ". ".join(f"{index}. {item['title']}" for index, item in enumerate(shown, start=1))
    return ToolResult.ok(
        f"{cabecera}: {hablado}.",
        source=source_name,
        topic=topic,
        origin=origin,
        total=len(headlines),
        shown=len(shown),
        headlines=shown,
    )


def register(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="get_news",
            description=(
                "Lee los titulares de hoy desde fuentes de prensa autorizadas (RSS). "
                "Admite un tema concreto o una de las fuentes del catálogo."
            ),
            category=ToolCategory.SYSTEM,
            risk_level=RiskLevel.LOW,
            handler=get_news,
            parameters=(
                ParameterSpec(
                    name="topic",
                    type=ParamType.STRING,
                    description="Tema a buscar; vacío para la portada del país.",
                    required=False,
                    max_length=120,
                ),
                ParameterSpec(
                    name="source",
                    type=ParamType.STRING,
                    description="Fuente: " + ", ".join(item.key for item in SOURCES),
                    required=False,
                    max_length=20,
                ),
                ParameterSpec(
                    name="limit",
                    type=ParamType.INTEGER,
                    description="Cuántos titulares (1-15, por defecto 5).",
                    required=False,
                    default=5,
                ),
            ),
            examples=("Cuéntame las noticias de hoy", "Noticias de economía"),
        )
    )
