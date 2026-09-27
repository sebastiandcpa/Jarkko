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
