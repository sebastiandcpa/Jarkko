"""Proveedores externos: arquitectura lista, integración pendiente.

Cada clase queda declarada para que cambiar de proveedor sea configuración y no
refactor.  Cuando se implementen, el contrato es siempre el mismo:

1. construir el prompt de sistema con ``registry.describe_for_prompt()`` (o el
   esquema de *tool calling* nativo del proveedor);
2. pedir al modelo una lista de acciones ``{"tool": ..., "arguments": {...}}``;
3. devolver un ``IntentResult``.

El modelo **nunca** recibe acceso a PowerShell, CMD ni al sistema operativo: solo
puede nombrar herramientas ya registradas, y el Validator + Permission Manager
deciden si se ejecutan.

Las claves se leen de variables de entorno (``JARVIS_AI_API_KEY``).  Nunca se
escriben en logs ni en la base de datos.
"""

from __future__ import annotations

from app.providers.base import UnimplementedProvider


class OpenAIProvider(UnimplementedProvider):
    """Integración futura con la API de OpenAI (function calling)."""

    name = "openai"
    vendor = "OpenAI"
    default_model = "gpt-4o-mini"


class AnthropicProvider(UnimplementedProvider):
    """Integración futura con la API de Anthropic (tool use)."""

    name = "anthropic"
    vendor = "Anthropic"
    default_model = "claude-sonnet-5"


class GeminiProvider(UnimplementedProvider):
    """Integración futura con la API de Google Gemini (function calling)."""

    name = "gemini"
    vendor = "Google"
    default_model = "gemini-2.0-flash"
