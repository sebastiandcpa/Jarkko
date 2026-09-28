# JARKKO · Backend

Backend del asistente inteligente de escritorio para Windows (proyecto *JARVIS - EKKO*).
Python 3.12 · FastAPI · Uvicorn · Pydantic · psutil · SQLite.

**JARKKO** es la fusión de JARVIS y EKKO: un solo motor, una sola personalidad, un
solo modelo. Los nombres `jarvis` y `ekko` se siguen aceptando como alias en la API
para no romper nada, pero resuelven siempre a JARKKO.

JARKKO **habla y escucha**, y ninguna de las dos cosas cuesta dinero
(ver [Voz](#voz) y [Escucha](#escucha)).
Y funciona **sin ninguna API de IA configurada** gracias al `MockAIProvider`.

---

## Principio de seguridad fundamental

> **El modelo de IA nunca tiene acceso a PowerShell, CMD ni al sistema operativo.**

La IA solo puede *solicitar* herramientas previamente registradas:

```json
{ "tool": "open_url", "arguments": { "url": "https://youtube.com" } }
```

Esa petición atraviesa siempre la misma cadena:

```
Usuario (texto o, en el futuro, voz)
  ↓
IA / IntentParser        app/agent/intent_parser.py   (MockAIProvider o proveedor externo)
  ↓
Planner                  app/agent/planner.py
  ↓
ToolSelector             app/agent/tool_selector.py   (nombre → herramienta registrada)
  ↓
Validator                app/security/validator.py    (tipos, rutas, URLs, existencia)
  ↓
Permission Manager       app/security/permissions.py  (política de riesgo)
  ↓
Tool Executor            app/agent/executor.py        (único punto que invoca handlers)
  ↓
Windows
  ↓
Verification             app/services/verification.py (¿ocurrió de verdad?)
  ↓
Resultado + Activity Log + eventos WebSocket + voz
```

Garantías concretas:

- **No existe** ninguna herramienta genérica tipo `run_command`, y no debe crearse.
- `subprocess` solo se invoca con rutas absolutas resueltas desde el
  *Application Registry* (`app/tools/applications/catalog.py`), sin `shell=True`
  y sin argumentos provenientes del modelo. La voz tampoco usa shell: los bindings
  WinRT van en proceso, así que el texto del asistente nunca llega a una línea de
  comandos.
- Las rutas se normalizan y deben quedar **dentro del home del usuario** (o de las
  raíces extra que se configuren explícitamente). Se rechazan rutas UNC, nombres
  de dispositivo reservados (`CON`, `NUL`, `COM1`…), directorios del sistema y
  carpetas sensibles (`.ssh`, `.aws`, almacenes de credenciales…).
- `open_file` **no abre ejecutables ni scripts** (`.exe`, `.bat`, `.ps1`, `.lnk`…):
  abrirlos equivale a ejecutar código.
- Nunca se sobrescribe un destino existente: se responde `conflict`.
- Las acciones de riesgo `high` exigen confirmación explícita del usuario;
  las `critical` están bloqueadas salvo activación explícita en la configuración.
- El registro de actividad sanea los argumentos: no guarda contraseñas, tokens ni
  API keys.

---

## Instalación

Requisitos: **Python 3.12+** y Windows 10/11.

```powershell
cd "C:\Users\<tu-usuario>\Desktop\Jarvis - Ekko\backend"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

El archivo `.env` ya existe con la configuración local (no se sube a git). Lo único
que falta por rellenar es `JARVIS_ELEVENLABS_API_KEY`, y es **opcional**.

---

## Ejecución

**Un solo ejecutable**: doble clic en `frontend/release/Jarkko/Jarkko.exe`.

La aplicación arranca este backend por su cuenta, sin ventana de consola, y lo
cierra al salir. Detalles de ese arranque (en `frontend/electron/main.cjs`):

- si el puerto 8765 ya responde, **reutiliza** ese backend y no lo mata al cerrar
  (así no estorba si lo tenías abierto a mano);
- si no, lanza `.venv\Scripts\python.exe -m uvicorn app.main:app` con la ventana
  oculta y vuelca su registro en `%TEMP%\jarkko-backend.log`;
- si falta la carpeta `backend` o su `.venv`, la app lo dice en un aviso en vez de
  quedarse muda;
- abrir el ejecutable dos veces **no** abre una segunda ventana: enfoca la que ya
  está.

Para depurar el backend solo, sin la aplicación:

```powershell
.\start-jarkko.ps1 -SoloBackend
```

A mano:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Equivalentes:

```powershell
python -m app.main                                            # usa JARVIS_HOST / JARVIS_PORT
uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload    # desarrollo
```

| Recurso | URL |
| --- | --- |
| API | `http://127.0.0.1:8765` |
| Documentación interactiva | `http://127.0.0.1:8765/docs` |
| Eventos en tiempo real | `ws://127.0.0.1:8765/ws/events` |

## Tests

```powershell
.\.venv\Scripts\Activate.ps1
pytest            # 151 tests
pytest tests/test_voice.py tests/test_listening.py -v
```

Los tests usan directorios y base de datos temporales, y **nunca** ejecutan acciones
peligrosas: de las herramientas que abren ventanas o el navegador solo se comprueban
los caminos de rechazo. La voz se sintetiza de verdad pero con la reproducción
desactivada, así que la suite es **silenciosa** y no gasta cuota.

---

## Voz

JARKKO tiene dos voces y una regla: **la de identidad no se paga dos veces**.

| Motor | Qué dice | Coste |
| --- | --- | --- |
| `elevenlabs` | Las frases fijas del catálogo, servidas **desde caché** | 0 € en marcha; ~2.000 caracteres una única vez al generar el caché |
| `windows` | Todo lo demás: cifras, rutas, texto libre | 0 €, offline, ilimitado (**Microsoft Raul**, es-MX, masculina) |

Claves del diseño:

1. **Lo hablado no es lo escrito.** En pantalla ves
   `Creé la carpeta C:\Users\...\Documents\Jarvis Test`; en voz oyes
   *«Carpeta creada y verificada»*. Esa frase corta es fija, así que se cachea y
   suena siempre con la voz de identidad sin gastar nada.
   Las herramientas informativas (`get_memory_usage`, `get_disk_usage`, …) son la
   excepción: ahí el dato **es** la respuesta, y se lee con la voz local.
2. **Protección de cuota en el código, no en la disciplina.** Con
   `JARVIS_ELEVENLABS_ALLOW_LIVE=false` (el valor por defecto) el motor de
   ElevenLabs solo devuelve audio que ya está en disco: es imposible gastar
   créditos por accidente. Generar el caché es una acción explícita.
3. **Nunca se queda mudo.** Si falta la clave, si la frase no está cacheada o si se
   agota la cuota, habla la voz local.
4. **Una locución a la vez.** Las frases se reproducen en cola; JARKKO no se habla
   encima.

### Activar su voz de identidad (opcional, gratis)

1. Pega tu API key de ElevenLabs en `backend/.env` → `JARVIS_ELEVENLABS_API_KEY=`.
   La clave solo se lee del entorno: no se registra en logs, ni en la base de datos,
   ni en el manifiesto del caché.
2. Asegúrate de que la voz está en **"My Voices"** de tu cuenta. Las voces de la
   Voice Library no funcionan por API hasta que las añades a tu espacio: si no,
   la API responde 404 (`/api/voice/status` te lo dice claramente).
3. Genera el caché **una sola vez**:

```powershell
python -m app.voice.build_cache --dry-run   # calcula el coste, no gasta nada
python -m app.voice.build_cache             # genera el caché de verdad
```

A partir de ahí el audio sale del disco. Si algún día añades frases nuevas al
catálogo (`app/voice/phrases.py`), vuelve a ejecutarlo: solo generará las que falten.

### Nota técnica

Las voces del motor moderno de Windows (WinRT) **no** aparecen en el SAPI clásico,
así que `pyttsx3` no ve a Raul (solo a Sabina, femenina). Por eso se usa `winsdk`
en proceso, que además evita pasar el texto del asistente por una línea de comandos.

---

## Escucha

Reconocimiento de voz **offline** con Vosk (`vosk-model-small-es-0.42`, 39 MB,
Apache 2.0): en CPU, sin GPU, sin coste y **sin que la voz salga del equipo**.

Manos libres: basta hablar empezando por la palabra clave.

```
«Jarkko, abre YouTube»
«Jarkko, crea una carpeta llamada Facturas en Documentos»
«Jarkko, cuánta memoria estoy usando»
```

Se enciende sola con el backend (`JARVIS_STT_AUTOSTART=true` en `.env`) o a mano:

```powershell
curl -X POST http://127.0.0.1:8765/api/voice/listen/start
curl -X POST http://127.0.0.1:8765/api/voice/listen/stop
curl http://127.0.0.1:8765/api/voice/listen/status
```

Decisiones importantes:

1. **La voz no da privilegios.** La orden hablada entra por el mismo camino que el
   texto escrito: intención → plan → Validator → Permission Manager → ejecución. Una
   acción de riesgo alto sigue pidiendo confirmación aunque se pida a gritos.
2. **Palabra clave tolerante.** El modelo no tiene «Jarkko» en su léxico y lo
   transcribe como «arco», «zarco», «jarco»… Se aceptan esas variantes (medidas en
   pruebas reales, no inventadas). Cambiable con `JARVIS_WAKE_WORD`.
3. **Sin eco.** Mientras JARKKO habla, el micrófono se ignora; si no, se oiría a sí
   mismo por los altavoces y se respondería solo.
4. **Discreción.** Si la palabra clave coincide de forma dudosa («marco polo») y la
   orden no se entiende, JARKKO se calla en lugar de contestar «no te entendí».
5. **Nada se guarda.** El audio se transcribe en memoria; no se escribe en disco ni
   se envía a ningún servidor.

### Si JARKKO no te oye

Windows entrega **silencio sin dar ningún error** cuando el micrófono está
silenciado. Para distinguirlo de un fallo del código:

```powershell
curl "http://127.0.0.1:8765/api/voice/microphone/test?seconds=2"
```

Devuelve el nivel medido y qué revisar. Comprobado en este equipo: los permisos de
privacidad de Windows están en «Permitir», pero **la entrada da silencio digital
(nivel 0.5)**, así que hay que desmutear el micrófono en Configuración → Sistema →
Sonido → Entrada, o con la tecla de función del portátil.

---

## Estructura

```
backend/
├── app/
│   ├── main.py                  FastAPI, CORS, lifespan, manejo de errores
│   ├── config.py                configuración por variables JARVIS_* / .env
│   ├── api/
│   │   ├── deps.py              dependencias inyectables
│   │   ├── websocket.py         /ws/events + broadcaster de system.status
│   │   └── routes/              health, system, tools, chat, actions, activity, files, voice
│   ├── agent/
│   │   ├── engine.py            orquestador (chat, ejecución directa, confirmaciones, voz)
│   │   ├── intent_parser.py     reglas ES/EN + fachada sobre el AIProvider
│   │   ├── planner.py           selección + validación + permisos → plan
│   │   ├── tool_selector.py     normalización de nombres/alias de herramientas
│   │   └── executor.py          ejecución, verificación, eventos y registro
│   ├── tools/
│   │   ├── base.py              ToolDefinition, ParameterSpec, ToolResult
│   │   ├── registry.py          registro central
│   │   ├── bootstrap.py         construcción del registro
│   │   ├── browser/             open_url, web_search
│   │   ├── applications/        catálogo de apps + open_application
│   │   ├── files/               list, search, open, create, move, copy, rename, (delete)
│   │   └── system/              info, memoria, disco, procesos
│   ├── voice/
│   │   ├── base.py              TTSProvider, SpeechPlan, SpeechAudio
│   │   ├── phrases.py           catálogo de frases fijas (lo que se cachea)
│   │   ├── windows_tts.py       voz local WinRT (gratis, offline, ilimitada)
│   │   ├── elevenlabs.py        voz de identidad, servida desde caché
│   │   ├── cache.py             caché en disco + manifiesto
│   │   ├── player.py            reproducción (winsound / MCI, sin dependencias)
│   │   ├── service.py           qué se dice, con qué motor y cuándo
│   │   ├── build_cache.py       CLI: genera el caché una sola vez
│   │   ├── recognizer.py        Vosk + palabra clave tolerante
│   │   ├── microphone.py        captura y diagnóstico del micrófono
│   │   └── listener.py          escucha manos libres (hilo dedicado)
│   ├── security/
│   │   ├── risk.py              RiskLevel: low | medium | high | critical
│   │   ├── validator.py         validación de argumentos, rutas y URLs
│   │   ├── permissions.py       política de confirmación y bloqueo
│   │   └── paths.py             carpetas del usuario (sin rutas hardcodeadas)
│   ├── providers/
│   │   ├── base.py              AIProvider, ToolCall, IntentResult
│   │   ├── mock.py              MockAIProvider (offline, determinista)
│   │   ├── external.py          OpenAI / Anthropic / Gemini (pendientes)
│   │   └── factory.py           selección + degradación a mock
│   ├── services/
│   │   ├── activity.py          registro en SQLite
│   │   ├── verification.py      comprobación real del efecto
│   │   ├── events.py            bus de eventos
│   │   ├── confirmations.py     confirmaciones pendientes (un solo uso, con TTL)
│   │   └── assistants.py        identidad JARKKO (+ alias jarvis/ekko)
│   ├── database/                db.py (SQLite + WAL), models.py (esquema)
│   ├── schemas/                 modelos Pydantic de la API
│   └── utils/                   texto y saneado de datos
├── tests/                       151 tests
├── data/jarvis.db               se crea al arrancar (ignorado por git)
├── data/voice/                  caché de audio (ignorado por git)
├── data/models/                 modelo de reconocimiento (ignorado por git)
├── start-jarkko.ps1             lanzador solo-backend (depuración)
├── requirements.txt
├── .env / .env.example
├── API_CONTRACT.md              contrato para el frontend
└── README.md
```

---

## Endpoints

Contrato completo, con ejemplos de request/response: **[API_CONTRACT.md](API_CONTRACT.md)**.

| Método | Ruta | Descripción |
| --- | --- | --- |
| GET | `/api/health` | Estado, versión, proveedor de IA, voz, nº de herramientas |
| GET | `/api/system/status` | Memoria, disco, procesos, CPU |
| GET | `/api/system/info` | Información detallada del equipo |
| GET | `/api/tools` | Catálogo de herramientas + riesgos + apps conocidas |
| GET | `/api/tools/{nombre}` | Detalle de una herramienta |
| POST | `/api/chat` | Lenguaje natural → interpretación → ejecución (+ voz) |
| POST | `/api/actions/execute` | Ejecutar una herramienta concreta |
| POST | `/api/actions/confirm` | Confirmar o cancelar una acción de riesgo alto |
| GET | `/api/actions/pending` | Confirmaciones pendientes |
| GET | `/api/activity` | Historial reciente (filtros: `limit`, `tool`, `status`) |
| GET | `/api/activity/stats` | Resumen de actividad |
| GET | `/api/files/search` | `?q=...&path=...` |
| GET | `/api/files/list` | `?path=...&limit=...` |
| GET | `/api/files/known-folders` | Escritorio, Documentos, Descargas, … |
| GET | `/api/voice/status` | Motores, caché, cuota de la voz de identidad |
| GET | `/api/voice/listen/status` | Estado de la escucha, micrófono y lo último oído |
| POST | `/api/voice/listen/start` | Activar la escucha manos libres |
| POST | `/api/voice/listen/stop` | Desactivarla |
| POST | `/api/voice/listen` | Escuchar una vez (con `execute` ejecuta la orden) |
| GET | `/api/voice/microphone/test` | Diagnóstico del nivel de micrófono |
| GET | `/api/voice/phrases` | Catálogo de frases fijas |
| POST | `/api/voice/speak` | Hacer hablar a JARKKO |
| GET | `/api/voice/audio/{clave}` | Audio cacheado (para que lo reproduzca el frontend) |
| POST | `/api/voice/cache/build` | Generar el caché con la voz de identidad |
| WS | `/ws/events` | Eventos en tiempo real |

---

## Herramientas del MVP

| Herramienta | Riesgo | Descripción |
| --- | --- | --- |
| `open_url` | low | Abre una URL http/https en el navegador por defecto |
| `web_search` | low | Busca en el buscador configurado |
| `open_application` | low → **high** para shells | Abre una app del catálogo |
| `list_files` | low | Lista una carpeta |
| `search_files` | low | Busca por nombre (admite `*` y `?`) |
| `open_file` | low | Abre un archivo (no ejecutables ni scripts) |
| `open_folder` | low | Abre una carpeta en el Explorador |
| `create_folder` | medium | Crea una carpeta (verificada) |
| `move_file` | medium | Mueve archivo o carpeta (verificado, sin sobrescribir) |
| `copy_file` | medium | Copia archivo o carpeta (verificado, sin sobrescribir) |
| `rename_file` | medium | Renombra en su misma ubicación (verificado) |
| `get_datetime` | low | Fecha y hora locales (día de la semana en español) |
| `media_control` | low | Teclas multimedia de Windows: pausa, pista, volumen, silencio |
| `get_news` | low | Titulares del día desde fuentes RSS autorizadas (sin clave) |
| `play_media` | low | Abre música o vídeo en Spotify, YouTube o YouTube Music |
| `delete_file` | **critical** | Definida pero **deshabilitada**; requiere activación + confirmación |

Apps reconocidas: Chrome, Edge, Firefox, VS Code, Bloc de notas, Calculadora,
Explorador de archivos y PowerShell. Abrir PowerShell abre una ventana vacía para
el usuario y exige confirmación; el asistente **no** escribe comandos en ella.

Alias de carpetas admitidos en cualquier parámetro de ruta (`Descargas`,
`Escritorio`, `Documentos`, `Imágenes`, `Vídeos`, `Música`, y sus equivalentes en
inglés), resueltos desde el registro de Windows para respetar redirecciones de
OneDrive.

---

## Configuración

Todas las variables usan el prefijo `JARVIS_` (ver `.env.example`).

| Variable | Por defecto | Descripción |
| --- | --- | --- |
| `JARVIS_HOST` / `JARVIS_PORT` | `127.0.0.1` / `8765` | Dirección del servidor |
| `JARVIS_CORS_ORIGINS` | `…:5173,…:4173,file://,null` | Orígenes permitidos (Vite dev/preview y Electron empaquetado) |
| `JARVIS_AI_PROVIDER` | `mock` | `mock`, `openai`, `anthropic`, `gemini` |
| `JARVIS_AI_API_KEY` | vacío | Clave del proveedor externo (nunca se registra en logs) |
| `JARVIS_CONFIRMATION_THRESHOLD` | `high` | Riesgo mínimo que exige confirmación |
| `JARVIS_ENABLE_CRITICAL_TOOLS` | `false` | Habilita herramientas `critical` |
| `JARVIS_EXTRA_ALLOWED_ROOTS` | vacío | Raíces extra para archivos, separadas por comas |
| `JARVIS_CONFIRMATION_TTL_SECONDS` | `300` | Validez de una confirmación |
| `JARVIS_SEARCH_ENGINE` | `google` | `google`, `duckduckgo`, `bing` |
| `JARVIS_SYSTEM_STATUS_INTERVAL` | `5` | Segundos entre eventos `system.status` |
| `JARVIS_DATABASE_PATH` | `data/jarvis.db` | Ruta del SQLite |
| `JARVIS_LOG_LEVEL` | `INFO` | Nivel de log |
| `JARVIS_TTS_ENABLED` | `true` | Interruptor general de la voz |
| `JARVIS_TTS_AUTOSPEAK` | `true` | Si habla solo al responder en `/api/chat` |
| `JARVIS_TTS_PLAYBACK` | `true` | Si el backend reproduce por los altavoces |
| `JARVIS_TTS_ENGINE` | `auto` | `auto`, `elevenlabs`, `windows`, `none` |
| `JARVIS_TTS_WINDOWS_VOICE` | `Microsoft Raul` | Voz local (es-MX, masculina) |
| `JARVIS_TTS_CACHE_DIR` | `data/voice` | Caché de audio |
| `JARVIS_ELEVENLABS_API_KEY` | vacío | Voz de identidad (opcional) |
| `JARVIS_ELEVENLABS_VOICE_ID` | `WEXRePkZGpmcFLvCOaB1` | Voz de JARKKO |
| `JARVIS_ELEVENLABS_MODEL` | `eleven_multilingual_v2` | `eleven_flash_v2_5` gasta la mitad de créditos |
| `JARVIS_ELEVENLABS_ALLOW_LIVE` | `false` | **Protección de cuota**: solo caché |
| `JARVIS_ELEVENLABS_OUTPUT_FORMAT` | `pcm_24000` | PCM se envuelve en WAV; si el plan no lo permite, reintenta en MP3 |
| `JARVIS_STT_ENABLED` | `true` | Interruptor general de la escucha |
| `JARVIS_STT_AUTOSTART` | `false` (`true` en el `.env`) | Abrir el micrófono al arrancar |
| `JARVIS_WAKE_WORD` | `jarkko` | Palabra clave |
| `JARVIS_WAKE_WORD_REQUIRED` | `true` | `false` obedece cualquier frase (más falsos positivos) |
| `JARVIS_STT_MODEL_PATH` | `data/models/vosk-model-small-es-0.42` | Modelo de Vosk |
| `JARVIS_STT_DEVICE` | `-1` | Micrófono (-1 = el predeterminado) |
| `JARVIS_STT_SILENCE_SECONDS` | `1.2` | Silencio que cierra una frase |

Si se selecciona un proveedor de IA externo sin implementación o sin API key, el
backend **no falla**: registra un aviso, cae al `MockAIProvider` y lo indica en
`/api/health` (`ai_provider.fallback_for`).

---

## Cómo se amplía

**Herramienta nueva** — declara su `ToolDefinition` en el módulo correspondiente de
`app/tools/` y registra el módulo en `app/tools/bootstrap.py`. Nada más: la API, el
agente, los permisos y la voz la recogen automáticamente.

```python
registry.register(
    ToolDefinition(
        name="mi_herramienta",
        description="Qué hace, en una frase.",
        category=ToolCategory.SYSTEM,
        risk_level=RiskLevel.MEDIUM,
        handler=mi_handler,                # handler(args) -> ToolResult
        verify=True,                       # se verifica el efecto real
        parameters=(ParameterSpec(name="path", type=ParamType.PATH, must_exist=True),),
    )
)
```

Si quieres que tenga su propia frase hablada, añade la clave en
`app/voice/phrases.py` (`_TOOL_SUCCESS_PHRASES`) y regenera el caché.

**Aplicación nueva** — añade un `AppSpec` a `APPLICATIONS` en
`app/tools/applications/catalog.py` con sus rutas candidatas.

**Motor de voz nuevo** (Piper, edge-tts…) — implementa `TTSProvider` en
`app/voice/` y añádelo a la cadena en `VoiceService._build_engines`.

**Proveedor de IA real** — implementa `parse_intent` en la clase correspondiente de
`app/providers/external.py` usando `registry.describe_for_prompt()` o el esquema de
*tool calling* nativo, devuelve `IntentResult` y quita la degradación en
`app/providers/factory.py`. El resto del sistema no cambia.

---

## Limitaciones actuales

- Solo Windows: `os.startfile`, `winsound`/MCI y las voces WinRT.
- **El micrófono de este equipo entrega silencio** (está silenciado o deshabilitado
  en Windows): la escucha está implementada y probada, pero no oirá nada hasta que se
  desmutee. Compruébalo con `GET /api/voice/microphone/test`.
- El reconocedor es el modelo pequeño: acierta bien en órdenes cortas, comete fallos
  en nombres propios y palabras raras (la palabra clave se maneja con variantes).
- Sin interrupción («barge-in»): no se puede cortar a JARKKO hablando; el micrófono
  se ignora mientras suena.
- Los proveedores de IA externos (OpenAI/Anthropic/Gemini) están declarados pero
  **sin implementar**: el cerebro es el `MockAIProvider` de reglas, que obedece
  bien pero no conversa.
- La voz de identidad solo suena en frases fijas cacheadas; el texto dinámico usa
  la voz local. Es deliberado: es lo que mantiene el coste en cero.
- Sin control de ventanas ni terminación de procesos (previstos como `high`).
- `delete_file` deshabilitada y sin papelera de reciclaje.
- Confirmaciones y eventos viven en memoria: se pierden al reiniciar (la actividad
  y el caché de voz, no).
- Sin autenticación: el servidor escucha solo en `127.0.0.1` y está pensado para
  uso local de escritorio.
