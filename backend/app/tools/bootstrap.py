"""Construcción del Tool Registry de la aplicación.

Añadir una familia de herramientas nueva = crear el módulo con su función
``register(registry)`` y añadirlo a ``_REGISTRARS``.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from app.tools.applications import handlers as applications_handlers
from app.tools.browser import handlers as browser_handlers
from app.tools.files import handlers as files_handlers
from app.tools.media import handlers as media_handlers
from app.tools.news import handlers as news_handlers
from app.tools.registry import ToolRegistry
from app.tools.system import handlers as system_handlers
from app.tools.system import media as system_media

_REGISTRARS: tuple[Callable[[ToolRegistry], None], ...] = (
    browser_handlers.register,
    applications_handlers.register,
    files_handlers.register,
    system_handlers.register,
    system_media.register,
    media_handlers.register,
    news_handlers.register,
)


def build_registry() -> ToolRegistry:
    """Crea un registro nuevo con todas las herramientas del MVP."""

    registry = ToolRegistry()
    for register in _REGISTRARS:
        register(registry)
    return registry


@lru_cache(maxsize=1)
def get_registry() -> ToolRegistry:
    """Registro compartido por toda la aplicación."""

    return build_registry()
