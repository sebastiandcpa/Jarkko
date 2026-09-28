"""Selección del proveedor de IA según configuración.

Regla de oro del MVP: el asistente **siempre** arranca.  Si el proveedor elegido
no está configurado o implementado, se degrada al ``MockAIProvider`` y se informa
en ``GET /api/health``.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.config import Settings, get_settings
from app.providers.base import AIProvider, UnimplementedProvider
from app.providers.external import AnthropicProvider, GeminiProvider, OpenAIProvider
from app.providers.groq import GroqProvider
from app.providers.mock import MockAIProvider

logger = logging.getLogger(__name__)

_EXTERNAL_PROVIDERS: dict[str, type[UnimplementedProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
}

KNOWN_PROVIDERS: tuple[str, ...] = ("mock", "groq", *_EXTERNAL_PROVIDERS)


def build_provider(settings: Settings | None = None) -> AIProvider:
    settings = settings or get_settings()
    requested = settings.ai_provider.strip().lower() or "mock"

    if requested == "mock":
        return MockAIProvider()

    if requested == "groq":
        groq = GroqProvider(api_key=settings.ai_api_key, model=settings.ai_model)
        if not groq.configured:
            logger.warning(
                "Groq está seleccionado pero falta JARVIS_AI_API_KEY. Se usa 'mock'."
            )
            return MockAIProvider(fallback_for=requested)
        logger.info("Cerebro: Groq (modelo %s)", settings.ai_model or GroqProvider.default_model)
        return groq

    provider_class = _EXTERNAL_PROVIDERS.get(requested)
    if provider_class is None:
        logger.warning("Proveedor de IA desconocido '%s'. Se usa 'mock'.", requested)
        return MockAIProvider(fallback_for=requested)

    provider = provider_class(api_key=settings.ai_api_key, model=settings.ai_model)
    if not provider.configured:
        logger.warning(
            "El proveedor '%s' no tiene API key configurada. Se usa 'mock'.", requested
        )
        return MockAIProvider(fallback_for=requested)

    # La integración real todavía no está implementada: se avisa y se degrada,
    # en lugar de romper el asistente en tiempo de ejecución.
    logger.warning(
        "El proveedor '%s' está seleccionado pero su integración no está implementada. Se usa 'mock'.",
        requested,
    )
    return MockAIProvider(fallback_for=requested)


@lru_cache(maxsize=1)
def get_provider() -> AIProvider:
    """Proveedor compartido por toda la aplicación."""

    return build_provider()
