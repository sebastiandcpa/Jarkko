# Jarkko

Asistente de escritorio con una sola identidad visual. La esfera azul y verde es el centro de la pantalla; los paneles de navegación y conversación aparecen al pulsar sus controles laterales.

## Abrir en Windows sin instalar nada

La aplicación preparada está en `frontend/release/Jarkko/Jarkko.exe`. Para compartirla, copia **la carpeta `Jarkko` completa** a otro equipo Windows x64. La otra persona abre esa carpeta y ejecuta `Jarkko.exe` con doble clic. No necesita un IDE, Node.js ni Python. El ejecutable debe permanecer junto a los demás archivos de su carpeta.

No se crea un ZIP. La interfaz portátil usa datos de muestra: el servicio local de `backend/` todavía no está integrado en el ejecutable y el control real del equipo o por voz no está disponible.

## Código fuente

- `frontend/`: interfaz React y aplicación Electron.
- `backend/`: servicio local en desarrollo.

Para desarrollar la interfaz se necesita Node.js. En `frontend/`, ejecuta `npm install` y `npm run dev`. Para reconstruir la carpeta de Windows x64, ejecuta `npm run package:win`; el resultado aparece en `frontend/release/Jarkko/`.

Consulta `frontend/README.md` para la estructura y las funciones actuales.
