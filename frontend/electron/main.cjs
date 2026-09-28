const { app, BrowserWindow, dialog } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");

const appId = "com.sebastiandcpa.jarkko";
app.setAppUserModelId(appId);

const BACKEND_HOST = "127.0.0.1";
const BACKEND_PORT = 8765;
const HEALTH_URL = `http://${BACKEND_HOST}:${BACKEND_PORT}/api/health`;
const STARTUP_TIMEOUT_MS = 40000;

/** Proceso del backend, solo si lo arrancamos nosotros. */
let backendProcess = null;
/** Si el backend ya estaba en marcha, no es nuestro y no se cierra al salir. */
let backendWasAlreadyRunning = false;
let mainWindow = null;

// Una sola instancia: abrir el ejecutable otra vez enfoca la ventana existente
// en lugar de abrir otra.
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  });
}

function backendCandidates() {
  const fromEnv = process.env.JARKKO_BACKEND_DIR;
  const exeDir = path.dirname(app.getPath("exe"));
  return [
    fromEnv,
    // La versión portátil debe usar primero el servicio y Python que viajan
    // junto al ejecutable, incluso si se abre desde el proyecto fuente.
    path.join(exeDir, "backend"),
    // desarrollo: frontend/electron -> frontend -> raíz del proyecto
    path.join(__dirname, "..", "..", "backend"),
    // empaquetado: <raíz>/frontend/release/Jarkko/Jarkko.exe
    path.join(exeDir, "..", "..", "..", "backend"),
    path.join(exeDir, "..", "..", "..", "..", "backend"),
  ].filter(Boolean);
}

function resolveBackend() {
  for (const dir of backendCandidates()) {
    if (!fs.existsSync(path.join(dir, "app", "main.py"))) continue;
    const candidates = [
      process.env.JARKKO_PYTHON,
      path.join(dir, "python", "python.exe"),
      path.join(dir, ".venv", "Scripts", "python.exe"),
    ].filter(Boolean);
    const python = candidates.find((candidate) => fs.existsSync(candidate));
    return { dir, python: python || null };
  }
  return { dir: null, python: null };
}

function ping(timeoutMs = 1500) {
  return new Promise((resolve) => {
    const request = http.get(HEALTH_URL, { timeout: timeoutMs }, (response) => {
      response.resume();
      resolve(response.statusCode === 200);
    });
    request.on("timeout", () => {
      request.destroy();
      resolve(false);
    });
    request.on("error", () => resolve(false));
  });
}

async function waitForBackend(deadline) {
  while (Date.now() < deadline) {
    if (await ping()) return true;
    if (backendProcess && backendProcess.exitCode !== null) return false;
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  return false;
}

async function startBackend() {
  // Si ya responde alguien en el puerto, se reutiliza: así arrancar la app con
  // el backend ya abierto a mano no levanta un segundo proceso.
  if (await ping()) {
    backendWasAlreadyRunning = true;
    return { ok: true, reused: true };
  }

  const { dir, python } = resolveBackend();
  if (!dir) {
    return {
      ok: false,
      reason:
        "No encuentro la carpeta backend junto a la aplicación.\n\n" +
        "JARKKO necesita su backend en la misma carpeta del proyecto. " +
        "Si moviste el ejecutable, déjalo en su sitio o define la variable " +
        "JARKKO_BACKEND_DIR.",
    };
  }
  if (!python) {
    return {
      ok: false,
      reason:
        `Falta Python junto al backend en:\n${dir}\\python\n\n` +
        "Si ejecutas el proyecto desde el código fuente, crea el entorno con:\n" +
        "  py -3.12 -m venv .venv\n" +
        "  .\\.venv\\Scripts\\Activate.ps1\n" +
        "  pip install -r requirements.txt",
    };
  }

  const logFile = path.join(os.tmpdir(), "jarkko-backend.log");
  const log = fs.createWriteStream(logFile, { flags: "a" });
  log.write(`\n--- ${new Date().toISOString()} arranque desde la app ---\n`);

  backendProcess = spawn(
    python,
    [
      "-m",
      "uvicorn",
      "app.main:app",
      "--host",
      BACKEND_HOST,
      "--port",
      String(BACKEND_PORT),
    ],
    {
      cwd: dir,
      // Sin ventana de consola: el usuario solo debe ver la app.
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  backendProcess.stdout.pipe(log);
  backendProcess.stderr.pipe(log);
  backendProcess.on("error", (error) => log.write(`spawn error: ${error}\n`));
  backendProcess.on("exit", (code) => {
    log.write(`backend terminado con código ${code}\n`);
    backendProcess = null;
  });

  const ready = await waitForBackend(Date.now() + STARTUP_TIMEOUT_MS);
  if (!ready) {
    return {
      ok: false,
      reason:
        "El backend no respondió a tiempo.\n\n" +
        `Revisa el registro en:\n${logFile}`,
    };
  }
  return { ok: true, reused: false };
}

function stopBackend() {
  if (!backendProcess || backendWasAlreadyRunning) return;
  const { pid } = backendProcess;
  backendProcess = null;
  if (!pid) return;
  try {
    if (process.platform === "win32") {
      // /T incluye los procesos hijos que pueda haber creado uvicorn.
      spawn("taskkill", ["/pid", String(pid), "/T", "/F"], {
        windowsHide: true,
      });
    } else {
      process.kill(pid, "SIGTERM");
    }
  } catch {
    // La app se está cerrando: no hay nada útil que hacer aquí.
  }
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 900,
    minHeight: 650,
    show: false,
    title: "JARKKO",
    backgroundColor: "#071018",
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });

  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event, url) => {
    const allowed = app.isPackaged
      ? url.startsWith("file://")
      : url.startsWith("http://127.0.0.1:5173/");
    if (!allowed) event.preventDefault();
  });

  if (!app.isPackaged && process.env.ELECTRON_START_URL) {
    void window.loadURL(process.env.ELECTRON_START_URL);
  } else {
    void window.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }

  window.once("ready-to-show", () => window.show());
  window.on("closed", () => {
    mainWindow = null;
  });
  mainWindow = window;
  return window;
}

app.whenReady().then(async () => {
  // La ventana aparece de inmediato; el backend arranca detrás para que abrir
  // la app no se sienta lenta.
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });

  const result = await startBackend();
  if (!result.ok && mainWindow) {
    dialog.showMessageBox(mainWindow, {
      type: "warning",
      title: "JARKKO sin backend",
      message: "La aplicación se abrió, pero su backend no está disponible.",
      detail: result.reason,
      buttons: ["Entendido"],
    });
  }
});

app.on("before-quit", stopBackend);
app.on("will-quit", stopBackend);
process.on("exit", stopBackend);

app.on("window-all-closed", () => {
  stopBackend();
  if (process.platform !== "darwin") app.quit();
});
