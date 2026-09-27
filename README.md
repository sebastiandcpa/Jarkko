# JARVIS · EKKO

Asistente de escritorio con dos identidades visuales: JARVIS (azul, ciudad nocturna) y EKKO (verde, entorno natural). Incluye navegación, conversación, tareas, archivos, calendario, conocimiento, herramientas, actividad y configuración.

## Abrir en Windows sin instalar nada

Descarga `Jarvis-Ekko-0.2.0-Windows-x64.zip`, descomprímelo y haz doble clic en `Jarvis Ekko/Jarvis Ekko.exe`. La otra persona no necesita Node.js, Python ni un IDE. Conserva toda la carpeta descomprimida junto al ejecutable.

El ZIP contiene la interfaz de escritorio. Las respuestas y los datos son de muestra mientras no se conecte un servicio local. El reconocimiento de voz y las acciones sobre el equipo todavía no están habilitados en este paquete.

## Código fuente

- `frontend/`: interfaz React, diseño JARVIS/EKKO y contenedor Electron.
- `backend/`: trabajo en curso para el servicio local; no se incluye ni se ejecuta en el ZIP portátil.

Para desarrollar la interfaz se necesita Node.js. En `frontend/`, ejecuta `npm install` y `npm run dev`. Para regenerar el ZIP en Windows x64, ejecuta `npm run package:win`; el resultado aparece en `frontend/release/`.

Consulta `frontend/README.md` para la estructura y las funciones actuales.
