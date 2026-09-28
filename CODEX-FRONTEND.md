# JARKKO · Reparto de trabajo: Codex (frontend) · Claude (backend)

Este documento es el acuerdo entre los dos agentes que trabajan en este repositorio.
La regla es una sola y no admite excepciones:

| Carpeta | Dueño | El otro agente |
| --- | --- | --- |
| `frontend/` | **Codex** | Claude no crea ni borra archivos aquí |
| `backend/` | **Claude** | Codex no toca nada de aquí, ni para "arreglar" un endpoint |
| raíz (`README`, este archivo) | compartido | avisar antes de reescribir |

El contrato entre las dos mitades es **`backend/API_CONTRACT.md`**. Es la única
fuente de verdad: si algo no está ahí, no existe. Si el frontend necesita un
endpoint nuevo, se pide a Claude; **no se inventa ni se simula**.

---

## 1. Copia esto en Codex

> Trabajas **exclusivamente** dentro de `frontend/` del proyecto JARKKO
> (`C:\Users\Usuario\Desktop\Jarvis - Ekko`). Eres el dueño del frontend: vistas,
> componentes, estado, conectores con el backend y empaquetado de Electron.
>
> **Prohibido:** crear, editar o borrar cualquier archivo de `backend/`. Si crees que
> falta un endpoint o que uno responde mal, **no lo parchees ni lo simules**:
> escríbelo en `frontend/PENDIENTE-BACKEND.md` como una petición concreta (endpoint,
> método, payload que necesitas y para qué vista) y sigue con el resto.
>
> **Lee primero, sin excepción:**
> 1. `backend/API_CONTRACT.md` — contrato completo. Tiene los tipos TypeScript
>    sugeridos (§11) y un cliente mínimo de ejemplo (§12). Úsalos como base.
> 2. `backend/README.md` — cómo arranca el backend y qué hace cada capa.
> 3. `frontend/src/services/api.ts` — la capa de conexión actual. **Funciona y está
>    verificada contra el backend real**: amplíala, no la reescribas desde cero.
>
> **Stack, sin cambios:** Electron + Vite + React + TypeScript. No añadas
> dependencias pesadas (nada de Redux, MUI, Tailwind nuevo, ni librerías de gráficas)
> sin justificarlo en el PR. La UI está en español (es-PE).
>
> **Estado actual del backend (todo esto ya funciona y está probado):**
> - Escucha en `http://127.0.0.1:8765`. WebSocket en `ws://127.0.0.1:8765/ws/events`.
> - Arranca solo: `frontend/electron/main.cjs` lo lanza como proceso hijo, espera a
>   `GET /api/health`, reutiliza el que ya esté vivo y lo mata al cerrar. **Un solo
>   ejecutable, una sola ventana** — esto es un requisito del usuario, no lo rompas.
> - 16 herramientas reales (abrir apps y webs, listar/buscar archivos, crear carpeta,
>   mover/copiar/renombrar, estado del sistema). Sin IA de pago: un parser de reglas
>   en español entiende las órdenes.
> - Voz: habla con voz local de Windows (gratis, ilimitada) y escucha por micrófono
>   con Vosk. El reconocimiento es el modelo pequeño: **transcribe mal las frases
>   largas**. La UI tiene que hacer ese fallo visible y llevadero, no esconderlo.
> - `frontend/.env` ya tiene `VITE_USE_MOCK_API=false`. **El modo de muestra jamás
>   puede volver a ser el valor por defecto de una build.**
>
> **Tus tareas, por orden de valor:**
>
> 1. **Conectores de verdad, con estados honestos.** Cliente tipado para todos los
>    endpoints del contrato (§2–§9.ter) y un único hook/servicio de WebSocket con
>    reconexión y *backoff*. Tres estados visibles y distinguibles en la UI:
>    *conectado* · *reconectando* · *backend caído* (con el motivo). Hoy un fallo de
>    red se disfraza de respuesta vacía; eso no puede pasar.
>
> 2. **Flujo de confirmaciones (§7).** Es el corazón de la seguridad del producto:
>    llega `confirmation.required` por WebSocket → diálogo que muestre herramienta,
>    argumentos, riesgo y qué va a pasar → `POST /api/actions/confirm`. Al abrir la
>    app, rehidrata los pendientes con `GET /api/actions/pending`. Una confirmación
>    caduca y es de un solo uso: refleja los dos casos.
>
> 3. **Panel de conversación como fuente de verdad.** `POST /api/chat` devuelve
>    `status` (`success`, `error`, `awaiting_confirmation`, `no_action`) y `actions[]`
>    con `tool`, `message`, `risk_level`, `verified` y `data`. Pinta la diferencia:
>    lo que se ejecutó y se **verificó** en disco no se ve igual que un "no te
>    entendí". Enseña el historial real (`GET /api/activity`), no uno inventado.
>
> 4. **Voz en la interfaz, sin mentir.** Eventos: `speech.partial` (texto parcial en
>    vivo), `speech.heard` (frase final, con `acted` y `reason` cuando la ignoró),
>    `assistant.speaking` / `assistant.spoken`, `assistant.status`
>    (`idle` · `listening` · `thinking` · `planning` · `executing` ·
>    `waiting_confirmation` · `success` · `error`). Controles reales:
>    `POST /api/voice/listen/start` · `/stop`, `GET /api/voice/listen/status`,
>    `GET /api/voice/microphone/test` para un medidor de nivel de micro.
>    Si el micro está silenciado o entra silencio digital, dilo con esas palabras.
>
> 5. **Vistas completas:** Inicio (esfera + estado + micro), Conversación,
>    Herramientas (`GET /api/tools`: nombre, descripción, riesgo, habilitada,
>    `confirmation_threshold` — **léelo, no lo asumas**), Archivos
>    (`/api/files/search`, `/api/files/list`, `/api/files/known-folders`; sin rutas
>    escritas a mano), Actividad (`/api/activity` + `/api/activity/stats`) y Ajustes
>    (solo lo que el backend expone de verdad: voz, escucha, umbral de confirmación).
>
> 6. **Estabilidad visual.** El usuario se ha quejado dos veces de que "se ve feo"
>    al pulsar el micro y de que la esfera se mueve raro. Reglas: una sola animación
>    por estado, sin saltos de layout al cambiar de estado, `prefers-reduced-motion`
>    respetado **de forma local** (nunca un reset global con `!important`: en esta
>    máquina Windows tiene las animaciones desactivadas y un reset global deja la
>    interfaz muerta), foco visible y navegación por teclado.
>
> 7. **Calidad.** `npm run typecheck` y `npm run lint` limpios. Tests con Vitest de
>    los mapeadores de `api.ts` y del reductor de eventos del WebSocket, con payloads
>    **copiados literalmente** del contrato. Que `npm run package:win` siga
>    produciendo un ejecutable que arranca el backend solo.
>
> **Cómo verificar que algo funciona:** con el backend en marcha
> (`cd backend; .venv\Scripts\python.exe -m uvicorn app.main:app --port 8765`) y
> `curl`/DevTools contra el endpoint real. Una captura de pantalla no es una prueba.
>
> Empieza por leer `backend/API_CONTRACT.md` y `frontend/src/services/api.ts`, y
> dime qué encuentras roto antes de tocar nada.

---

## 2. Lo que hago yo (Claude) en el backend

Por orden, y con tests que lo demuestren:

1. **Entender de verdad lo que se dice.** *(hecho — 178 tests en verde)*
   - Cortesía y rodeos: «¿me puedes abrir YouTube?», «quiero que abras…»,
     «necesito que busques…» ya valen igual que la orden seca.
   - Sinónimos de consulta: «cuánta memoria tengo», «cómo va el disco».
   - Rescate de frases destrozadas por el micrófono: si el verbo se rompe pero el
     nombre sobrevive («pueden saber youtube»), se abre lo evidente. Con freno: solo
     frases cortas, sin negaciones, un único objetivo y **nunca** una consola.
   - Charla: saludos, «¿me escuchas?», «¿qué puedo hacer?», «gracias».
   - Nunca se queda callado: si no entiende, lo dice.
2. **Reconocimiento mejor (lo que más duele).** Evaluar `whisper.cpp` con el modelo
   `small` frente al Vosk actual sobre grabaciones reales del usuario, y cambiar el
   motor solo si gana de forma medible. Sigue siendo gratis y local.
3. **Memoria de conversación.** Que «ábrela» o «y ahora ciérrala» sepan de qué se
   estaba hablando.
4. **Más herramientas útiles** (subir/bajar volumen, bloquear el equipo, papelera,
   captura de pantalla), cada una con su nivel de riesgo y su verificación.
5. **Voz de identidad de ElevenLabs** cacheada: 28 frases fijas, 875 caracteres,
   una sola vez, dentro del plan gratuito. Falta que el usuario pegue su clave en
   `backend/.env` (`JARVIS_ELEVENLABS_API_KEY=`).
6. **Endpoints que Codex pida** en `frontend/PENDIENTE-BACKEND.md`.

## 3. Reglas que ninguno de los dos rompe

- El modelo de IA **nunca** toca PowerShell, CMD ni el sistema operativo. No existe
  ninguna herramienta `run_command` genérica y no se va a crear.
- Nada de rutas escritas a mano (`C:\Users\Usuario\…`): las carpetas del usuario se
  preguntan al backend.
- Ninguna acción destructiva se ejecuta sin confirmación explícita del usuario.
- El registro de actividad no guarda contraseñas ni claves de API.
- Cero dependencias de pago y cero modelos locales pesados: esta máquina no tiene
  GPU potente.
