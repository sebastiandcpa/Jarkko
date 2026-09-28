"""Utilidades de texto compartidas (normalización para comparar entradas)."""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE_RE = re.compile(r"\s+")


def strip_accents(text: str) -> str:
    """Elimina tildes y diacríticos: ``"Música"`` -> ``"Musica"``."""

    decomposed = unicodedata.normalize("NFD", text)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def normalize(text: str) -> str:
    """Normaliza para comparaciones tolerantes: minúsculas, sin tildes, sin espacios extra."""

    return _WHITESPACE_RE.sub(" ", strip_accents(text).lower()).strip()


def truncate(text: str, limit: int = 500) -> str:
    """Recorta cadenas largas dejando constancia del recorte."""

    if len(text) <= limit:
        return text
    return f"{text[:limit]}… (+{len(text) - limit} caracteres)"


def fold(text: str) -> str:
    """Minúsculas sin tildes **conservando la longitud** carácter a carácter.

    Permite ejecutar expresiones regulares sobre el texto normalizado y usar los
    índices resultantes para recortar el texto ORIGINAL (con tildes y mayúsculas).
    """

    folded: list[str] = []
    for char in text:
        decomposed = unicodedata.normalize("NFD", char)
        base = decomposed[0] if decomposed else char
        folded.append(base.lower())
    return "".join(folded)
