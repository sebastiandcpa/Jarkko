const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { createPackage } = require('@electron/asar');

if (process.platform !== 'win32' || process.arch !== 'x64') {
  throw new Error('Este paquete se genera en Windows x64.');
}

const root = path.resolve(__dirname, '..');
const release = path.join(root, 'release');
const portable = path.join(release, 'Jarkko');
const stage = path.join(release, '.app-stage');
const electron = path.join(root, 'node_modules', 'electron');
const runtime = path.join(electron, 'dist');
const backendSource = path.resolve(root, '..', 'backend');

function pythonRuntime() {
  const cfg = path.join(backendSource, '.venv', 'pyvenv.cfg');
  const venvHome = fs.existsSync(cfg)
    ? fs.readFileSync(cfg, 'utf8').match(/^home\s*=\s*(.+)$/m)?.[1]?.trim()
    : null;
  const bundled = path.join(
    process.env.USERPROFILE || '',
    '.cache', 'codex-runtimes', 'codex-primary-runtime',
    'dependencies', 'python',
  );
  const candidates = [process.env.JARKKO_PYTHON_RUNTIME, venvHome, bundled].filter(Boolean);
  const found = candidates.find((dir) => fs.existsSync(path.join(dir, 'python.exe')));
  if (!found) {
    throw new Error('Necesito Python 3.12 para preparar la versión portátil. Define JARKKO_PYTHON_RUNTIME con la carpeta de Python.');
  }
  return found;
}

function copyBackend(destination) {
  const pythonSource = pythonRuntime();
  const pythonTarget = path.join(destination, 'python');
  const dependencies = path.join(backendSource, '.venv', 'Lib', 'site-packages');
  if (!fs.existsSync(path.join(backendSource, 'app', 'main.py')) || !fs.existsSync(dependencies)) {
    throw new Error('Faltan el backend o sus dependencias instaladas.');
  }
  fs.mkdirSync(pythonTarget, { recursive: true });
  for (const file of ['python.exe', 'python3.dll', 'python312.dll', 'vcruntime140.dll', 'vcruntime140_1.dll', 'LICENSE.txt']) {
    const source = path.join(pythonSource, file);
    if (fs.existsSync(source)) fs.copyFileSync(source, path.join(pythonTarget, file));
  }
  fs.cpSync(path.join(pythonSource, 'DLLs'), path.join(pythonTarget, 'DLLs'), { recursive: true });
  fs.cpSync(path.join(pythonSource, 'Lib'), path.join(pythonTarget, 'Lib'), {
    recursive: true,
    filter: (source) => {
      const relative = path.relative(path.join(pythonSource, 'Lib'), source);
      return !relative.split(path.sep).some((part) => part === 'site-packages' || part === '__pycache__');
    },
  });
  fs.cpSync(dependencies, path.join(pythonTarget, 'Lib', 'site-packages'), {
    recursive: true,
    filter: (source) => !path.relative(dependencies, source).split(path.sep).includes('__pycache__'),
  });
  fs.cpSync(path.join(backendSource, 'app'), path.join(destination, 'app'), {
    recursive: true,
    filter: (source) => !path.relative(path.join(backendSource, 'app'), source).split(path.sep).includes('__pycache__'),
  });
  const models = path.join(backendSource, 'data', 'models');
  if (fs.existsSync(models)) fs.cpSync(models, path.join(destination, 'data', 'models'), { recursive: true });
  const example = path.join(backendSource, '.env.example');
  if (fs.existsSync(example)) fs.copyFileSync(example, path.join(destination, '.env.example'));
}

function assertInsideRelease(target) {
  const relative = path.relative(release, target);
  const workspaceRelative = path.relative(path.resolve(root, '..'), target);
  if (!relative || relative.startsWith('..') || path.isAbsolute(relative) ||
      !workspaceRelative || workspaceRelative.startsWith('..') || path.isAbsolute(workspaceRelative)) {
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
  copyBackend(path.join(portable, 'backend'));
  fs.writeFileSync(
    path.join(stage, 'package.json'),
    JSON.stringify({ name: 'jarkko', version: '0.3.0', main: 'electron/main.cjs' }),
  );

  const resources = path.join(portable, 'resources');
  fs.rmSync(path.join(resources, 'default_app.asar'), { force: true });
  await createPackage(stage, path.join(resources, 'app.asar'));
  fs.renameSync(path.join(portable, 'electron.exe'), path.join(portable, 'Jarkko.exe'));
  fs.writeFileSync(
    path.join(portable, 'LEEME.txt'),
    'JARKKO - aplicación portátil\r\n\r\nAbre Jarkko.exe. La aplicación iniciará su servicio local automáticamente.\r\nPara compartirla, copia o comprime la carpeta Jarkko completa; conserva juntos el ejecutable y la carpeta backend.\r\nNo hace falta instalar un IDE ni Python en el otro equipo.\r\n',
    'utf8',
  );
  fs.rmSync(stage, { recursive: true, force: true });
  console.log(`Aplicación lista: ${path.join(portable, 'Jarkko.exe')}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
