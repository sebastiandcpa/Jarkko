"""Application Registry: aplicaciones que el asistente puede abrir.

La IA nunca indica un ejecutable ni argumentos: solo un nombre lógico
(``"chrome"``, ``"bloc de notas"``).  Este catálogo resuelve ese nombre a una ruta
concreta previamente autorizada.  Ampliar el catálogo es añadir un ``AppSpec``.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from app.security.risk import RiskLevel
from app.utils.text import normalize


@dataclass(frozen=True, slots=True)
class AppSpec:
    """Aplicación permitida."""

    key: str
    display_name: str
    aliases: tuple[str, ...] = ()
    candidates: tuple[str, ...] = ()
    """Rutas candidatas (admiten variables de entorno estilo Windows)."""
    which: tuple[str, ...] = ()
    """Ejecutables a buscar en el PATH si ninguna candidata existe."""
    risk_level: RiskLevel = RiskLevel.LOW
    """Riesgo específico: abrir una shell pesa más que abrir la calculadora."""
    note: str = ""

    def all_names(self) -> tuple[str, ...]:
        return (self.key, self.display_name, *self.aliases)

    def resolve(self) -> Path | None:
        """Primera ruta existente, o ``None`` si la app no está instalada."""

        for raw in self.candidates:
            expanded = os.path.expandvars(raw)
            if "%" in expanded:  # variable inexistente en esta máquina
                continue
            path = Path(expanded)
            if path.is_file():
                return path
        for executable in self.which:
            found = shutil.which(executable)
            if found:
                return Path(found)
        return None


APPLICATIONS: tuple[AppSpec, ...] = (
    AppSpec(
        key="chrome",
        display_name="Google Chrome",
        aliases=("google chrome", "navegador chrome"),
        candidates=(
            r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
            r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
            r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
        ),
        which=("chrome",),
    ),
    AppSpec(
        key="edge",
        display_name="Microsoft Edge",
        aliases=("microsoft edge", "msedge"),
        candidates=(
            r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
            r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
        ),
        which=("msedge",),
    ),
    AppSpec(
        key="firefox",
        display_name="Mozilla Firefox",
        aliases=("mozilla firefox", "mozilla"),
        candidates=(
            r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
            r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe",
        ),
        which=("firefox",),
    ),
    AppSpec(
        key="vscode",
        display_name="Visual Studio Code",
        aliases=("vs code", "visual studio code", "code", "editor de codigo"),
        candidates=(
            r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
            r"%ProgramFiles%\Microsoft VS Code\Code.exe",
            r"%ProgramFiles(x86)%\Microsoft VS Code\Code.exe",
        ),
        which=("code",),
    ),
    AppSpec(
        key="notepad",
        display_name="Bloc de notas",
        aliases=("bloc de notas", "notas", "notepad"),
        candidates=(
            r"%WINDIR%\system32\notepad.exe",
            r"%SystemRoot%\system32\notepad.exe",
        ),
        which=("notepad",),
    ),
    AppSpec(
        key="calculator",
        display_name="Calculadora",
        aliases=("calculadora", "calc", "calculator"),
        candidates=(
            r"%WINDIR%\system32\calc.exe",
            r"%SystemRoot%\system32\calc.exe",
        ),
        which=("calc",),
    ),
    AppSpec(
        key="explorer",
        display_name="Explorador de archivos",
        aliases=("explorador", "explorador de archivos", "explorer", "archivos"),
        candidates=(
            r"%WINDIR%\explorer.exe",
            r"%SystemRoot%\explorer.exe",
        ),
        which=("explorer",),
    ),
    AppSpec(
        key="powershell",
        display_name="Windows PowerShell",
        aliases=("power shell", "terminal", "consola"),
        candidates=(
            r"%WINDIR%\System32\WindowsPowerShell\v1.0\powershell.exe",
            r"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe",
        ),
        which=("powershell",),
        risk_level=RiskLevel.HIGH,
        note=(
            "Se abre una ventana interactiva vacía para el usuario. "
            "El asistente no escribe ni ejecuta comandos dentro de ella."
        ),
    ),
)


_INDEX: dict[str, AppSpec] = {}
for _spec in APPLICATIONS:
    for _name in _spec.all_names():
        _INDEX[normalize(_name)] = _spec


def find_app(name: str) -> AppSpec | None:
    """Busca una aplicación por nombre lógico o alias (tolerante a tildes/mayúsculas)."""

    if not isinstance(name, str) or not name.strip():
        return None
    key = normalize(name)
    if key in _INDEX:
        return _INDEX[key]
    # Coincidencia parcial: "abre el bloc de notas de windows"
    for alias, spec in _INDEX.items():
        if len(alias) >= 4 and (alias in key or key in alias):
            return spec
    return None


def app_names() -> tuple[str, ...]:
    return tuple(spec.display_name for spec in APPLICATIONS)


def catalog() -> list[dict[str, object]]:
    """Catálogo público: qué apps conoce el asistente y cuáles están instaladas."""

    entries: list[dict[str, object]] = []
    for spec in APPLICATIONS:
        resolved = spec.resolve()
        entries.append(
            {
                "key": spec.key,
                "display_name": spec.display_name,
                "aliases": list(spec.aliases),
                "installed": resolved is not None,
                "risk_level": spec.risk_level.value,
                "note": spec.note,
            }
        )
    return entries
