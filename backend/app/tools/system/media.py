"""Control de reproducción y volumen mediante las teclas multimedia de Windows.

Esto **no** es ejecución de comandos: la IA solo puede pedir una de las acciones de
``MEDIA_ACTIONS``, y cada una está atada en este archivo a un código de tecla virtual
fijo.  No hay ``subprocess``, no hay texto del modelo llegando al sistema operativo y
no hay forma de pedir una tecla que no esté en esta tabla.

Windows no ofrece una lectura barata del volumen sin dependencias extra, así que el
resultado dice que la tecla se envió, no que el volumen sea ahora otro: prometer una
verificación que no se ha hecho sería mentir.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Any

from app.security.risk import RiskLevel
from app.tools.base import (
    ParameterSpec,
    ParamType,
    ToolCategory,
    ToolDefinition,
    ToolResult,
)
from app.tools.registry import ToolRegistry

#: Acción lógica -> (código de tecla virtual, repeticiones, confirmación hablada).
MEDIA_ACTIONS: dict[str, tuple[int, int, str]] = {
    "play_pause": (0xB3, 1, "Reproducción alternada."),
    "next": (0xB0, 1, "Siguiente pista."),
    "previous": (0xB1, 1, "Pista anterior."),
    "stop": (0xB2, 1, "Reproducción detenida."),
    "volume_up": (0xAF, 4, "Subí el volumen."),
    "volume_down": (0xAE, 4, "Bajé el volumen."),
    "mute": (0xAD, 1, "Silencio alternado."),
}

_KEYEVENTF_KEYUP = 0x0002


def _press(key_code: int, times: int) -> None:
    """Pulsa y suelta una tecla virtual concreta ``times`` veces."""

    import ctypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    for _ in range(times):
        user32.keybd_event(key_code, 0, 0, 0)
        user32.keybd_event(key_code, 0, _KEYEVENTF_KEYUP, 0)


def media_control(arguments: Mapping[str, Any]) -> ToolResult:
    action = str(arguments.get("action") or "").strip().lower()
    if action not in MEDIA_ACTIONS:
        return ToolResult.error(
            f"No conozco la acción «{action}». Admito: {', '.join(sorted(MEDIA_ACTIONS))}.",
            action=action,
            allowed=sorted(MEDIA_ACTIONS),
        )
    if sys.platform != "win32":
        return ToolResult.error("Las teclas multimedia solo existen en Windows.", action=action)

    key_code, times, message = MEDIA_ACTIONS[action]
    try:
        _press(key_code, times)
    except Exception as exc:  # noqa: BLE001 - ctypes/user32 puede fallar de formas variadas
        return ToolResult.error(f"No pude enviar la tecla multimedia: {exc}", action=action)

    return ToolResult.ok(message, action=action, key_presses=times, verified=False)


def register(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="media_control",
            description=(
                "Envía una tecla multimedia de Windows: reproducir/pausar, pista anterior o "
                "siguiente, detener, subir o bajar el volumen, silenciar. No escribe comandos."
            ),
            category=ToolCategory.SYSTEM,
            risk_level=RiskLevel.LOW,
            handler=media_control,
            parameters=(
                ParameterSpec(
                    name="action",
                    type=ParamType.STRING,
                    description="Una de: " + ", ".join(sorted(MEDIA_ACTIONS)),
                    required=True,
                    max_length=20,
                ),
            ),
            examples=("Pausa la música", "Sube el volumen", "Siguiente canción"),
        )
    )
