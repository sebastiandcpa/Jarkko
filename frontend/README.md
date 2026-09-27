# Jarkko

Interfaz de escritorio de Jarkko. La esfera azul y verde ocupa el centro de la pantalla; la navegación y la conversación se abren al pulsar los controles de los bordes. Cuatro satélites visibles recorren lentamente la órbita. Al activar el micro, la esfera cambia suavemente de forma y aumenta su brillo.

## Aplicación lista para Windows

En Windows x64, desde esta carpeta:

```powershell
npm install
npm run package:win
```

El comando genera la carpeta `release/Jarkko/`, con `Jarkko.exe` y los archivos que necesita. Para usarla en otro equipo Windows x64, copia **toda la carpeta Jarkko**, ábrela y haz doble clic en `Jarkko.exe`. No hace falta instalar un IDE, Node.js ni Python para ejecutar la interfaz. El proyecto ya no genera un ZIP.

## Desarrollo

Requiere Node.js. `npm run dev` inicia la interfaz en `http://127.0.0.1:5173`. `npm run desktop` la compila y abre en Electron. `npm run typecheck` y `npm run build` verifican la compilación.

## Estructura

- `src/app/App.tsx`: navegación, estado compartido y pantallas.
- `src/components/JarkkoOrb.tsx`: esfera principal.
- `src/jarkko.css`: composición de Jarkko y tamaños de ventana.
- `src/assets/`: sala y esfera de Jarkko.
- `src/mock/data.ts`: conversación, tareas, archivos, herramientas y actividad de muestra.
- `src/services/api.ts`: endpoints HTTP con respaldo de datos de muestra.
- `electron/main.cjs`: ventana de escritorio y límites de navegación.
- `scripts/package-win.cjs`: ensamblado de la carpeta portátil para Windows x64.

## Estado funcional

Puedes navegar, enviar mensajes de prueba, cambiar estados de tareas, buscar en datos de muestra y confirmar acciones simuladas.

La carpeta portátil abre la interfaz completa, pero aún no controla el PC, reconoce voz ni conecta un modelo de IA real. El directorio `../backend` contiene trabajo en curso y no está incluido en la aplicación portátil. La interfaz usa datos de muestra por defecto. Existe una capa HTTP prevista para un servicio local en `http://127.0.0.1:8765`; cuando ese servicio esté listo se podrán integrar acciones reales con sus permisos correspondientes.
