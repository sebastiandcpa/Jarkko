"""Catálogo de frases fijas de JARKKO.

Estas son las únicas frases que se sintetizan con la voz de identidad
(ElevenLabs) y se guardan en caché **para siempre**: unos 2.000 caracteres en
total, es decir una fracción de la cuota gratuita de un solo mes, y no vuelven a
gastar nada.

Regla de oro: **ninguna frase de aquí lleva variables**.  Lo variable (rutas,
nombres, cifras) se muestra en el chat y, si hace falta decirlo, lo dice la voz
local ilimitada.
"""

from __future__ import annotations

from app.agent.executor import ActionStatus

#: clave -> texto exacto que se sintetiza y se cachea.
PHRASES: dict[str, str] = {
    # --- presencia ---
    "greeting": "Hola. Soy Jarkko. ¿Qué necesitas?",
    "presence": "Aquí estoy.",
    "listening": "Te escucho.",
    "working": "Dame un momento.",
    "capabilities": (
        "Puedo abrir aplicaciones y páginas web, buscar y abrir archivos, "
        "crear carpetas, mover, copiar o renombrar cosas, y contarte cómo va el sistema."
    ),
    # --- confirmaciones de éxito, una por familia de acción ---
    "ack.generic": "Hecho.",
    "ack.url": "Listo, lo abrí en el navegador.",
    "ack.search": "Ya te lancé la búsqueda.",
    "ack.app": "Aplicación abierta.",
    "ack.folder_opened": "Ahí tienes la carpeta.",
    "ack.file_opened": "Archivo abierto.",
    "ack.folder_created": "Carpeta creada y verificada.",
    "ack.moved": "Listo, lo moví y lo verifiqué.",
    "ack.copied": "Copia hecha y verificada.",
    "ack.renamed": "Renombrado y verificado.",
    "ack.listed": "Aquí tienes el contenido, mira la pantalla.",
    "ack.found": "Encontré resultados, te los muestro en pantalla.",
    "ack.not_found": "No encontré nada que coincida.",
    # --- problemas ---
    "error.generic": "No pude completarlo.",
    "error.not_found": "No encontré esa ruta.",
    "error.conflict": "El destino ya existe, así que no toqué nada.",
    "error.denied": "Eso no te lo puedo hacer.",
    "error.rejected": "Esa orden no pasó las comprobaciones de seguridad.",
    "error.unknown_app": "No conozco esa aplicación.",
    # --- confirmación explícita del usuario ---
    "confirm.required": "Eso es delicado. Necesito que me lo confirmes.",
    "confirm.cancelled": "Cancelado. No hice nada.",
    # --- conversación ---
    "no_understand": "No te entendí. ¿Me lo dices de otra forma?",
    "empty": "No escuché nada.",
}

#: Frases fijas que corresponden a cada estado de acción cuando no hay una más
#: específica para la herramienta.
_STATUS_PHRASES: dict[ActionStatus, str] = {
    ActionStatus.SUCCESS: "ack.generic",
    ActionStatus.ERROR: "error.generic",
    ActionStatus.CONFLICT: "error.conflict",
    ActionStatus.DENIED: "error.denied",
    ActionStatus.REJECTED: "error.rejected",
    ActionStatus.AWAITING_CONFIRMATION: "confirm.required",
    ActionStatus.CANCELLED: "confirm.cancelled",
    ActionStatus.SKIPPED: "error.generic",
}

#: Frase fija por herramienta cuando la acción sale bien.
_TOOL_SUCCESS_PHRASES: dict[str, str] = {
    "open_url": "ack.url",
    "web_search": "ack.search",
    "open_application": "ack.app",
    "open_folder": "ack.folder_opened",
    "open_file": "ack.file_opened",
    "create_folder": "ack.folder_created",
    "move_file": "ack.moved",
    "copy_file": "ack.copied",
    "rename_file": "ack.renamed",
    "list_files": "ack.listed",
    "play_media": "ack.url",
}

#: Herramientas informativas: aquí el dato ES la respuesta, así que se lee el
#: texto dinámico con la voz local en lugar de una frase fija.
SPOKEN_DYNAMIC_TOOLS: frozenset[str] = frozenset(
    {
        "get_system_info",
        "get_memory_usage",
        "get_disk_usage",
        "get_running_processes",
        "get_datetime",
        "get_news",
    }
)


def phrase(key: str) -> str | None:
    return PHRASES.get(key)


def phrase_for_action(tool: str, status: ActionStatus, *, found_results: bool | None = None) -> str | None:
    """Clave de frase fija para el resultado de una acción, o ``None`` si toca texto libre."""

    if tool in SPOKEN_DYNAMIC_TOOLS:
        return None
    if status is ActionStatus.SUCCESS:
        if tool == "search_files":
            return "ack.found" if found_results else "ack.not_found"
        return _TOOL_SUCCESS_PHRASES.get(tool, "ack.generic")
    return _STATUS_PHRASES.get(status, "error.generic")


def total_characters() -> int:
    """Caracteres que cuesta generar el caché completo (control de cuota)."""

    return sum(len(text) for text in PHRASES.values())


def catalog() -> list[dict[str, object]]:
    return [
        {"key": key, "text": text, "characters": len(text)}
        for key, text in sorted(PHRASES.items())
    ]
