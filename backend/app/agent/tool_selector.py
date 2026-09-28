"""ToolSelector: resuelve el nombre pedido por la IA a una herramienta registrada.

Los modelos externos tienden a inventar variantes del nombre (``openUrl``,
``open_website``, ``mkdir``).  Aquí se normalizan esos alias **hacia herramientas
que ya existen**; lo que no se reconoce se rechaza, nunca se improvisa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.providers.base import ToolCall
from app.tools.base import ToolDefinition
from app.tools.registry import ToolRegistry

#: Alias tolerados -> nombre canónico.
TOOL_ALIASES: dict[str, str] = {
    "openurl": "open_url",
    "open_website": "open_url",
    "open_web": "open_url",
    "open_page": "open_url",
    "browse": "open_url",
    "search_web": "web_search",
    "websearch": "web_search",
    "google_search": "web_search",
    "search_internet": "web_search",
    "open_app": "open_application",
    "openapplication": "open_application",
    "launch_application": "open_application",
    "launch_app": "open_application",
    "start_application": "open_application",
    "list_directory": "list_files",
    "list_dir": "list_files",
    "ls": "list_files",
    "find_files": "search_files",
    "file_search": "search_files",
    "make_folder": "create_folder",
    "make_directory": "create_folder",
    "mkdir": "create_folder",
    "new_folder": "create_folder",
    "move": "move_file",
    "move_folder": "move_file",
    "copy": "copy_file",
    "copy_folder": "copy_file",
    "rename": "rename_file",
    "rename_folder": "rename_file",
    "system_info": "get_system_info",
    "systeminfo": "get_system_info",
    "memory_usage": "get_memory_usage",
    "ram_usage": "get_memory_usage",
    "disk_usage": "get_disk_usage",
    "processes": "get_running_processes",
    "list_processes": "get_running_processes",
    "running_processes": "get_running_processes",
    "delete": "delete_file",
    "remove_file": "delete_file",
}

_SEPARATORS_RE = re.compile(r"[\s\-.:]+")
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def canonical_name(raw: str) -> str:
    """``"Open URL"`` / ``"openUrl"`` / ``"open-url"`` -> ``"open_url"``."""

    if not isinstance(raw, str):
        return ""
    text = _CAMEL_RE.sub("_", raw.strip())
    text = _SEPARATORS_RE.sub("_", text).lower().strip("_")
    return TOOL_ALIASES.get(text.replace("_", ""), TOOL_ALIASES.get(text, text))


@dataclass(frozen=True, slots=True)
class SelectionResult:
    tool: ToolDefinition | None
    resolved_name: str
    error: str | None = None
    code: str | None = None

    @property
    def found(self) -> bool:
        return self.tool is not None


class ToolSelector:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def select(self, call: ToolCall) -> SelectionResult:
        requested = call.tool if isinstance(call.tool, str) else ""
        name = canonical_name(requested)
        if not name:
            return SelectionResult(None, "", "No se indicó ninguna herramienta.", "tool_missing")
        tool = self._registry.get(name)
        if tool is None:
            return SelectionResult(
                None,
                name,
                f"La herramienta '{requested}' no existe en el registro.",
                "tool_not_found",
            )
        return SelectionResult(tool, name)
