"""Tests de las noticias y de poner música.

Ninguno sale a internet: el RSS se sirve desde una cadena de bytes y el navegador
se sustituye por un espía.  Así los tests son rápidos y no dependen de que un
diario esté levantado.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.agent.intent_parser import RuleBasedIntentParser
from app.tools.media import handlers as media
from app.tools.news import handlers as news

parser = RuleBasedIntentParser()

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Noticias de prueba</title>
  <item>
    <title>Sube el precio del limón - El Comercio</title>
    <link>https://example.com/limon</link>
    <pubDate>Sun, 27 Sep 2026 20:00:00 GMT</pubDate>
  </item>
  <item>
    <title>El Congreso debate la ley de datos</title>
    <link>https://example.com/congreso</link>
  </item>
</channel></rss>
""".encode("utf-8")


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Sustituye la descarga: guarda la URL pedida y devuelve el RSS de prueba."""

    pedidas: list[str] = []

    def fake_fetch(url: str) -> bytes:
        pedidas.append(url)
        return RSS

    monkeypatch.setattr(news, "_fetch", fake_fetch)
    return pedidas


# ----------------------------------------------------------------------
# noticias
# ----------------------------------------------------------------------
def test_headlines_are_read_and_cleaned(offline: list[str]) -> None:
    result = news.get_news({})

    assert result.data["shown"] == 2
    first = result.data["headlines"][0]
    # El medio va en su campo, no pegado al titular: en voz alta sonaría fatal.
    assert first["title"] == "Sube el precio del limón"
    assert first["source"] == "El Comercio"
    assert "Sube el precio del limón" in result.message


def test_limit_is_clamped(offline: list[str]) -> None:
    assert news.get_news({"limit": 999}).data["shown"] == 2
    assert news.get_news({"limit": 1}).data["shown"] == 1
    assert news.get_news({"limit": "no es un número"}).data["shown"] == 2


def test_topic_travels_encoded(offline: list[str]) -> None:
    news.get_news({"topic": "inteligencia artificial & robots"})

    url = offline[-1]
    assert url.startswith("https://news.google.com/rss/search?q=")
    # Lo que escribe el usuario nunca se pega crudo a la dirección.
    assert "inteligencia+artificial" in url
    assert " " not in url and "&robots" not in url


def test_unknown_source_is_refused_without_touching_the_network(offline: list[str]) -> None:
    result = news.get_news({"source": "diario inventado"})

    assert result.status.value == "error"
    assert offline == []
    assert "gestion" in result.message


def test_network_failure_is_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    def explota(url: str) -> bytes:
        raise TimeoutError("sin red")

    monkeypatch.setattr(news, "_fetch", explota)
    result = news.get_news({})

    assert result.status.value == "error"
    assert "internet" in result.message.lower()


# ----------------------------------------------------------------------
# música
# ----------------------------------------------------------------------
@pytest.fixture
def browser(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    abiertas: list[str] = []

    def fake_open(url: str) -> bool:
        abiertas.append(url)
        return True

    monkeypatch.setattr(media, "_open_in_browser", fake_open)
    return abiertas


@pytest.mark.parametrize(
    ("service", "expected"),
    [
        ("", "https://open.spotify.com/search/"),
        ("spotify", "https://open.spotify.com/search/"),
        ("youtube", "https://www.youtube.com/results?search_query="),
        ("yt", "https://www.youtube.com/results?search_query="),
        ("youtube music", "https://music.youtube.com/search?q="),
    ],
)
def test_each_service_has_its_own_fixed_template(
    browser: list[str], service: str, expected: str
) -> None:
    result = media.play_media({"query": "Dominick Fike", "service": service})

    assert result.status.value == "success"
    assert browser[-1].startswith(expected)
    assert "Dominick" in browser[-1]


def test_query_is_encoded_never_concatenated(browser: list[str]) -> None:
    media.play_media({"query": "rock & roll/años 80", "service": "youtube"})

    url = browser[-1]
    assert url.startswith("https://www.youtube.com/results?search_query=")
    assert " " not in url
    assert url.count("?") == 1  # nada se cuela como parámetro nuevo


def test_unknown_service_opens_nothing(browser: list[str]) -> None:
    result = media.play_media({"query": "algo", "service": "deezer"})

    assert result.status.value == "error"
    assert browser == []


def test_empty_query_asks_instead_of_opening(browser: list[str]) -> None:
    result = media.play_media({"query": " "})

    assert result.status.value == "error"
    assert browser == []


# ----------------------------------------------------------------------
# lenguaje
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("message", "expected_arguments"),
    [
        ("cuéntame las noticias de hoy", {}),
        ("qué noticias hay", {}),
        ("noticias de hoy en mi país", {}),
        ("dame los titulares", {}),
        ("noticias de economía", {"source": "gestion"}),
        ("noticias sobre inteligencia artificial", {"topic": "inteligencia artificial"}),
    ],
)
def test_news_orders(message: str, expected_arguments: dict[str, str]) -> None:
    result = parser.parse(message)

    assert [action.tool for action in result.actions] == ["get_news"]
    assert result.actions[0].arguments == expected_arguments


@pytest.mark.parametrize(
    ("message", "expected_arguments"),
    [
        ("reproduce Dominick Fike en Spotify", {"query": "Dominick Fike", "service": "spotify"}),
        ("pon Bad Bunny en YouTube", {"query": "Bad Bunny", "service": "youtube"}),
        ("reproduce música de Dominick Fike", {"query": "Dominick Fike"}),
        ("quiero escuchar Rosalía", {"query": "Rosalía"}),
    ],
)
def test_play_orders(message: str, expected_arguments: dict[str, str]) -> None:
    result = parser.parse(message)

    assert [action.tool for action in result.actions] == ["play_media"]
    assert result.actions[0].arguments == expected_arguments


def test_putting_on_a_site_still_opens_the_site() -> None:
    """«pon Spotify» es abrir Spotify, no buscar la palabra «Spotify» dentro."""

    assert parser.parse("pon spotify").actions[0].tool == "open_url"
    assert parser.parse("pon música").actions[0].tool == "open_url"
