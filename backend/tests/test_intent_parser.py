"""Tests del intérprete de lenguaje natural (MockAIProvider)."""

from __future__ import annotations

import pytest

from app.agent.intent_parser import RuleBasedIntentParser
from app.agent.tool_selector import ToolSelector, canonical_name
from app.providers.base import ToolCall
from app.tools.bootstrap import build_registry

parser = RuleBasedIntentParser()


@pytest.mark.parametrize(
    ("message", "tool", "expected_arguments"),
    [
        ("Abre YouTube", "open_url", {"url": "https://www.youtube.com"}),
        ("ábreme youtube.com", "open_url", {"url": "https://youtube.com"}),
        ("Abre la carpeta Descargas", "open_folder", {"path": "Descargas"}),
        ("abre descargas", "open_folder", {"path": "descargas"}),
        (
            "Crea una carpeta llamada Jarvis Test en Documentos",
            "create_folder",
            {"path": "Documentos\\Jarvis Test"},
        ),
        ("busca en internet recetas de pan", "web_search", {"query": "recetas de pan"}),
        ("abre el bloc de notas", "open_application", {"app_name": "notepad"}),
        ("abre chrome", "open_application", {"app_name": "chrome"}),
        ("¿cuánta memoria estoy usando?", "get_memory_usage", {}),
        ("muéstrame el espacio en disco", "get_disk_usage", {}),
        ("qué procesos están corriendo", "get_running_processes", {}),
        ("dame información del sistema", "get_system_info", {}),
        ("lista los archivos de Descargas", "list_files", {"path": "Descargas"}),
        ("busca el archivo factura.pdf", "search_files", {"query": "factura.pdf"}),
        (
            "renombra Descargas/doc.txt a notas.txt",
            "rename_file",
            {"source": "Descargas/doc.txt", "new_name": "notas.txt"},
        ),
    ],
)
def test_expected_intent(message: str, tool: str, expected_arguments: dict[str, str]) -> None:
    result = parser.parse(message)
    assert len(result.actions) == 1, result
    action = result.actions[0]
    assert action.tool == tool
    assert action.arguments == expected_arguments


def test_accents_and_case_are_preserved_in_values() -> None:
    result = parser.parse("Crea una carpeta llamada Facturación Anual en Documentos")
    assert result.actions[0].arguments["path"] == "Documentos\\Facturación Anual"


def test_move_intent_keeps_source_and_destination() -> None:
    result = parser.parse("mueve Descargas/foto.png a Imágenes")
    action = result.actions[0]
    assert action.tool == "move_file"
    assert action.arguments == {"source": "Descargas/foto.png", "destination": "Imágenes"}


def test_several_actions_in_one_sentence() -> None:
    result = parser.parse("abre youtube y spotify")
    assert [action.tool for action in result.actions] == ["open_url", "open_url"]


def test_greeting_produces_no_actions() -> None:
    result = parser.parse("hola")
    assert result.actions == []
    assert result.reply


def test_unknown_message_asks_for_clarification() -> None:
    result = parser.parse("asdfgh qwerty zxcvbn")
    assert result.actions == []
    assert result.needs_clarification


def test_empty_message_is_handled() -> None:
    result = parser.parse("   ")
    assert result.actions == []
    assert result.needs_clarification


def test_every_proposed_tool_exists_in_the_registry() -> None:
    registry = build_registry()
    messages = [
        "Abre YouTube",
        "abre chrome",
        "crea una carpeta llamada test en Documentos",
        "busca en internet python",
        "lista los archivos de Descargas",
        "cuánta memoria uso",
        "mueve Descargas/a.txt a Documentos",
        "copia Descargas/a.txt a Documentos",
        "renombra Descargas/a.txt a b.txt",
        "abre el archivo Documentos/a.txt",
        "busca el archivo a.txt",
        "qué hay en Documentos",
    ]
    for message in messages:
        for action in parser.parse(message).actions:
            assert action.tool in registry, (message, action.tool)


def test_tool_selector_normalizes_alias_names() -> None:
    assert canonical_name("openUrl") == "open_url"
    assert canonical_name("Open URL") == "open_url"
    assert canonical_name("mkdir") == "create_folder"

    selector = ToolSelector(build_registry())
    assert selector.select(ToolCall(tool="list_directory")).resolved_name == "list_files"
    rejected = selector.select(ToolCall(tool="run_command"))
    assert not rejected.found
    assert rejected.code == "tool_not_found"


# ----------------------------------------------------------------------
# tolerancia al lenguaje real (y a lo que entiende el reconocedor de voz)
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("message", "tool", "expected_arguments"),
    [
        ("¿me puedes abrir YouTube?", "open_url", {"url": "https://www.youtube.com"}),
        ("quiero que abras youtube", "open_url", {"url": "https://www.youtube.com"}),
        ("oye, ¿podrías poner Spotify?", "open_url", {"url": "https://open.spotify.com"}),
        ("necesito que busques información sobre la luna", "web_search", {"query": "luna"}),
        ("¿puedes abrir el bloc de notas?", "open_application", {"app_name": "notepad"}),
        ("cuánta memoria tengo", "get_memory_usage", {}),
        ("cómo va el disco", "get_disk_usage", {}),
    ],
)
def test_courtesy_does_not_hide_the_order(
    message: str, tool: str, expected_arguments: dict[str, str]
) -> None:
    """«¿me puedes abrir YouTube?» vale lo mismo que «abre YouTube»."""

    result = parser.parse(message)
    assert len(result.actions) == 1, result
    assert result.actions[0].tool == tool
    assert result.actions[0].arguments == expected_arguments


@pytest.mark.parametrize(
    ("heard", "tool"),
    [
        # Lo que de verdad transcribe el reconocedor cuando se le habla por un
        # micrófono Bluetooth: el verbo se rompe, el nombre propio aguanta.
        ("pueden saber youtube", "open_url"),
        ("cuenta memoria tengo", "get_memory_usage"),
        ("cuenta memoria temo", "get_memory_usage"),
    ],
)
def test_garbled_speech_still_acts(heard: str, tool: str) -> None:
    result = parser.parse(heard)
    assert len(result.actions) == 1, result
    assert result.actions[0].tool == tool


@pytest.mark.parametrize(
    "message",
    [
        "no abras youtube",
        "cierra youtube",
        "deja de poner spotify",
        "youtube spotify netflix",  # tres objetivos: no se adivina
        "estaba pensando en lo que me contaste ayer sobre youtube y su algoritmo",
        "eso de powershell",  # rescatar nunca abre una consola
    ],
)
def test_salvage_stays_quiet_when_it_could_equivocate(message: str) -> None:
    assert parser.parse(message).actions == []


def test_salvage_never_offers_a_console() -> None:
    from app.agent.intent_parser import _SALVAGE_KEYS

    for forbidden in ("powershell", "power shell", "terminal", "consola"):
        assert forbidden not in _SALVAGE_KEYS


@pytest.mark.parametrize(
    "message",
    ["hola", "¿me escuchas?", "y qué puedo hacer", "gracias", "¿qué puedes hacer?", "buenos días"],
)
def test_smalltalk_always_answers(message: str) -> None:
    result = parser.parse(message)
    assert result.matched_rule == "smalltalk"
    assert result.actions == []
    assert result.reply


def test_smalltalk_answers_to_the_point() -> None:
    assert "A tu orden" in parser.parse("gracias").reply
    assert "te escucho" in parser.parse("¿me escuchas?").reply


@pytest.mark.parametrize(
    "message",
    ["¿qué hora es?", "dime la hora", "qué día es hoy", "días hoy", "¿qué fecha es hoy?"],
)
def test_datetime_questions(message: str) -> None:
    result = parser.parse(message)
    assert [action.tool for action in result.actions] == ["get_datetime"]


@pytest.mark.parametrize("message", ["buenos días", "abre la carpeta del dia"])
def test_datetime_does_not_hijack_other_phrases(message: str) -> None:
    result = parser.parse(message)
    assert "get_datetime" not in [action.tool for action in result.actions]


# ----------------------------------------------------------------------
# reproduccion y volumen
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("message", "action"),
    [
        ("pausa", "play_pause"),
        ("pausa la música", "play_pause"),
        ("reanuda", "play_pause"),
        ("sube el volumen", "volume_up"),
        ("súbele", "volume_up"),
        ("baja el volumen", "volume_down"),
        ("silencia", "mute"),
        ("siguiente canción", "next"),
        ("canción anterior", "previous"),
    ],
)
def test_media_orders(message: str, action: str) -> None:
    result = parser.parse(message)
    assert len(result.actions) == 1, result
    assert result.actions[0].tool == "media_control"
    assert result.actions[0].arguments == {"action": action}


def test_put_music_opens_the_player() -> None:
    """Con una tecla de play y nada reproduciendose no pasaria nada visible."""

    result = parser.parse("pon música")
    assert result.actions[0].tool == "open_url"
    assert "spotify" in result.actions[0].arguments["url"]


def test_media_orders_do_not_fire_by_accident() -> None:
    assert parser.parse("sube el archivo a drive").actions == []


# ----------------------------------------------------------------------
# respuestas concretas cuando algo no se puede
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("message", "expected_rule", "must_mention"),
    [
        ("abre la carpeta", "unresolved:folder", "qué carpeta"),
        ("abre el archivo", "unresolved:file", "extensión"),
        ("abre la página de mi banco", "unresolved:url", "dirección"),
        ("abre trapatrapa", "unresolved:target", "trapatrapa"),
        ("mueve el archivo", "unresolved:path_needed", "origen"),
        ("crea una carpeta", "unresolved:create", "cómo la llamo"),
        ("borra mis descargas", "unresolved:delete", "borro"),
        ("apaga la computadora", "unresolved:no_tool", "no lo puedo hacer"),
        ("blabla", "unresolved:too_short", "blabla"),
    ],
)
def test_failures_explain_what_went_wrong(
    message: str, expected_rule: str, must_mention: str
) -> None:
    """Nunca «no te entendí»: se nombra el objeto o el motivo."""

    result = parser.parse(message)
    assert result.actions == []
    assert result.needs_clarification is True
    assert result.matched_rule == expected_rule
    assert must_mention.lower() in result.reply.lower()
    assert "no te entend" not in result.reply.lower()
