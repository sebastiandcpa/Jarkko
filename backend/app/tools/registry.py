"""Tool Registry: catálogo central de herramientas.

Todo el sistema (agente, API, tests) consulta este registro.  No hay cadenas de
``if/else`` repartidas por el proyecto: registrar una herramienta nueva consiste en
declarar su ``ToolDefinition`` y añadirla aquí.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from app.tools.base import ToolCategory, ToolDefinition


class ToolNotFoundError(LookupError):
    """La herramienta solicitada no está registrada."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Herramienta desconocida: '{name}'")
        self.name = name


class DuplicateToolError(ValueError):
    """Se intentó registrar dos veces el mismo nombre."""


class ToolRegistry:
    """Registro en memoria de las herramientas disponibles."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    # ------------------------------------------------------------------
    def register(self, tool: ToolDefinition) -> ToolDefinition:
        if tool.name in self._tools:
            raise DuplicateToolError(f"La herramienta '{tool.name}' ya está registrada.")
        self._tools[tool.name] = tool
        return tool

    def register_all(self, tools: list[ToolDefinition]) -> None:
        for tool in tools:
            self.register(tool)

    # ------------------------------------------------------------------
    def get(self, name: str) -> ToolDefinition | None:
        if not isinstance(name, str):
            return None
        return self._tools.get(name.strip())

    def require(self, name: str) -> ToolDefinition:
        tool = self.get(name)
        if tool is None:
            raise ToolNotFoundError(str(name))
        return tool

    # ------------------------------------------------------------------
    def all(self) -> tuple[ToolDefinition, ...]:
        return tuple(self._tools.values())

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def by_category(self, category: ToolCategory) -> tuple[ToolDefinition, ...]:
        return tuple(tool for tool in self._tools.values() if tool.category is category)

    def enabled(self) -> tuple[ToolDefinition, ...]:
        return tuple(tool for tool in self._tools.values() if tool.enabled)

    def catalog(self) -> list[dict[str, Any]]:
        """Catálogo serializable, ordenado por categoría y nombre."""

        return [
            tool.to_public()
            for tool in sorted(self._tools.values(), key=lambda item: (item.category.value, item.name))
        ]

    def describe_for_prompt(self) -> str:
        """Resumen compacto de herramientas, pensado para el prompt de un LLM."""

        lines: list[str] = []
        for tool in sorted(self._tools.values(), key=lambda item: item.name):
            if not tool.enabled:
                continue
            params = ", ".join(
                f"{spec.name}{'' if spec.required else '?'}:{spec.type.value}" for spec in tool.parameters
            )
            lines.append(f"- {tool.name}({params}) [{tool.risk_level.value}] {tool.description}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._tools

    def __iter__(self) -> Iterator[ToolDefinition]:
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)
