const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { createPackage } = require('@electron/asar');

if (process.platform !== 'win32' || process.arch !== 'x64') {
  throw new Error('Este paquete se genera en Windows x64.');
}

const root = path.resolve(__dirname, '..');
const release = path.join(root, 'release');
const portable = path.join(release, 'Jarvis Ekko');
const stage = path.join(release, '.app-stage');
const zip = path.join(release, 'Jarvis-Ekko-0.2.0-Windows-x64.zip');
const electron = path.join(root, 'node_modules', 'electron');
const runtime = path.join(electron, 'dist');

function assertInsideRelease(target) {
  const relative = path.relative(release, target);
  if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) {
    throw new Error(`Ruta de salida inesperada: ${target}`);
  }
}

async function main() {
  if (!fs.existsSync(path.join(runtime, 'electron.exe'))) {
    console.log('Descargando el runtime de Electron...');
    execFileSync(process.execPath, [path.join(electron, 'install.js')], { stdio: 'inherit' });
  }
  if (!fs.existsSync(path.join(root, 'dist', 'index.html'))) {
    throw new Error('Falta dist/index.html. Ejecuta npm run build.');
  }

  fs.mkdirSync(release, { recursive: true });
  for (const target of [portable, stage]) {
    assertInsideRelease(target);
    fs.rmSync(target, { recursive: true, force: true });
  }
  fs.cpSync(runtime, portable, { recursive: true });
  fs.mkdirSync(stage, { recursive: true });
  fs.cpSync(path.join(root, 'dist'), path.join(stage, 'dist'), { recursive: true });
  fs.cpSync(path.join(root, 'electron'), path.join(stage, 'electron'), { recursive: true });
  fs.writeFileSync(
    path.join(stage, 'package.json'),
    JSON.stringify({ name: 'jarvis-ekko', version: '0.2.0', main: 'electron/main.cjs' }),
  );

  const resources = path.join(portable, 'resources');
  fs.rmSync(path.join(resources, 'default_app.asar'), { force: true });
  await createPackage(stage, path.join(resources, 'app.asar'));
  fs.renameSync(path.join(portable, 'electron.exe'), path.join(portable, 'Jarvis Ekko.exe'));
  fs.rmSync(stage, { recursive: true, force: true });
  fs.rmSync(zip, { force: true });
  execFileSync('tar.exe', ['-a', '-c', '-f', zip, '-C', release, 'Jarvis Ekko'], { stdio: 'inherit' });
  console.log(`Paquete listo: ${zip}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
