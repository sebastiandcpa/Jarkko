"""IntentParser: de lenguaje natural a peticiones de herramienta.

Dos piezas:

* ``RuleBasedIntentParser``: motor determinista (español e inglés básico) que no
  necesita ninguna API.  Es el cerebro del ``MockAIProvider`` y también la red de
  seguridad cuando un proveedor externo falla.
* ``IntentParser``: fachada que usa el ``AIProvider`` configurado y cae a las
  reglas si el proveedor no está disponible.

Ninguna de las dos ejecuta nada: solo producen ``ToolCall`` candidatas.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from typing import Any, Callable

from app.providers.base import (
    AIProvider,
    AIProviderError,
    ChatTurn,
    IntentResult,
    ToolCall,
)
from app.security.paths import FOLDER_ALIASES
from app.security.risk import RiskLevel
from app.tools.applications.catalog import APPLICATIONS, find_app
from app.tools.registry import ToolRegistry
from app.utils.text import fold, normalize

logger = logging.getLogger(__name__)

#: Sitios web frecuentes -> URL canónica.
SITES: dict[str, str] = {
    "youtube": "https://www.youtube.com",
    "yt": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "correo": "https://mail.google.com",
    "drive": "https://drive.google.com",
    "google drive": "https://drive.google.com",
    "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "calendar": "https://calendar.google.com",
    "github": "https://github.com",
    "gitlab": "https://gitlab.com",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "gemini": "https://gemini.google.com",
    "wikipedia": "https://es.wikipedia.org",
    "netflix": "https://www.netflix.com",
    "disney": "https://www.disneyplus.com",
    "disney plus": "https://www.disneyplus.com",
    "prime video": "https://www.primevideo.com",
    "spotify": "https://open.spotify.com",
    "twitch": "https://www.twitch.tv",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "tiktok": "https://www.tiktok.com",
    "reddit": "https://www.reddit.com",
    "linkedin": "https://www.linkedin.com",
    "whatsapp": "https://web.whatsapp.com",
    "telegram": "https://web.telegram.org",
    "discord": "https://discord.com/app",
    "amazon": "https://www.amazon.com",
    "mercadolibre": "https://www.mercadolibre.com",
    "outlook": "https://outlook.live.com",
    "hotmail": "https://outlook.live.com",
    "notion": "https://www.notion.so",
    "trello": "https://trello.com",
    "figma": "https://www.figma.com",
    "canva": "https://www.canva.com",
    "duolingo": "https://www.duolingo.com",
}

#: Verbos de apertura/ejecución admitidos (texto ya sin tildes).
_OPEN_VERB = (
    r"(?:abre(?:me)?|abrir(?:me)?|abri(?:me)?|abras|abra|habre|habrir|ve\s+a|entra\s+(?:a|en)|"
    r"navega\s+(?:a|hacia)|lanza|inicia(?:me)?|arranca|ejecuta|visita|llevame\s+a|"
    r"pon(?:me)?|pones|poner(?:me)?|pongas|ponga|enciende|activa|quiero\s+(?:ver|abrir|entrar\s+a)|"
    r"muestrame|open|launch|go\s+to)"
)

_FILLER_PREFIXES = (
    "la pagina web de", "la pagina web", "la pagina de", "la pagina", "el sitio web de",
    "el sitio web", "el sitio de", "el sitio", "la web de", "la web", "el programa",
    "la aplicacion", "la app", "el app", "la carpeta", "el archivo", "el documento",
    "la", "el", "los", "las", "mi", "mis", "un", "una", "al", "a",
)

#: Cortesía y rodeos con los que se envuelve una orden.  Si la frase entera no
#: encaja en ninguna regla, se quita esto y se vuelve a intentar: «¿me puedes abrir
#: YouTube?» tiene que valer exactamente igual que «abre YouTube».
_PREAMBLE = re.compile(
    r"^(?:"
    r"(?:oye|okey|ok|okay|hey|mira|escucha|bueno|pues|eh+|a\s+ver|venga|dale|y|e|o)\b[\s,]*|"
    r"(?:me\s+|nos\s+)?(?:puedes|podrias|podras|puede|podria|pudieras|podes|sabes)\s+|"
    r"(?:quiero|necesito|quisiera|deseo|me\s+gustaria|me\s+interesa)\s+que\s+(?:me\s+)?|"
    r"(?:quiero|necesito|quisiera|deseo)\s+|"
    r"(?:haz(?:me)?\s+el\s+favor\s+de|ayudame\s+a|porfa(?:vor)?|por\s+favor|please|"
    r"can\s+you|could\s+you|would\s+you|i\s+want\s+(?:to|you\s+to))\s+"
    r")+"
)

#: Con cualquiera de estas palabras NO se rescata la frase: el usuario niega o pide
#: cerrar algo, no abrirlo.
_NEGATION_RE = re.compile(
    r"\b(?:no|nunca|jamas|tampoco|cierra|cerrar|apaga|apagar|quita|quitar|deja|dejes|"
    r"para|parar|detiene|detener|cancela|cancelar|minimiza|callate|silencio)\b"
)

_TRAILING_NOISE = re.compile(
    r"(?:\s+(?:por\s+favor|porfavor|please|gracias|ya|ahora|ahorita))+[\s.!?]*$", re.IGNORECASE
)

#: Herramientas que pueden combinarse en una sola frase ("abre youtube y spotify").
_MULTI_SAFE_TOOLS = frozenset(
    {
        "open_url",
        "web_search",
        "open_application",
        "open_folder",
        "list_files",
        "get_system_info",
        "get_memory_usage",
        "get_disk_usage",
        "get_running_processes",
        "get_datetime",
        "media_control",
        "get_news",
        "play_media",
    }
)

#: Órdenes de reproducción y volumen -> acción fija de ``media_control``.  Van
#: ancladas al final de la frase a propósito: «sube» es volumen, «sube el archivo a
#: Drive» no es nada que exista aquí y no debe tocar el volumen por descuido.
_MEDIA_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "volume_up",
        re.compile(
            r"^(?:sube|subele|subeme|subir|aumenta|incrementa)"
            r"(?:\s+(?:un\s+poco|bastante|mas))?(?:\s+(?:el|la))?"
            r"(?:\s+(?:volumen|sonido|audio|musica))?$"
        ),
    ),
    (
        "volume_down",
        re.compile(
            r"^(?:baja|bajale|bajame|bajar|reduce|disminuye)"
            r"(?:\s+(?:un\s+poco|bastante|mas))?(?:\s+(?:el|la))?"
            r"(?:\s+(?:volumen|sonido|audio|musica))?$"
        ),
    ),
    (
        "mute",
        re.compile(
            r"^(?:silencia(?:lo|la|me)?|mutea(?:lo)?|silencio|"
            r"quita(?:le)?\s+el\s+(?:sonido|volumen|audio))$"
        ),
    ),
    (
        "next",
        re.compile(
            r"^(?:siguiente|proxima|pasa\s+de|salta|next)"
            r"(?:\s+(?:la\s+)?(?:cancion|pista|tema|video|musica))?$"
        ),
    ),
    (
        "previous",
        re.compile(
            r"^(?:(?:anterior|previa|vuelve|regresa|atras|back)"
            r"(?:\s+(?:a\s+la\s+)?(?:la\s+)?(?:cancion|pista|tema|anterior))?"
            r"|(?:la\s+)?(?:cancion|pista|tema)\s+(?:anterior|previa|de\s+antes))$"
        ),
    ),
    (
        "play_pause",
        re.compile(
            r"^(?:pausa(?:lo|la)?|pausar|pause|play|para(?:la|lo)?|detente|"
            r"pon\s+pausa|reanuda(?:lo|la)?|continua|sigue)"
            r"(?:\s+(?:la|el))?(?:\s+(?:musica|cancion|video|reproduccion|audio))?$"
        ),
    ),
)

#: «pon música» sin decir dónde: con una tecla de play no pasaría nada visible, así
#: que se abre el reproductor.
_MUSIC_START = re.compile(
    r"^(?:pon(?:me|le)?|poner|reproduce(?:me)?|reproducir|echa|dale\s+a)"
    r"(?:\s+(?:algo\s+de|un\s+poco\s+de|la|el))?\s+(?:musica|cancion(?:es)?)$"
)

#: Reglas que se buscan en cualquier parte de la frase, no solo al principio:
#: «y de paso dime cuanta memoria tengo» sigue siendo una consulta de memoria.
_SEARCH_ANYWHERE = frozenset({"system", "datetime", "news"})

_SPLIT_RE = re.compile(r"\s+y\s+(?:luego\s+|despues\s+|tambien\s+)?|\s*;\s*|\s+luego\s+|\s+despues\s+")

#: Palabras que no nombran a nadie: «pon música» no es buscar «música».
_GENERIC_MUSIC = frozenset(
    {"musica", "cancion", "canciones", "musiquita", "algo", "algo de musica", "temas", "playlist"}
)

#: Palabras que, solas o combinadas, NO son un tema: «noticias de hoy en mi país»
#: sigue siendo la portada de siempre, no una búsqueda de «hoy en mi país».
_NEWS_STOPWORDS = frozenset(
    {
        "hoy", "ahora", "dia", "dias", "momento", "ultima", "ultimo", "ultimas", "ultimos",
        "hora", "horas", "actualidad", "peru", "pais", "mi", "mis", "aqui", "siempre",
        "semana", "mundo", "todo", "toda", "todos", "todas", "el", "la", "los", "las",
        "en", "de", "del", "un", "una", "importante", "importantes", "general", "generales",
        "ahorita", "reciente", "recientes", "nuevo", "nuevas", "nuevos", "nueva",
    }
)


def _news_topic_is_generic(topic: str) -> bool:
    """¿Todo lo que dijo son muletillas de tiempo y lugar?  Entonces no hay tema."""

    words = normalize(topic).split()
    return not words or all(word in _NEWS_STOPWORDS for word in words)

#: «noticias de economia» → el diario economico, no una búsqueda por tema.
_NEWS_SOURCES = {
    "economia": "gestion",
    "negocios": "gestion",
    "finanzas": "gestion",
    "rpp": "rpp",
    "el comercio": "comercio",
    "comercio": "comercio",
    "gestion": "gestion",
}

#: Sustantivos que nombran la CLASE de cosa, no la cosa: si el objetivo se queda en
#: uno de estos, el usuario no ha dicho todavia qué quiere abrir.
_GENERIC_NOUNS = frozenset(
    {
        "carpeta", "carpetas", "directorio", "folder", "archivo", "archivos",
        "documento", "documentos", "fichero", "pagina", "web", "sitio", "url",
        "aplicacion", "programa", "app", "cosa", "eso", "esto", "algo",
    }
)

#: Palabras que son objetivo y palabra corriente a la vez: no sirven para rescatar
#: una frase (``"abre el correo"`` ya lo resuelven las reglas normales).
_SALVAGE_STOPWORDS = frozenset({"correo", "calendar", "maps", "drive", "notas", "camara"})


def _build_salvage_keys() -> tuple[str, ...]:
    """Nombres distintivos que se pueden reconocer dentro de una frase destrozada.

    Solo objetivos de riesgo bajo: rescatar a ciegas nunca debe acabar abriendo una
    consola del sistema.
    """

    names = {key for key in SITES if len(key) >= 5}
    for spec in APPLICATIONS:
        if spec.risk_level is not RiskLevel.LOW:
            continue
        names.update(normalize(name) for name in spec.all_names() if len(name) >= 5)
    return tuple(sorted(names - _SALVAGE_STOPWORDS, key=len, reverse=True))


_SALVAGE_KEYS = _build_salvage_keys()

_URL_RE = re.compile(r"^(?:https?://)[^\s]+$", re.IGNORECASE)
_BARE_DOMAIN_RE = re.compile(r"^(?:www\.)?[a-z0-9][a-z0-9\-]*(?:\.[a-z0-9\-]+)+(?:/[^\s]*)?$", re.IGNORECASE)
_FILENAME_RE = re.compile(r"^[^\\/:*?\"<>|]+\.[a-z0-9*?]{1,8}$", re.IGNORECASE)


def _clean(value: str) -> str:
    """Quita ruido de cortesía, comillas y artículos iniciales."""

    text = _TRAILING_NOISE.sub("", value).strip()
    text = text.strip("¿?¡!.,;:").strip()
    text = text.strip('"').strip("'").strip("«»").strip()
    lowered = fold(text)
    for prefix in _FILLER_PREFIXES:
        if lowered.startswith(prefix + " "):
            text = text[len(prefix) + 1 :].strip()
            lowered = fold(text)
    return text.strip()


def _is_folder_alias(value: str) -> bool:
    return normalize(value) in FOLDER_ALIASES


def _looks_like_path(value: str) -> bool:
    if any(separator in value for separator in ("\\", "/")):
        return True
    if value.startswith("~") or re.match(r"^[a-zA-Z]:", value):
        return True
    return _is_folder_alias(value)


def _resolve_site(value: str) -> str | None:
    """Convierte ``"youtube"`` / ``"youtube.com"`` en una URL, o ``None``."""

    cleaned = _clean(value)
    if not cleaned:
        return None
    key = normalize(cleaned)
    if key in SITES:
        return SITES[key]
    if _URL_RE.match(cleaned):
        return cleaned
    if _BARE_DOMAIN_RE.match(cleaned):
        return cleaned if cleaned.lower().startswith("http") else f"https://{cleaned}"
    return None


class RuleBasedIntentParser:
    """Intérprete determinista basado en patrones.  Sin IA, sin red."""

    source = "rules"

    def __init__(self) -> None:
        self._rules: tuple[tuple[str, re.Pattern[str], Callable[[re.Match[str], str], IntentResult | None]], ...] = (
            ("web_search", re.compile(r"^(?:busca(?:me)?|buscar|busques?|buscas|investiga)\s+(?:informacion|info|datos)\s+(?:sobre|de|acerca\s+de)\s+(?P<query>.+)$"), self._rule_web_search),
            ("web_search", re.compile(r"^(?:busca(?:me)?|buscar|busques?|buscas|investiga)\s+(?:en\s+(?:internet|google|la\s+web|el\s+navegador|bing|duckduckgo))\s+(?P<query>.+)$"), self._rule_web_search),
            ("web_search", re.compile(r"^(?:busca(?:me)?|buscar|busques?|buscas|investiga)\s+(?P<query>.+?)\s+en\s+(?:internet|google|la\s+web|el\s+navegador|bing|duckduckgo)\s*$"), self._rule_web_search),
            ("web_search", re.compile(r"^(?:googlea(?:me)?|search(?:\s+for)?)\s+(?P<query>.+)$"), self._rule_web_search),
            ("search_files", re.compile(r"^(?:busca(?:me)?|buscar|busques?|buscas|encuentra|localiza|find)\s+(?:(?:el|los|la|las|un|una|mis?)\s+)?(?:archivos?|documentos?|ficheros?|carpetas?)\s+(?:llamad[oa]s?\s+|con\s+nombre\s+|que\s+se\s+llamen?\s+)?(?P<query>.+?)(?:\s+en\s+(?P<root>.+?))?\s*$"), self._rule_search_files),
            ("search_files", re.compile(r"^(?:busca(?:me)?|buscar|busques?|buscas|encuentra|localiza)\s+(?P<query>[^\s]+\.[a-z0-9*?]{1,8})(?:\s+en\s+(?P<root>.+?))?\s*$"), self._rule_search_files),
            ("create_folder", re.compile(r"^(?:crea(?:me)?|crear|haz(?:me)?|nueva|new)\s+(?:una?\s+)?(?:carpeta|directorio|folder)\s+(?:llamad[oa]\s+|con\s+(?:el\s+)?nombre\s+|de\s+nombre\s+|que\s+se\s+llame\s+)?(?P<name>.+?)(?:\s+(?:en|dentro\s+de|adentro\s+de)\s+(?P<where>.+?))?\s*$"), self._rule_create_folder),
            ("rename_file", re.compile(r"^(?:renombra(?:me)?|renombrar|cambia(?:le)?\s+(?:el\s+)?nombre\s+(?:de|a)|cambiar\s+(?:el\s+)?nombre\s+de)\s+(?:(?:el|la|los|las)\s+)?(?:archivo\s+|carpeta\s+|documento\s+)?(?P<source>.+?)\s+(?:a|por|como)\s+(?P<new_name>.+?)\s*$"), self._rule_rename_file),
            ("move_file", re.compile(r"^(?:mueve(?:me)?|mover|traslada|move)\s+(?:(?:el|la|los|las)\s+)?(?:archivo\s+|carpeta\s+|documento\s+)?(?P<source>.+?)\s+(?:a|hacia|hasta|al)\s+(?P<destination>.+?)\s*$"), self._rule_move_file),
            ("copy_file", re.compile(r"^(?:copia(?:me)?|copiar|duplica|copy)\s+(?:(?:el|la|los|las)\s+)?(?:archivo\s+|carpeta\s+|documento\s+)?(?P<source>.+?)\s+(?:a|hacia|hasta|al|en)\s+(?P<destination>.+?)\s*$"), self._rule_copy_file),
            ("list_files", re.compile(r"^(?:lista(?:me)?|listar|muestra(?:me)?|ensename|ver|dime)\s+(?:(?:los|las|el|la)\s+)?(?:archivos?|elementos|contenido|documentos?|carpetas?)\s+(?:de|en|dentro\s+de)\s+(?P<path>.+?)\s*$"), self._rule_list_files),
            ("list_files", re.compile(r"^(?:que\s+(?:hay|tengo)\s+(?:en|dentro\s+de)|contenido\s+de|ls)\s+(?P<path>.+?)\s*$"), self._rule_list_files),
            ("news", re.compile(r"\b(?:noticias?|titulares|actualidad)\b"), self._rule_news),
            ("play_media", re.compile(
                r"^(?:pon(?:me|le)?|poner|reproduce(?:me)?|reproducir|echa(?:me)?|"
                r"quiero\s+(?:escuchar|oir)|escuchar|play)\s+(?P<rest>.+)$"), self._rule_play_media),
            ("media", re.compile(r"^(?P<phrase>.{2,60})$"), self._rule_media),
            ("datetime", re.compile(
                r"\b(?:que|cual)\s+(?:hora|dias?|fecha)\b"
                r"|\b(?:hora|fecha)\s+(?:es|tenemos|actual|de\s+hoy)\b"
                r"|\b(?:dime|dame|sabes|recuerdame)\s+(?:la\s+|el\s+)?(?:hora|fecha|dias?)\b"
                r"|\b(?:dias?|fecha)\s+(?:es\s+)?hoy\b"
                r"|\b(?:que|en\s+que)\s+dias?\s+estamos\b"
                r"|\bhora\s+(?:es|actual)\b"
                r"|\bwhat\s+time\b"
            ), self._rule_datetime),
            ("system", re.compile(r"(?P<topic>\b(?:memoria|ram|disco|espacio|almacenamiento|procesos|tareas|sistema|equipo|pc|computadora|ordenador|maquina|cpu)\b)"), self._rule_system),
            ("open_folder", re.compile(rf"^{_OPEN_VERB}\s+(?:(?:la|el|mi|los|las)\s+)?(?:carpeta|directorio|folder)\s+(?:de\s+)?(?P<path>.+?)\s*$"), self._rule_open_folder),
            ("open_file", re.compile(rf"^{_OPEN_VERB}\s+(?:(?:el|la|mi)\s+)?(?:archivo|documento|fichero|file)\s+(?P<path>.+?)\s*$"), self._rule_open_file),
            ("open_target", re.compile(rf"^{_OPEN_VERB}\s+(?P<target>.+?)\s*$"), self._rule_open_target),
            ("bare_target", re.compile(r"^(?P<target>[a-z0-9 ._\-]{2,40})$"), self._rule_bare_target),
            ("smalltalk", re.compile(
                r"^(?:hola|holas|buenas|buenos\s+dias|buenas\s+(?:tardes|noches)|hey|hi|hello|"
                r"que\s+tal|quien\s+eres|quien\s+sos|como\s+(?:estas|te\s+llamas)|ayuda|help|"
                r"que\s+(?:puedes|puedo|podemos|sabes|saves)\s+(?:hacer|decir)|que\s+haces|"
                r"para\s+que\s+sirves|me\s+escuchas|me\s+oyes|estas\s+(?:ahi|despiert[oa]|activ[oa])|"
                r"gracias|thanks|thank\s+you)\b"), self._rule_smalltalk),
        )

    # ------------------------------------------------------------------
    def parse(self, message: str) -> IntentResult:
        original = (message or "").strip()
        if not original:
            return IntentResult(
                reply="No recibí ningún mensaje. ¿Qué quieres que haga?",
                confidence=0.0,
                source=self.source,
                needs_clarification=True,
                matched_rule="empty",
            )

        combined = self._parse_multi(original)
        if combined is not None:
            return combined
        return self._parse_single(original)

    # ------------------------------------------------------------------
    def _parse_multi(self, message: str) -> IntentResult | None:
        segments = [segment.strip() for segment in _SPLIT_RE.split(fold(message)) if segment.strip()]
        if len(segments) < 2 or len(segments) > 4:
            return None
        # Se reparsea sobre el texto original recortado por longitudes equivalentes:
        # trabajar con el texto plegado es suficiente para estas intenciones simples.
        results = [self._parse_single(segment) for segment in segments]
        actions: list[ToolCall] = []
        for result in results:
            actions.extend(result.actions)
        if len(actions) < 2 or not all(action.tool in _MULTI_SAFE_TOOLS for action in actions):
            return None
        return IntentResult(
            reply="",
            actions=actions,
            confidence=min(result.confidence for result in results if result.actions),
            source=self.source,
            matched_rule="multi",
        )

    def _parse_single(self, message: str) -> IntentResult:
        # Se recorta el texto ORIGINAL y solo después se pliega, de modo que ambos
        # tengan exactamente la misma longitud y los índices de las coincidencias
        # sirvan para recortar el original (ver ``_slice``).
        cleaned = _TRAILING_NOISE.sub("", message).strip()
        cleaned = re.sub(r"^(?:oye|ok|okay|hey|por\s+favor|porfa)[\s,]+", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip("¿?¡!.,;: ").strip()

        result = self._match_rules(cleaned)
        if result is not None:
            return result

        # Segundo intento sin cortesía: nadie da órdenes secas al hablar.  Se recorta
        # sobre el texto original para que ``_slice`` siga cuadrando índice a índice.
        preamble = _PREAMBLE.match(fold(cleaned))
        if preamble is not None and preamble.end() < len(cleaned):
            shorter = cleaned[preamble.end() :].strip("¿?¡!.,;: ").strip()
            if shorter:
                result = self._match_rules(shorter)
                if result is not None:
                    return result
                cleaned = shorter

        # Tercer intento: el reconocedor de voz rompió el verbo pero el nombre propio
        # sobrevivió («pueden saber youtube»).  Mejor abrir lo evidente que callar.
        result = self._salvage(cleaned)
        if result is not None:
            return result

        # Nada encajó: se explica QUÉ falló, no «no te entendí».
        return self._diagnose(cleaned)

    # ------------------------------------------------------------------
    def _diagnose(self, cleaned: str) -> IntentResult:
        """Convierte un fallo de interpretación en una respuesta concreta.

        Decir «no te entendí» no ayuda a nadie: si se reconoció el verbo pero no el
        objeto, lo útil es nombrar el objeto que no se reconoce y decir qué haría
        falta para ejecutarlo.
        """

        folded = fold(cleaned)

        def answer(reply: str, rule: str) -> IntentResult:
            return IntentResult(
                reply=reply,
                confidence=0.0,
                source=self.source,
                needs_clarification=True,
                matched_rule=f"unresolved:{rule}",
            )

        verb = re.match(rf"^{_OPEN_VERB}\s+(?P<target>.+)$", folded)
        if verb is not None:
            target = _clean(self._slice(verb, "target", cleaned))
            # «abre la carpeta» deja «carpeta» como objetivo: eso no es un nombre.
            if normalize(target) in _GENERIC_NOUNS:
                target = ""
            if re.search(r"\b(?:carpeta|directorio|folder)\b", folded):
                if not target:
                    return answer(
                        "¿Qué carpeta quieres que abra? Puedo abrir tus carpetas "
                        "(Descargas, Documentos, Escritorio, Imágenes, Vídeos, Música) "
                        "o cualquier ruta dentro de tu usuario.",
                        "folder",
                    )
                return answer(
                    f"No encuentro la carpeta «{target}». Puedo abrir tus carpetas "
                    f"(Descargas, Documentos, Escritorio, Imágenes, Vídeos, Música) o una "
                    f"ruta completa; fuera de tu usuario no tengo permiso para entrar.",
                    "folder",
                )
            if re.search(r"\b(?:archivo|documento|fichero)\b", folded):
                if not target:
                    return answer(
                        "¿Qué archivo quieres que abra? Dime el nombre con su extensión "
                        "y lo busco.",
                        "file",
                    )
                return answer(
                    f"No encuentro el archivo «{target}». Dime el nombre con su extensión "
                    f"y lo busco, o dame la ruta completa.",
                    "file",
                )
            if re.search(r"\b(?:pagina|web|sitio|url)\b", folded):
                return answer(
                    f"No sé qué página es «{target or 'esa'}». Dime la dirección completa "
                    f"y la abro.",
                    "url",
                )
            return answer(
                f"Entendí que quieres abrir «{target or 'algo'}», pero no sé qué es: no es "
                f"una web que conozca, ni una aplicación de mi catálogo, ni una de tus "
                f"carpetas.",
                "target",
            )

        if re.match(r"^(?:mueve|mover|copia|copiar|renombra|renombrar|traslada)\b", folded):
            return answer(
                "Para mover, copiar o renombrar necesito la ruta del origen y el destino. "
                "Por ejemplo: «mueve Descargas/foto.png a Imágenes».",
                "path_needed",
            )

        if re.match(r"^(?:crea|crear|haz|hazme|nueva|nuevo)\b", folded):
            return answer(
                "Puedo crear carpetas. Dime cómo la llamo y dónde: «crea una carpeta "
                "llamada Facturas en Documentos».",
                "create",
            )

        if re.match(r"^(?:borra|borrar|elimina|eliminar|manda\s+a\s+la\s+papelera)\b", folded):
            return answer(
                "No borro nada: la herramienta de borrado está deshabilitada a propósito. "
                "Puedo abrirte la carpeta para que lo hagas tú.",
                "delete",
            )

        if re.match(
            r"^(?:apaga|reinicia|cierra|mata|instala|desinstala|actualiza|configura|"
            r"cambia\s+(?:el|la)\s+(?:fondo|tema|contrasena))\b",
            folded,
        ):
            return answer(
                "Eso no lo puedo hacer: no tengo herramientas para apagar, cerrar programas "
                "ni instalar cosas. Solo hago lo que aparece en mi lista de herramientas.",
                "no_tool",
            )

        if len(folded.split()) <= 2:
            return answer(
                f"Solo entendí «{cleaned}». ¿Me lo dices con la acción completa? "
                f"Por ejemplo «abre YouTube» o «cuánta memoria tengo».",
                "too_short",
            )

        return answer(
            f"No sé qué hacer con «{cleaned}». Puedo abrir aplicaciones y páginas web, "
            f"abrir, buscar y organizar archivos, crear carpetas, controlar el volumen y "
            f"contarte cómo va el equipo.",
            "unknown",
        )

    def _match_rules(self, cleaned: str) -> IntentResult | None:
        """Pasa el texto por todas las reglas.  ``None`` si ninguna encaja."""

        folded = fold(cleaned)
        for name, pattern, handler in self._rules:
            # Las consultas (estado, hora) se buscan en cualquier posición de la frase;
            # las órdenes se anclan al principio para no disparar por una palabra suelta.
            search = name in _SEARCH_ANYWHERE
            match = pattern.search(folded) if search else pattern.match(folded)
            if match is None:
                continue
            result = handler(match, cleaned)
            if result is not None:
                return result
        return None

    def _salvage(self, cleaned: str) -> IntentResult | None:
        """Rescata la intención cuando solo se entendió el nombre del objetivo.

        El reconocedor de voz destroza los verbos («puedes abrir» -> «pueden saber»)
        pero los nombres propios aguantan porque son sonidos poco comunes.  Con una
        frase corta, sin negaciones y con un único objetivo conocido, abrirlo acierta
        muchísimo más veces de las que falla.
        """

        folded = fold(cleaned)
        words = folded.split()
        if not 1 <= len(words) <= 6 or _NEGATION_RE.search(folded):
            return None

        hits = [key for key in _SALVAGE_KEYS if re.search(rf"\b{re.escape(key)}\b", folded)]
        # "google drive" y "drive" son el mismo objetivo: cuentan como uno.
        unique = [key for key in hits if not any(key != other and key in other for other in hits)]
        if len(unique) != 1:
            return None
        return self._resolve_open_target(
            unique[0], rule="salvage", confidence_penalty=0.35, allow_risky=False
        )

    # ------------------------------------------------------------------
    # reglas
    # ------------------------------------------------------------------
    def _rule_web_search(self, match: re.Match[str], original: str) -> IntentResult | None:
        query = self._slice(match, "query", original)
        query = _clean(query)
        if len(query) < 2:
            return None
        return self._single_action(
            "web_search", {"query": query}, rule="web_search", confidence=0.8,
            reason="El usuario pidió una búsqueda en internet.",
        )

    def _rule_search_files(self, match: re.Match[str], original: str) -> IntentResult | None:
        query = _clean(self._slice(match, "query", original))
        if len(query) < 2:
            return None
        arguments: dict[str, Any] = {"query": query}
        root = self._slice(match, "root", original)
        if root:
            root = _clean(root)
            if root:
                arguments["root_path"] = root
        return self._single_action(
            "search_files", arguments, rule="search_files", confidence=0.75,
            reason="El usuario pidió localizar archivos por nombre.",
        )

    def _rule_create_folder(self, match: re.Match[str], original: str) -> IntentResult | None:
        name = _clean(self._slice(match, "name", original))
        if not name:
            return None
        where = _clean(self._slice(match, "where", original) or "")
        base = where or "Documentos"
        path = f"{base}\\{name}" if not _looks_like_path(name) else name
        return self._single_action(
            "create_folder", {"path": path}, rule="create_folder", confidence=0.75,
            reason=f"Crear la carpeta «{name}»" + (f" dentro de {base}." if not where else "."),
        )

    def _rule_move_file(self, match: re.Match[str], original: str) -> IntentResult | None:
        source = _clean(self._slice(match, "source", original))
        destination = _clean(self._slice(match, "destination", original))
        if not source or not destination or not _looks_like_path(source):
            return None
        return self._single_action(
            "move_file", {"source": source, "destination": destination},
            rule="move_file", confidence=0.7, reason="Mover un archivo o carpeta.",
        )

    def _rule_copy_file(self, match: re.Match[str], original: str) -> IntentResult | None:
        source = _clean(self._slice(match, "source", original))
        destination = _clean(self._slice(match, "destination", original))
        if not source or not destination or not _looks_like_path(source):
            return None
        return self._single_action(
            "copy_file", {"source": source, "destination": destination},
            rule="copy_file", confidence=0.7, reason="Copiar un archivo o carpeta.",
        )

    def _rule_rename_file(self, match: re.Match[str], original: str) -> IntentResult | None:
        source = _clean(self._slice(match, "source", original))
        new_name = _clean(self._slice(match, "new_name", original))
        if not source or not new_name or not _looks_like_path(source):
            return None
        return self._single_action(
            "rename_file", {"source": source, "new_name": new_name},
            rule="rename_file", confidence=0.7, reason="Renombrar un archivo o carpeta.",
        )

    def _rule_list_files(self, match: re.Match[str], original: str) -> IntentResult | None:
        path = _clean(self._slice(match, "path", original))
        if not path or not _looks_like_path(path):
            return None
        return self._single_action(
            "list_files", {"path": path}, rule="list_files", confidence=0.75,
            reason="Listar el contenido de una carpeta.",
        )

    def _rule_news(self, match: re.Match[str], original: str) -> IntentResult | None:
        """«cuéntame las noticias», «noticias de economía», «qué titulares hay»."""

        folded = fold(original)
        arguments: dict[str, Any] = {}
        tema = re.search(
            r"\b(?:noticias?|titulares|actualidad)\s+(?:de|del|de\s+la|sobre|acerca\s+de)\s+"
            r"(?P<topic>.+?)\s*$",
            folded,
        )
        if tema is not None:
            topic = _clean(self._slice(tema, "topic", original))
            # «noticias de hoy» o «noticias del Perú» no son temas: son la portada.
            if _news_topic_is_generic(topic):
                topic = ""
            if normalize(topic) in _NEWS_SOURCES:
                arguments["source"] = _NEWS_SOURCES[normalize(topic)]
            elif topic:
                arguments["topic"] = topic
        return self._single_action(
            "get_news", arguments, rule="news", confidence=0.8,
            reason="El usuario pidió titulares de prensa.",
        )

    def _rule_play_media(self, match: re.Match[str], original: str) -> IntentResult | None:
        """«reproduce Dominick Fike en Spotify», «pon Bad Bunny en YouTube»."""

        rest = _clean(self._slice(match, "rest", original))
        if not rest:
            return None
        service = ""
        lugar = re.search(
            r"\s+(?:en|por|con|desde)\s+(?P<service>spotify|spoti|youtube\s+music|"
            r"music\s+youtube|youtube|yt)\s*$",
            fold(rest),
        )
        if lugar is not None:
            service = normalize(lugar.group("service"))
            rest = _clean(rest[: lugar.start()])
        # «música de X» -> X.  Se recorta sobre el texto plegado para que la tilde de
        # «música» no rompa la coincidencia.
        prefijo = re.match(r"^(?:musica|cancion(?:es)?|algo|temas?)\s+(?:de|del|de\s+la)\s+", fold(rest))
        if prefijo is not None:
            rest = rest[prefijo.end() :]
        rest = _clean(rest)
        if len(rest) < 2:
            return None
        # «pon música» a secas no nombra nada: de eso se encarga la regla de medios,
        # que abre el reproductor en vez de buscar la palabra «música».
        if not service and normalize(rest) in _GENERIC_MUSIC:
            return None
        # «pon YouTube» a secas es abrir el sitio, no reproducir nada.
        if not service and _resolve_site(rest) is not None:
            return None
        arguments: dict[str, Any] = {"query": rest}
        if service:
            arguments["service"] = service
        return self._single_action(
            "play_media", arguments, rule="play_media", confidence=0.75,
            reason="El usuario pidió poner música o vídeo.",
        )

    def _rule_media(self, match: re.Match[str], original: str) -> IntentResult | None:
        """«pausa», «sube el volumen», «siguiente canción», «pon música»."""

        phrase = fold(original).strip()
        if _MUSIC_START.match(phrase):
            return self._single_action(
                "open_url", {"url": SITES["spotify"]}, rule="media:music",
                confidence=0.7, reason="Poner música: se abre el reproductor.",
            )
        for action, pattern in _MEDIA_PATTERNS:
            if pattern.match(phrase):
                return self._single_action(
                    "media_control", {"action": action}, rule=f"media:{action}",
                    confidence=0.8, reason="Control de reproducción o volumen.",
                )
        return None

    def _rule_datetime(self, match: re.Match[str], original: str) -> IntentResult | None:
        """«¿qué hora es?», «qué día es hoy».

        El patrón exige la forma de pregunta completa: hablar del «otro día» o de «la
        carpeta del día 3» no es preguntar la hora.
        """

        return self._single_action(
            "get_datetime", {}, rule="datetime", confidence=0.8,
            reason="Consulta de fecha y hora.",
        )

    def _rule_system(self, match: re.Match[str], original: str) -> IntentResult | None:
        folded = fold(original)
        if not re.search(
            r"\b(?:cuant[oa]s?|cuanta|cuenta(?:me)?|cuentas|estado|informacion|info|dame|"
            r"muestra(?:me)?|dime|ver|revisa|como\s+(?:esta|va|anda)|uso|usando|utilizando|"
            r"consumo|consumiendo|gastando|ocupando|libre|ocupad[oa]|disponible|tengo|tienes|"
            r"queda|quedan|nivel|porcentaje|especificaciones|caracteristicas|abiertos?|"
            r"corriendo|ejecucion|status|check)\b",
            folded,
        ):
            return None
        topic = match.group("topic")
        tool = {
            "memoria": "get_memory_usage",
            "ram": "get_memory_usage",
            "disco": "get_disk_usage",
            "espacio": "get_disk_usage",
            "almacenamiento": "get_disk_usage",
            "procesos": "get_running_processes",
            "tareas": "get_running_processes",
        }.get(topic, "get_system_info")
        return self._single_action(
            tool, {}, rule=f"system:{topic}", confidence=0.7,
            reason="Consulta de estado del sistema.",
        )

    def _rule_open_folder(self, match: re.Match[str], original: str) -> IntentResult | None:
        path = _clean(self._slice(match, "path", original))
        if not path:
            return None
        return self._single_action(
            "open_folder", {"path": path}, rule="open_folder", confidence=0.8,
            reason="Abrir una carpeta en el explorador.",
        )

    def _rule_open_file(self, match: re.Match[str], original: str) -> IntentResult | None:
        path = _clean(self._slice(match, "path", original))
        if not path:
            return None
        return self._single_action(
            "open_file", {"path": path}, rule="open_file", confidence=0.75,
            reason="Abrir un archivo con su aplicación asociada.",
        )

    def _rule_open_target(self, match: re.Match[str], original: str) -> IntentResult | None:
        target = _clean(self._slice(match, "target", original))
        return self._resolve_open_target(target, rule="open_target")

    def _rule_bare_target(self, match: re.Match[str], original: str) -> IntentResult | None:
        target = _clean(self._slice(match, "target", original))
        if len(target) < 2:
            return None
        return self._resolve_open_target(
            target, rule="bare_target", confidence_penalty=0.1, allow_risky=False
        )

    def _resolve_open_target(
        self,
        target: str,
        *,
        rule: str,
        confidence_penalty: float = 0.0,
        allow_risky: bool = True,
    ) -> IntentResult | None:
        if not target:
            return None

        # 1) sitio web conocido, URL o dominio explícito
        url = _resolve_site(target)
        if url is not None:
            return self._single_action(
                "open_url", {"url": url}, rule=f"{rule}:url",
                confidence=0.85 - confidence_penalty, reason=f"Abrir {url} en el navegador.",
            )

        # 2) carpeta conocida del usuario ("descargas", "escritorio")
        if _is_folder_alias(target):
            return self._single_action(
                "open_folder", {"path": target}, rule=f"{rule}:folder",
                confidence=0.8 - confidence_penalty, reason="Abrir una carpeta del usuario.",
            )

        # 3) aplicación del catálogo.  Sin un verbo explícito («abre la terminal») no
        # se propone nada que pese más que abrir la calculadora: una frase suelta mal
        # entendida no debe acabar ofreciendo una consola del sistema.
        app = find_app(target)
        if app is not None:
            if not allow_risky and app.risk_level is not RiskLevel.LOW:
                return None
            return self._single_action(
                "open_application", {"app_name": app.key}, rule=f"{rule}:app",
                confidence=0.85 - confidence_penalty,
                reason=f"Abrir {app.display_name}.",
            )

        # 4) ruta explícita o archivo con extensión
        if _looks_like_path(target):
            return self._single_action(
                "open_folder", {"path": target}, rule=f"{rule}:path",
                confidence=0.6 - confidence_penalty, reason="Abrir una ruta del sistema.",
            )
        if _FILENAME_RE.match(target):
            return self._single_action(
                "search_files", {"query": target}, rule=f"{rule}:search",
                confidence=0.5 - confidence_penalty,
                reason="No sé dónde está el archivo: primero lo busco.",
            )
        return None

    def _rule_smalltalk(self, match: re.Match[str], original: str) -> IntentResult:
        folded = fold(original)
        if re.match(r"^(?:gracias|thanks|thank\s+you)", folded):
            reply = "A tu orden. Sigo aquí si necesitas algo más."
        elif re.match(r"^(?:me\s+(?:escuchas|oyes)|estas\s+(?:ahi|despiert|activ))", folded):
            reply = "Aquí estoy, te escucho. Dime qué necesitas."
        else:
            reply = (
                "Estoy en línea. Puedo abrir aplicaciones y páginas web, abrir y buscar archivos, "
                "listar carpetas, crear carpetas, mover, copiar o renombrar archivos y contarte "
                "cómo va el sistema. Dime qué necesitas."
            )
        return IntentResult(
            reply=reply,
            confidence=0.9,
            source=self.source,
            matched_rule="smalltalk",
        )

    # ------------------------------------------------------------------
    # utilidades
    # ------------------------------------------------------------------
    @staticmethod
    def _slice(match: re.Match[str], group: str, original: str) -> str:
        """Recorta el texto ORIGINAL usando los índices del texto plegado.

        ``fold`` conserva la longitud, así que los índices son intercambiables y se
        preservan tildes y mayúsculas del usuario (nombres de carpeta, por ejemplo).
        """

        try:
            start, end = match.span(group)
        except (IndexError, KeyError):  # pragma: no cover - los grupos están declarados
            return ""
        if start < 0:
            return ""
        if len(original) >= end:
            return original[start:end]
        return match.group(group) or ""

    def _single_action(
        self,
        tool: str,
        arguments: dict[str, Any],
        *,
        rule: str,
        confidence: float,
        reason: str = "",
    ) -> IntentResult:
        return IntentResult(
            reply="",
            actions=[ToolCall(tool=tool, arguments=arguments, reason=reason)],
            confidence=confidence,
            source=self.source,
            matched_rule=rule,
        )


class IntentParser:
    """Fachada: usa el proveedor configurado y cae a reglas si algo falla."""

    def __init__(self, provider: AIProvider, registry: ToolRegistry) -> None:
        self._provider = provider
        self._registry = registry
        self._fallback = RuleBasedIntentParser()

    @property
    def provider(self) -> AIProvider:
        return self._provider

    async def parse(
        self, message: str, *, assistant: str, history: Sequence[ChatTurn] = ()
    ) -> IntentResult:
        try:
            intent = await self._provider.parse_intent(
                message, assistant=assistant, registry=self._registry, history=history
            )
        except AIProviderError as exc:
            logger.warning("Proveedor '%s' no disponible (%s). Uso reglas locales.", self._provider.name, exc)
            intent = self._fallback.parse(message)
            intent.source = f"{intent.source}:fallback"
            return intent

        # El proveedor puede proponer herramientas inexistentes: se filtran aquí,
        # antes de que el Planner las vea.
        valid: list[ToolCall] = []
        for action in intent.actions:
            if action.tool in self._registry:
                valid.append(action)
            else:
                logger.warning("El proveedor propuso una herramienta desconocida: %s", action.tool)
        intent.actions = valid
        return intent
