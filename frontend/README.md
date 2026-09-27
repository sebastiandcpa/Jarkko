# Interfaz JARVIS · EKKO

Aplicación de escritorio con dos identidades visuales basadas en las referencias del proyecto: JARVIS en azul y EKKO en verde. La pantalla de inicio incorpora escenas, orbe animado, acciones rápidas, estado del sistema y conversación lateral. Las otras pantallas comparten navegación y componentes.

## Paquete portátil de Windows

En Windows x64, desde esta carpeta:

```powershell
npm install
npm run package:win
```

El comando genera `release/Jarvis-Ekko-0.2.0-Windows-x64.zip`. La persona destinataria solo debe descomprimirlo y ejecutar `Jarvis Ekko/Jarvis Ekko.exe`. No necesita instalar Node.js, Python ni un IDE. El ZIP incluye el runtime de Electron y todos los archivos visuales. Debe conservar la carpeta completa.

## Desarrollo

Requiere Node.js. `npm run dev` inicia la interfaz en `http://127.0.0.1:5173`. `npm run desktop` la compila y abre en Electron. `npm run typecheck` y `npm run build` verifican la compilación.

## Estructura

- `src/app/App.tsx`: navegación, estado compartido y pantallas.
- `src/components/Orb.tsx`: orbe animado.
- `src/styles.css`: temas, composición, animación y tamaños de ventana.
- `src/assets/`: escenas de JARVIS y EKKO.
- `src/mock/data.ts`: conversación, tareas, archivos, herramientas y actividad de muestra.
- `src/services/api.ts`: endpoints HTTP con respaldo de datos de muestra.
- `electron/main.cjs`: ventana de escritorio y límites de navegación.
- `scripts/package-win.cjs`: ensamblado y ZIP portátil para Windows x64.

## Estado funcional

Puedes navegar, enviar mensajes de prueba, cambiar estados de tareas, buscar en datos de muestra, confirmar acciones simuladas y cambiar entre JARVIS y EKKO. La identidad elegida se guarda localmente.

El ZIP abre la interfaz completa, pero aún no controla el PC, reconoce voz ni conecta un modelo de IA real. El directorio `../backend` contiene trabajo en curso y no está incluido en el paquete portátil. La interfaz usa datos de muestra por defecto. Existe una capa HTTP prevista para un servicio local en `http://127.0.0.1:8765`; cuando ese servicio esté listo se podrán integrar acciones reales con sus permisos correspondientes.
