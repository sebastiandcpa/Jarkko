# JARKKO · Contrato de API

Documento de referencia para el desarrollo del **frontend**.
Versión del backend: **0.1.0**.

> **Cambios desde la primera versión** (léelos si ya integraste algo):
> 1. **Una sola identidad: `jarkko`.** `jarvis` y `ekko` siguen aceptándose como
>    alias en las peticiones, pero la respuesta siempre trae `assistant: "jarkko"`.
> 2. **Nuevos endpoints `/api/voice/*`** y dos eventos nuevos por WebSocket:
>    `assistant.speaking` y `assistant.spoken`.
> 3. `GET /api/health` trae ahora `aliases` y `voice`.
> 4. **JARKKO escucha**: `/api/voice/listen/*` (manos libres con la palabra clave
>    «Jarkko») y los eventos `speech.partial` / `speech.heard`.
> 5. **El backend NO se arranca solo**: la app de escritorio necesita que
>    `uvicorn app.main:app --host 127.0.0.1 --port 8765` esté en marcha.

- **Base URL:** `http://127.0.0.1:8765`
- **WebSocket:** `ws://127.0.0.1:8765/ws/events`
- **Documentación interactiva (OpenAPI):** `http://127.0.0.1:8765/docs`
- **Content-Type:** `application/json` en todas las peticiones con cuerpo.
- **CORS:** permitidos por defecto `http://127.0.0.1:5173`, `http://localhost:5173`,
  `http://127.0.0.1:4173`, `http://localhost:4173` y, para el frontend empaquetado
  con Electron (que carga `dist/index.html` con `loadFile`), `file://` y `null`.
  Para otros orígenes: variable `JARVIS_CORS_ORIGINS` (lista separada por comas).
  Métodos permitidos: `GET`, `POST`, `OPTIONS`. Sin credenciales ni cookies.
- **Autenticación:** ninguna (servidor local).

---

## 1. Convenciones

### 1.1 Identidad

**JARKKO** es el asistente: un solo motor, una sola personalidad, un solo modelo.
Es la fusión de JARVIS y EKKO.

El campo `assistant` acepta `"jarkko"` y, por compatibilidad, los alias `"jarvis"`,
`"ekko"` y `"jarvis-ekko"`. Todos resuelven a JARKKO, y la respuesta devuelve
siempre `assistant: "jarkko"`. Cualquier valor desconocido también cae en JARKKO,
así que el campo nunca produce error.

Para la interfaz: **no** ofrezcas un selector de personalidad; hay un único
asistente. `GET /api/health` → `assistants` trae su ficha (nombre, lema y el
`voice_id` de su voz) y `aliases` los nombres aceptados.

### 1.2 Niveles de riesgo

| `risk_level` | Significado | Comportamiento |
| --- | --- | --- |
| `low` | Lectura o apertura de recursos | Se ejecuta directamente |
| `medium` | Modifica archivos de forma reversible | Se ejecuta directamente |
| `high` | Impacto en el sistema | **Requiere confirmación explícita** |
| `critical` | Irreversible | Bloqueada salvo activación en configuración |

El umbral es configurable (`JARVIS_CONFIRMATION_THRESHOLD`); el frontend debe
leerlo de `GET /api/tools` → `confirmation_threshold` y no asumirlo.

### 1.3 Estados de una acción (`ActionResult.status`)

| Estado | Qué ocurrió |
| --- | --- |
| `success` | Ejecutada y, si aplica, verificada |
| `error` | Falló la ejecución (o no se pudo verificar el efecto) |
| `conflict` | El destino ya existe; **no se sobrescribió nada** |
| `denied` | La herramienta se negó (p.ej. abrir un `.exe`) |
| `rejected` | Bloqueada antes de ejecutarse (herramienta inexistente/deshabilitada, argumento o ruta inválida) |
| `awaiting_confirmation` | En espera del usuario; llega `confirmation_id` |
| `skipped` | No se ejecutó porque otra acción del plan falló o quedó en espera |
| `cancelled` | El usuario rechazó la confirmación |

Solo `success` significa que el sistema cambió.

### 1.4 Errores HTTP

`200` incluso cuando una acción es `rejected` o `denied`: el resultado va en el
cuerpo (`status` + `error`). Los códigos de error HTTP se reservan para problemas
de la petición:

| Código | Cuándo |
| --- | --- |
| `400` | Ruta o argumento inválido en endpoints `/api/files/*` |
| `403` | Operación denegada en endpoints `/api/files/*` |
| `404` | Herramienta o confirmación inexistente |
| `409` | Conflicto en endpoints `/api/files/*` |
| `422` | Cuerpo/query inválido (validación de FastAPI) |
| `500` | Error interno |

Forma del error:

```json
{ "detail": { "code": "path_outside_allowed_roots", "message": "La ruta está fuera de las carpetas permitidas (C:\\Users\\Usuario).", "field": "path" } }
```

Códigos frecuentes: `tool_not_found`, `tool_disabled`, `critical_tools_disabled`,
`confirmation_required`, `confirmation_not_found`, `confirmation_expired`,
`missing_parameter`, `unknown_parameters`, `invalid_type`, `path_not_found`,
`path_already_exists`, `not_a_file`, `not_a_directory`, `path_outside_allowed_roots`,
`system_path_denied`, `sensitive_path_denied`, `unc_not_allowed`, `reserved_name`,
`invalid_file_name`, `scheme_not_allowed`, `credentials_in_url`,
`executable_extension_blocked`, `destination_exists`, `destination_parent_missing`,
`app_not_in_registry`, `app_not_installed`.

---

## 2. `GET /api/health`

Comprobación de vida y configuración efectiva. Úsalo al arrancar la app.

```json
{
  "status": "ok",
  "assistant": "jarvis-ekko",
  "version": "0.1.0",
  "assistants": [
    {
      "key": "jarkko",
      "display_name": "JARKKO",
      "tagline": "Preciso como JARVIS, cercano como EKKO. Un solo asistente.",
      "voice_id": "WEXRePkZGpmcFLvCOaB1"
    }
  ],
  "aliases": ["ekko", "jarko", "jarkos", "jarvis", "jarvis-ekko"],
  "voice": {
    "enabled": true,
    "engines": ["windows"],
    "identity_voice_configured": false,
    "cached_phrases": 0,
    "autospeak": true
  },
  "ai_provider": { "name": "mock", "requires_api_key": false, "available": true, "mode": "rule_based" },
  "tools_registered": 16,
  "confirmation_threshold": "high",
  "critical_tools_enabled": false,
  "websocket": "/ws/events",
  "uptime_seconds": 42
}
```

`assistant` es el nombre del **backend** (`jarvis-ekko`); la identidad del asistente
es la de `assistants[0].key` → `jarkko`.
`voice.engines` lista los motores de voz activos en orden de preferencia.

Si se configuró un proveedor externo sin implementación o sin clave,
`ai_provider` incluye `"fallback_for": "openai"` y una `note` explicativa: el
asistente sigue funcionando con reglas locales.

---

## 3. `GET /api/system/status`

Pensado para sondeo ligero o para acompañar al evento `system.status`.

```json
{
  "system": "operational",
  "memory_percent": 83.9,
  "disk_percent": 52.8,
  "running_processes": 314,
  "cpu_percent": 0.0,
  "uptime_seconds": 172693,
  "timestamp": "2026-09-27T17:52:02-05:00"
}
```

No genera entradas en el registro de actividad: puede llamarse periódicamente.

### `GET /api/system/info`

Información detallada: `{ "info": {...}, "memory": {...}, "disk": {...}, "user_paths": {...} }`
(SO, CPU, núcleos, RAM total, `boot_time`, particiones y carpetas del usuario).

---

## 4. `GET /api/tools`

Catálogo completo. Útil para pintar una paleta de comandos o un panel de permisos.

```json
{
  "total": 16,
  "confirmation_threshold": "high",
  "risk_levels": {
    "low": "Solo lectura o apertura de recursos. No modifica datos del usuario.",
    "medium": "Modifica el sistema de archivos de forma reversible (crear, copiar, mover, renombrar).",
    "high": "Acción potencialmente destructiva o con impacto en el sistema. Requiere confirmación explícita.",
    "critical": "Acción irreversible. Deshabilitada salvo activación explícita en la configuración."
  },
  "tools": [
    {
      "name": "create_folder",
      "description": "Crea una carpeta nueva (incluyendo carpetas intermedias).",
      "category": "files",
      "risk_level": "medium",
      "enabled": true,
      "parameters": [
        {
          "name": "path",
          "type": "path",
          "description": "Ruta completa de la carpeta a crear.",
          "required": true,
          "must_exist": false,
          "kind": "any"
        }
      ],
      "examples": ["Crea una carpeta llamada Jarvis Test en Documentos"]
    }
  ],
  "applications": [
    { "key": "chrome", "display_name": "Google Chrome", "aliases": ["google chrome", "navegador chrome"], "installed": true, "risk_level": "low", "note": "" },
    { "key": "powershell", "display_name": "Windows PowerShell", "aliases": ["power shell", "terminal", "consola"], "installed": true, "risk_level": "high", "note": "Se abre una ventana interactiva vacía para el usuario. El asistente no escribe ni ejecuta comandos dentro de ella." }
  ]
}
```

`category`: `browser` | `applications` | `files` | `system`.
`parameters[].type`: `string` | `integer` | `boolean` | `path` | `url`.
`parameters[].kind` (solo `path`): `any` | `file` | `directory`.
`parameters[].must_exist` (solo `path`): `true` debe existir, `false` no debe existir, `null` indiferente.

`GET /api/tools/{nombre}` devuelve un único objeto `Tool`, o `404`.

---

## 5. `POST /api/chat`

Entrada principal. Interpreta, planifica y ejecuta en una sola llamada.

**Request**

```json
{
  "message": "Abre YouTube",
  "assistant": "jarkko",
  "conversation_id": null
}
```

| Campo | Tipo | Obligatorio | Notas |
| --- | --- | --- | --- |
| `message` | string (1–2000) | sí | Texto del usuario |
| `assistant` | `"jarkko"` | no (`"jarkko"`) | Acepta los alias `jarvis` / `ekko` |
| `conversation_id` | string \| null | no | Omítelo la primera vez y **reutiliza** el que devuelve |

**Response 200**

```json
{
  "conversation_id": "70833143365b45549a94069f53da24a7",
  "assistant": "jarkko",
  "message": "Hecho. Abrí https://www.youtube.com en el navegador.",
  "status": "success",
  "requires_confirmation": false,
  "confirmations": [],
  "actions": [
    {
      "tool": "open_url",
      "status": "success",
      "message": "Abrí https://www.youtube.com en el navegador.",
      "risk_level": "low",
      "arguments": { "url": "https://www.youtube.com" },
      "data": { "url": "https://www.youtube.com" },
      "verified": null,
      "verification_detail": null,
      "confirmation_id": null,
      "duration_ms": 187,
      "error": null
    }
  ],
  "intent": {
    "reply": "",
    "actions": [{ "tool": "open_url", "arguments": { "url": "https://www.youtube.com" }, "reason": "Abrir https://www.youtube.com en el navegador." }],
    "confidence": 0.85,
    "source": "mock",
    "needs_clarification": false,
    "matched_rule": "open_target:url"
  }
}
```

`status` de la conversación: `success` | `error` | `awaiting_confirmation` | `no_action`.

- `no_action`: no se entendió la orden o era conversación (saludo, ayuda). `actions` vacío
  y `message` explica qué sabe hacer. `intent.needs_clarification` indica si conviene
  pedir al usuario que reformule.
- `awaiting_confirmation`: **no se ejecutó nada** del plan. Ver §7.

`message` ya viene con el tono de la identidad (`"Hecho."` / `"¡Listo!"`); es el
texto listo para mostrar en el chat.

### Frases que entiende el MockAIProvider

| Ejemplo | Herramienta resultante |
| --- | --- |
| «Abre YouTube», «ábreme youtube.com», «ve a github» | `open_url` |
| «busca en internet recetas de pan», «googlea python» | `web_search` |
| «abre el bloc de notas», «abre chrome» | `open_application` |
| «abre la carpeta Descargas», «abre Descargas» | `open_folder` |
| «abre el archivo Documentos/notas.txt» | `open_file` |
| «lista los archivos de Descargas», «qué hay en Documentos» | `list_files` |
| «busca el archivo factura.pdf», «busca *.png en Imágenes» | `search_files` |
| «crea una carpeta llamada Jarvis Test en Documentos» | `create_folder` |
| «mueve Descargas/foto.png a Imágenes» | `move_file` |
| «copia Documentos/cv.pdf a Escritorio» | `copy_file` |
| «renombra Descargas/doc.txt a notas.txt» | `rename_file` |
| «cuánta memoria estoy usando», «espacio en disco», «qué procesos hay», «información del sistema» | `get_*` |
| «¿qué hora es?», «qué día es hoy», «dime la hora» | `get_datetime` |
| «pausa», «sube el volumen», «siguiente canción», «silencia» | `media_control` |
| «pon música», «reproduce música» | `open_url` (el reproductor) |
| «cuéntame las noticias», «noticias de economía», «noticias sobre X» | `get_news` |
| «reproduce Dominick Fike en Spotify», «pon Bad Bunny en YouTube» | `play_media` |
| «abre youtube y spotify» | dos acciones en un plan |
| «hola», «qué puedes hacer», «¿me escuchas?», «gracias» | ninguna acción (`no_action`) |

Si no hay carpeta indicada, «crea una carpeta llamada X» usa **Documentos**.

**Tolerancia al lenguaje real.** No hace falta dar la orden seca. Si la frase completa
no encaja en ninguna regla, se le quita la cortesía y se vuelve a intentar, así que
todas estas equivalen a «abre YouTube»:

- «¿me puedes abrir YouTube?» · «quiero que abras youtube» · «oye, ¿podrías poner Spotify?»
- «necesito que busques información sobre la luna» → `web_search`
- «cuánta memoria tengo» · «cómo va el disco» · «qué procesos tengo abiertos» → `get_*`

**Rescate de frases mal transcritas.** El reconocedor de voz destroza los verbos pero
los nombres propios aguantan. Con una frase **corta**, **sin negaciones** y con **un
único objetivo conocido**, se abre lo evidente: «pueden saber youtube» → `open_url`.
Nunca se rescata algo de riesgo mayor que bajo — una frase suelta mal entendida jamás
acaba ofreciendo una consola del sistema. Si hay negación («no abras youtube»,
«cierra youtube»), varios objetivos o la frase es larga, no se adivina nada.

**Cuando no se puede, se dice por qué.** El motor no devuelve nunca un «no te
entendí» genérico. En `matched_rule` llega `unresolved:<motivo>` y en `message` la
explicación concreta, que la UI puede mostrar tal cual:

| `matched_rule` | Cuándo | Ejemplo de `message` |
| --- | --- | --- |
| `unresolved:target` | se entendió «abre X» pero X no es web, app ni carpeta | «Entendí que quieres abrir «trapatrapa», pero no sé qué es…» |
| `unresolved:folder` · `:file` · `:url` | falta el nombre, o no se reconoce | «¿Qué carpeta quieres que abra?…» |
| `unresolved:path_needed` | mover/copiar/renombrar sin rutas | «…necesito la ruta del origen y el destino» |
| `unresolved:create` | crear sin nombre | «Dime cómo la llamo y dónde» |
| `unresolved:delete` | pidió borrar | «No borro nada: esa herramienta está deshabilitada a propósito» |
| `unresolved:no_tool` | apagar, cerrar, instalar… | «No tengo herramientas para eso» |
| `unresolved:too_short` | una o dos palabras sin sentido | «Solo entendí «X»…» |
| `unresolved:unknown` | nada de lo anterior | «No sé qué hacer con «X»» + lo que sí sabe hacer |

Si la orden **sí** se interpretó pero falló al ejecutarse, el motivo llega en el
`message` de la acción y es igual de concreto: «No existe la ruta: C:\Users\…» o
«La ruta pertenece a un directorio protegido del sistema».

El `status` resultante distingue los dos casos que la UI debe pintar distinto:
`no_action` (te contesta, no ejecuta nada) y `success`/`error` (ejecutó algo).

---

## 6. `POST /api/actions/execute`

Ejecución directa de una herramienta (botones, paleta de comandos, reintentos).
Salta la interpretación de lenguaje natural, **no** la validación ni los permisos.

**Request**

```json
{
  "tool": "open_url",
  "arguments": { "url": "https://youtube.com" },
  "assistant": "jarkko",
  "conversation_id": null
}
```

**Response 200** — un único objeto `ActionResult` (§1.3).

```json
{
  "tool": "create_folder",
  "status": "success",
  "message": "Creé la carpeta C:\\Users\\Usuario\\Documents\\Jarvis Test.",
  "risk_level": "medium",
  "arguments": { "path": "C:\\Users\\Usuario\\Documents\\Jarvis Test" },
  "data": { "path": "C:\\Users\\Usuario\\Documents\\Jarvis Test" },
  "verified": true,
  "verification_detail": "La carpeta existe en disco: C:\\Users\\Usuario\\Documents\\Jarvis Test",
  "confirmation_id": null,
  "duration_ms": 3,
  "error": null
}
```

Ejemplo de rechazo (no es un error HTTP):

```json
{
  "tool": "open_url",
  "status": "rejected",
  "message": "Solo se permiten URLs http o https.",
  "risk_level": "low",
  "error": { "code": "scheme_not_allowed", "message": "Solo se permiten URLs http o https.", "field": "url" }
}
```

Si la herramienta es de riesgo alto, la respuesta es
`status: "awaiting_confirmation"` con `confirmation_id`, y **no se ejecuta nada**.

### Datos útiles en `data` por herramienta

| Herramienta | Campos de `data` |
| --- | --- |
| `open_url`, `web_search` | `url`, `query`, `engine` |
| `open_application` | `app`, `display_name`, `executable`, `pid`, `note` |
| `list_files` | `path`, `entries[]`, `total`, `directories`, `files`, `truncated` |
| `search_files` | `query`, `root_path`, `results[]`, `total`, `scanned`, `truncated` |
| `create_folder` | `path` |
| `move_file`, `copy_file`, `rename_file` | `source`, `destination`, `new_name` |
| `get_datetime` | `iso`, `date`, `time`, `weekday`, `day`, `month`, `year`, `timezone` |
| `media_control` | `action`, `key_presses`, `verified: false` (Windows no deja leer el volumen sin dependencias extra) |
| `get_news` | `origin`, `topic`, `total`, `shown`, `headlines[]` (`title`, `source`, `link`, `published`) |
| `play_media` | `query`, `service`, `service_name`, `url` |
| `get_system_info` | `os`, `cpu_cores_logical`, `memory_total_gb`, `boot_time`, `user_paths`, … |
| `get_memory_usage` | `total_gb`, `used_gb`, `available_gb`, `percent`, `swap_percent` |
| `get_disk_usage` | `partitions[]`, `primary_percent`, `primary_free_gb`, `primary_total_gb` |
| `get_running_processes` | `total`, `sort_by`, `processes[]` (`pid`, `name`, `memory_mb`, `cpu_percent`) |

Entradas de archivo (`entries[]`, `results[]`):

```json
{ "name": "factura.pdf", "path": "C:\\Users\\Usuario\\Documents\\factura.pdf", "type": "file", "size": 20481, "modified": "2026-09-20T11:03:12-05:00" }
```

`type`: `"file"` | `"directory"`; `size` es `null` en directorios.

---

## 7. Confirmaciones

Flujo de una acción de riesgo alto (ejemplo: «abre powershell»):

```
POST /api/chat                      → status: "awaiting_confirmation"
                                      requires_confirmation: true
                                      confirmations: [{ confirmation_id, tool, risk_level, description, expires_at }]
   (evento WS: assistant.status = waiting_confirmation + confirmation.required)
POST /api/actions/confirm           → { confirmation_id, approved: true|false }
                                      approved:true  → se revalida y se ejecuta  → status: success|error|conflict|denied|rejected
                                      approved:false → status: "cancelled"
```

**`POST /api/actions/confirm`**

```json
{ "confirmation_id": "hT7…", "approved": true, "assistant": "jarkko" }
```

Devuelve un `ActionResult`. Reglas que el frontend debe tener en cuenta:

- Cada `confirmation_id` es de **un solo uso**; al reusarlo → `404`
  (`confirmation_not_found`).
- Caduca a los `JARVIS_CONFIRMATION_TTL_SECONDS` (300 s por defecto): usa
  `expires_at` para mostrar una cuenta atrás o retirar el diálogo.
- Al confirmar, la acción se **revalida**: si el disco cambió (p.ej. el destino ya
  existe), el resultado puede ser `rejected` o `conflict` en lugar de `success`.
- Un plan con varias acciones donde alguna requiere confirmación **no ejecuta
  ninguna**; las demás llegan como `skipped`.

**`GET /api/actions/pending`** — para rehidratar diálogos tras recargar la UI:

```json
{ "total": 1, "confirmations": [ { "confirmation_id": "hT7…", "tool": "open_application", "arguments": { "app_name": "powershell" }, "risk_level": "high", "description": "Abre una aplicación del catálogo permitido → open_application(app_name=powershell)", "assistant": "jarkko", "conversation_id": "70833…", "created_at": "2026-09-27T17:53:01-05:00", "expires_at": "2026-09-27T17:58:01-05:00" } ] }
```

---

## 8. `GET /api/activity`

Historial persistido en SQLite. Query params: `limit` (1–500, por defecto 50),
`tool`, `status`.

```json
{
  "total": 2,
  "limit": 50,
  "entries": [
    {
      "id": 9,
      "timestamp": "2026-09-27T17:52:41-05:00",
      "assistant": "jarkko",
      "conversation_id": "70833143365b45549a94069f53da24a7",
      "tool": "search_files",
      "arguments": { "query": "Jarvis Smoke", "root_path": "C:\\Users\\Usuario\\Documents" },
      "risk_level": "low",
      "status": "success",
      "message": "Encontré 1 resultados para «Jarvis Smoke» en C:\\Users\\Usuario\\Documents.",
      "duration_ms": 512,
      "verified": null
    },
    {
      "id": 4,
      "timestamp": "2026-09-27T17:52:20-05:00",
      "assistant": "jarkko",
      "conversation_id": null,
      "tool": "open_application",
      "arguments": { "app_name": "powershell" },
      "risk_level": "high",
      "status": "cancelled",
      "message": "El usuario canceló la acción.",
      "duration_ms": null,
      "verified": null
    }
  ]
}
```

Orden: más reciente primero. Se registran también los rechazos y cancelaciones
(sirve como traza de auditoría). Los argumentos se sanean: las claves sensibles
(`password`, `token`, `api_key`, `clave`…) aparecen como `"[redactado]"`.

**`GET /api/activity/stats`** → `{ "total": 9, "by_status": { "success": 4, "rejected": 3, … }, "top_tools": [ { "tool": "list_files", "count": 2 } ] }`

---

## 9. `GET /api/files/*`

Atajos de lectura que atraviesan la misma validación de rutas que las herramientas.
Aceptan alias de carpeta (`Descargas`, `Documentos`, …) además de rutas absolutas.

| Endpoint | Query | Respuesta |
| --- | --- | --- |
| `/api/files/search` | `q` (≥2, admite `*` y `?`), `path` (opcional) | `{ query, root_path, total, truncated, scanned, results[] }` |
| `/api/files/list` | `path` (obligatorio), `limit` (1–1000, def. 200) | `{ path, total, directories, files, truncated, entries[] }` |
| `/api/files/known-folders` | — | `{ "folders": { "home": "C:\\Users\\Usuario", "desktop": "…", "documents": "…", "downloads": "…", "pictures": "…", "videos": "…", "music": "…" } }` |

En estos endpoints un problema de ruta **sí** es error HTTP (`400`/`403`/`409`).
`truncated: true` indica que se alcanzó el límite de resultados o de entradas
escaneadas: muéstralo en la UI.

Usa `known-folders` para construir accesos rápidos en lugar de hardcodear rutas.

---

## 9.bis `GET|POST /api/voice/*` — la voz de JARKKO

JARKKO habla solo: al responder en `/api/chat` reproduce su locución por los
altavoces del equipo (configurable con `JARVIS_TTS_AUTOSPEAK`). El frontend no
tiene que hacer nada para que suene; estos endpoints son para controlarlo,
mostrarlo en la interfaz o reproducir el audio en el cliente en lugar del backend.

**Lo hablado no es lo escrito.** Ante una acción, en pantalla va el detalle
(`Creé la carpeta C:\Users\...\Jarvis Test`) y en voz una frase corta y fija
(*«Carpeta creada y verificada»*). Esas frases fijas son las que suenan con la voz
de identidad, porque están cacheadas y no cuestan nada. Las herramientas
informativas (memoria, disco, procesos, sistema) son la excepción: ahí se lee el
dato real con la voz local.

### `GET /api/voice/status`

```json
{
  "enabled": true,
  "autospeak": true,
  "playback": true,
  "engines": [
    { "name": "windows", "available": true, "voice": "Microsoft Raul",
      "cost": "gratis, offline, ilimitada", "position": 1 }
  ],
  "cache": {
    "entries": 3, "bytes": 412160, "by_engine": { "windows": 3 },
    "phrases_cached": ["ack.generic", "capabilities", "presence"],
    "directory": "C:\Users\Usuario\Desktop\Jarvis - Ekko\backend\data\voice",
    "catalog_phrases": 26, "catalog_characters": 1174
  },
  "identity_voice": { "configured": false },
  "last_spoken": {
    "text": "Aquí estoy.", "engine": "windows", "voice": "Microsoft Raul",
    "cached": true, "phrase_key": "presence", "played": true, "duration_ms": 1722
  }
}
```

Con la API key de ElevenLabs puesta, `identity_voice` incluye además
`voice_check` (si la voz está disponible en la cuenta) y `subscription`
(créditos usados/restantes), útil para mostrar la cuota en la interfaz.

### `POST /api/voice/speak`

```json
{ "phrase_key": "greeting", "play": true }
```

o texto libre:

```json
{ "text": "Ya terminé de copiar los archivos.", "play": true }
```

| Campo | Tipo | Notas |
| --- | --- | --- |
| `phrase_key` | string | Clave del catálogo (`GET /api/voice/phrases`). Suena con la voz de identidad si está cacheada |
| `text` | string | Texto libre (máx. 2000). Usa la voz local; no se cachea |
| `play` | bool \| null | `false` sintetiza sin reproducir en el equipo (para que lo reproduzca el frontend) |

Respuesta:

```json
{
  "spoken": true,
  "engine": "windows",
  "voice": "Microsoft Raul",
  "media_type": "audio/wav",
  "cached": true,
  "phrase_key": "greeting",
  "text": "Hola. Soy Jarkko. ¿Qué necesitas?",
  "audio_url": "/api/voice/audio/02843ac062bdc78cf058dfd8de76298d",
  "bytes": 183726
}
```

`404` si la `phrase_key` no existe, `422` si no mandas ni `text` ni `phrase_key`.
`spoken: false` con `reason` si la voz está desactivada.

### `GET /api/voice/audio/{clave}`

Devuelve el archivo (`audio/wav` o `audio/mpeg`). Solo existe para audio cacheado,
es decir para frases fijas: úsalo si prefieres reproducir en el cliente
(`new Audio(...)`) en vez de dejar que suene en el backend. `404` si no está.

### `GET /api/voice/phrases`

`{ "total": 26, "total_characters": 1174, "phrases": [ { "key": "greeting", "text": "…", "characters": 33 } ] }`

### `POST /api/voice/cache/build?only_missing=true`

Genera el caché con la voz de identidad. **Es la única ruta que consume créditos de
ElevenLabs**, y solo se dispara a mano (una vez). Devuelve qué frases se generaron,
cuántos caracteres costó y el estado de la cuota. Sin API key responde
`{ "ok": false, "reason": "elevenlabs_not_configured" }` — y JARKKO sigue hablando
con la voz local.

---

---

## 9.ter `/api/voice/listen/*` — JARKKO escucha

Reconocimiento de voz **offline** (Vosk, modelo español de 39 MB), en CPU y sin
coste. Funciona sin que el frontend haga nada: el backend abre el micrófono, espera
la palabra clave y ejecuta la orden. Estos endpoints sirven para encenderlo,
apagarlo, mostrar lo que oye y diagnosticar el micrófono.

### `GET /api/voice/listen/status`

```json
{
  "enabled": true,
  "running": true,
  "available": true,
  "wake_word": "jarkko",
  "wake_word_required": true,
  "recognizer": { "engine": "vosk", "available": true, "model": "vosk-model-small-es-0.42",
                  "sample_rate": 16000, "loaded": true, "cost": "gratis, offline, sin GPU" },
  "microphone": { "available": true, "capture_rate": 16000, "target_rate": 16000,
                  "default_device": "Varios micrófonos (Senary Audio)", "inputs": [] },
  "stats": { "utterances": 12, "commands": 3, "ignored": 9 },
  "recent": [
    { "text": "arco abre youtube", "wake_word": true, "command": "abre youtube",
      "acted": true, "reason": "command", "at": "19:04:11" }
  ],
  "error": null
}
```

### `POST /api/voice/listen/start` · `POST /api/voice/listen/stop`

Enciende y apaga la escucha manos libres. Respuesta:
`{ "running": true, "started": true, "wake_word": "jarkko" }`.
Si no se puede arrancar, trae `reason` (`stt_disabled`, `recognizer_unavailable`,
`microphone_unavailable`) y `message`.

### `POST /api/voice/listen`

Escucha **una sola vez** (para un botón de micrófono):

```json
{ "seconds": 8, "execute": true, "require_wake_word": null }
```

```json
{
  "heard": true,
  "text": "jarkko cuanta memoria estoy usando",
  "command": "cuanta memoria estoy usando",
  "wake_word": true,
  "seconds": 8,
  "executed": true,
  "chat": { "conversation_id": "…", "message": "Hecho. RAM al 42%…", "status": "success", "actions": [] }
}
```

Con `execute: true` la orden entra por el mismo camino que `/api/chat`, así que
`chat` es una respuesta completa de `ChatResponse`. Si falta la palabra clave y es
obligatoria, no se ejecuta nada y llega `reason: "no_wake_word"`.

### `GET /api/voice/microphone/test?seconds=2`

Diagnóstico: mide el nivel de entrada y explica qué revisar.
`{ "ok": false, "level": 0.5, "diagnosis": "Entra silencio digital…", "device": "…" }`.
Windows **no da ningún error** cuando el micrófono está silenciado, así que si la
interfaz ofrece un botón de micrófono conviene usar esto para avisar al usuario.

### Cómo funciona la escucha

1. Un hilo del backend lee el micrófono y transcribe **en local** con Vosk: la voz
   no se guarda en disco ni sale del equipo.
2. Solo actúa si la frase empieza por la palabra clave. El reconocedor deforma
   «Jarkko» («arco», «zarco»…), así que se aceptan variantes.
3. La orden entra por el **mismo camino que el texto escrito**: hablar no da
   privilegios; una acción de riesgo alto sigue pidiendo confirmación.
4. Mientras JARKKO habla, el micrófono se ignora (si no, se oiría a sí mismo).
5. Si la palabra clave coincide de forma dudosa y la orden no se entiende, JARKKO
   **se calla** en lugar de contestar «no te entendí».

Eventos que emite la escucha:

| `type` | `data` |
| --- | --- |
| `speech.partial` | `{ text }` — transcripción provisional, para subtítulos en vivo |
| `speech.heard` | `{ text, wake_word, command, acted, reason, at }` — frase terminada |

Con `assistant.status` = `listening` al arrancar la escucha, y `thinking` en cuanto
se despacha una orden.

---

## 10. WebSocket `ws://127.0.0.1:8765/ws/events`

Canal de salida para animaciones y feedback en vivo. Al conectar se reciben, en
este orden: un `assistant.status` con `idle`, un `system.status` actual y un
`confirmation.required` por cada confirmación pendiente.

Envoltorio de todos los mensajes:

```json
{
  "type": "assistant.status",
  "data": { "status": "executing" },
  "sequence": 12,
  "timestamp": "2026-09-27T17:52:41.881-05:00"
}
```

`sequence` es creciente por evento (`0` en los mensajes de estado inicial) y sirve
para detectar pérdidas. El cliente puede enviar `ping` para mantener la conexión
(se responde con un `assistant.status` de `data.status = "pong"`); cualquier otro
mensaje entrante se ignora.

### Tipos de evento

| `type` | `data` |
| --- | --- |
| `assistant.status` | `{ status, assistant?, conversation_id? }` |
| `assistant.speaking` | `{ text, engine, voice, cached, phrase_key, audio_url }` — empieza una locución |
| `speech.partial` | `{ text }` — lo que va entendiendo del micrófono |
| `speech.heard` | `{ text, wake_word, command, acted, reason, at }` — frase completa oída |
| `assistant.spoken` | `{ text, engine, voice, cached, phrase_key, played, duration_ms }` — termina |
| `action.planning` | `{ assistant, conversation_id, actions[], confidence }` |
| `action.started` | `{ tool, arguments, risk_level, assistant, conversation_id }` |
| `action.completed` | `{ tool, status, message, risk_level, verified, duration_ms, assistant, conversation_id }` |
| `action.failed` | igual que `action.completed` |
| `confirmation.required` | el objeto `Confirmation` de §7 |
| `system.status` | igual que `GET /api/system/status` |

### Estados del asistente

`idle` · `listening` · `thinking` · `planning` · `executing` · `waiting_confirmation` · `success` · `error`

Secuencia típica de un `POST /api/chat` que ejecuta una acción:

```
thinking → planning → action.planning → executing → action.started
        → action.completed → success → idle
        → assistant.speaking → assistant.spoken
```

Los dos eventos de voz llegan **después** de la respuesta HTTP (la locución no
bloquea la petición) y son los que conviene usar para animar la onda o la boca:
`assistant.speaking` para arrancar la animación y `assistant.spoken` para pararla
(trae el `duration_ms` real del audio, sin contar la espera en cola).

Con confirmación: `thinking → planning → action.planning → waiting_confirmation → confirmation.required`
y, al confirmar: `executing → action.started → action.completed → success → idle`.

`listening` se emite mientras la escucha está activa (ver §9.ter).

`system.status` se publica cada `JARVIS_SYSTEM_STATUS_INTERVAL` segundos (5 por
defecto) **solo si hay clientes conectados**.

Recomendaciones: reconectar con *backoff*; tras reconectar, rehidratar con
`GET /api/actions/pending` y `GET /api/activity`. El WebSocket no sustituye a las
respuestas HTTP: el resultado autorizado de una acción es el cuerpo de la
respuesta, los eventos son para la UI.

---

## 11. Tipos TypeScript sugeridos

```ts
export type Assistant = 'jarkko';               // 'jarvis' y 'ekko' se aceptan como alias
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';
export type ToolCategory = 'browser' | 'applications' | 'files' | 'system';

export type ActionStatus =
  | 'success' | 'error' | 'conflict' | 'denied'
  | 'rejected' | 'awaiting_confirmation' | 'skipped' | 'cancelled';

export type ChatStatus = 'success' | 'error' | 'awaiting_confirmation' | 'no_action';

export type AssistantState =
  | 'idle' | 'listening' | 'thinking' | 'planning'
  | 'executing' | 'waiting_confirmation' | 'success' | 'error';

export interface ErrorDetail {
  code: string | null;
  message: string | null;
  field: string | null;
}

export interface ActionResult {
  tool: string;
  status: ActionStatus;
  message: string;
  risk_level: RiskLevel;
  arguments: Record<string, unknown>;
  data: Record<string, unknown>;
  verified: boolean | null;
  verification_detail: string | null;
  confirmation_id: string | null;
  duration_ms: number | null;
  error: ErrorDetail | null;
}

export interface Confirmation {
  confirmation_id: string;
  tool: string;
  arguments: Record<string, unknown>;
  risk_level: RiskLevel;
  description: string;
  assistant: Assistant;
  conversation_id: string | null;
  created_at: string;
  expires_at: string;
}

export interface ChatResponse {
  conversation_id: string;
  assistant: Assistant;
  message: string;
  status: ChatStatus;
  actions: ActionResult[];
  requires_confirmation: boolean;
  confirmations: Confirmation[];
  intent: {
    reply: string;
    actions: { tool: string; arguments: Record<string, unknown>; reason: string }[];
    confidence: number;
    source: string;
    needs_clarification: boolean;
    matched_rule: string | null;
  } | null;
}

export interface FileEntry {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size: number | null;
  modified: string | null;
}

export interface SystemStatus {
  system: string;
  memory_percent: number;
  disk_percent: number;
  running_processes: number;
  cpu_percent: number;
  uptime_seconds: number;
  timestamp: string;
}

export interface ToolParameter {
  name: string;
  type: 'string' | 'integer' | 'boolean' | 'path' | 'url';
  description: string;
  required: boolean;
  default?: unknown;
  must_exist?: boolean | null;
  kind?: 'any' | 'file' | 'directory';
}

export interface Tool {
  name: string;
  description: string;
  category: ToolCategory;
  risk_level: RiskLevel;
  enabled: boolean;
  parameters: ToolParameter[];
  examples: string[];
}

export type EventType =
  | 'assistant.status' | 'assistant.speaking' | 'assistant.spoken'
  | 'speech.partial' | 'speech.heard'
  | 'action.planning' | 'action.started'
  | 'action.completed' | 'action.failed' | 'confirmation.required' | 'system.status';

export interface SpeakingEvent {
  text: string;
  engine: 'elevenlabs' | 'windows';
  voice: string;
  cached: boolean;
  phrase_key: string | null;
  audio_url: string | null;
}

export interface SpokenEvent extends Omit<SpeakingEvent, 'audio_url'> {
  played: boolean;
  duration_ms: number | null;
}

export interface AssistantEvent<T = Record<string, unknown>> {
  type: EventType;
  data: T;
  sequence: number;
  timestamp: string;
}
```

---

## 12. Ejemplo de cliente mínimo

```ts
const BASE = 'http://127.0.0.1:8765';

export async function sendMessage(
  message: string,
  assistant: Assistant = 'jarkko',
  conversationId?: string,
): Promise<ChatResponse> {
  const response = await fetch(`${BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, assistant, conversation_id: conversationId ?? null }),
  });
  if (!response.ok) throw new Error(`chat ${response.status}`);
  return response.json();
}

export async function confirm(confirmationId: string, approved: boolean): Promise<ActionResult> {
  const response = await fetch(`${BASE}/api/actions/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirmation_id: confirmationId, approved }),
  });
  if (response.status === 404) throw new Error('La confirmación caducó o ya se usó.');
  return response.json();
}

export function connectEvents(onEvent: (event: AssistantEvent) => void): WebSocket {
  const socket = new WebSocket('ws://127.0.0.1:8765/ws/events');
  socket.onmessage = (raw) => onEvent(JSON.parse(raw.data));
  return socket; // reconectar con backoff en onclose
}
```

---

## 12.bis Arranque: un solo ejecutable

`frontend/release/Jarkko/Jarkko.exe` **arranca este backend por su cuenta** desde
`electron/main.cjs`, sin ventana de consola, y lo detiene al cerrarse. No hay que
lanzar nada aparte.

Reglas de ese arranque, útiles para el frontend:

- si `GET /api/health` ya responde en 8765, se reutiliza el backend existente y
  **no** se mata al salir (solo se cierra el que la propia app levantó);
- el arranque tarda unos segundos: la ventana se muestra enseguida y el backend
  llega después, así que la interfaz debe tolerar que las primeras llamadas fallen
  y reintentar `GET /api/health` en lugar de decidir a la primera que no hay
  servicio;
- una segunda ejecución del `.exe` enfoca la ventana existente en vez de abrir otra;
- registro del backend: `%TEMP%\jarkko-backend.log`.

---

## 13. Qué **no** hay (y no habrá) en esta API

- Ningún endpoint ni herramienta que ejecute comandos arbitrarios
  (`run_command`, PowerShell, CMD). Abrir PowerShell abre una ventana vacía para
  el usuario, y exige confirmación.
- Ninguna operación fuera del home del usuario (salvo raíces extra configuradas
  explícitamente por el propio usuario en el `.env`).
- Ninguna escritura silenciosa sobre archivos existentes.
- Ningún borrado: `delete_file` está definida pero deshabilitada.
- Ninguna clave de API ni contraseña en respuestas, logs o base de datos (tampoco
  la de ElevenLabs: solo se lee del entorno).
- Ningún gasto automático de cuota de voz: la síntesis de pago solo ocurre cuando el
  usuario pide construir el caché.

Si el frontend necesita una capacidad nueva, se añade como **herramienta
registrada** con su nivel de riesgo, no como endpoint genérico.
