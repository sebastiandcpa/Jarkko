# Arranca el backend de JARKKO y, si existe, abre la aplicación de escritorio.
#
#   .\start-jarkko.ps1              backend + app
#   .\start-jarkko.ps1 -SoloBackend solo el backend
#   .\start-jarkko.ps1 -SinEscucha  sin abrir el micrófono
#
# La app empaquetada (frontend/release/Jarkko/Jarkko.exe) NO arranca el backend por
# su cuenta: sin esto, no tiene con quién hablar.

param(
    [switch]$SoloBackend,
    [switch]$SinEscucha
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$backend = $PSScriptRoot
$proyecto = Split-Path $backend -Parent
$python = Join-Path $backend ".venv\Scripts\python.exe"
$app = Join-Path $proyecto "frontend\release\Jarkko\Jarkko.exe"
$salud = "http://127.0.0.1:8765/api/health"

if (-not (Test-Path $python)) {
    Write-Host "No encuentro el entorno virtual en $python" -ForegroundColor Red
    Write-Host "Crealo con:  py -3.12 -m venv .venv ; .\.venv\Scripts\Activate.ps1 ; pip install -r requirements.txt"
    exit 1
}

# ¿Ya está en marcha?
$yaVivo = $false
try {
    Invoke-RestMethod -Uri $salud -TimeoutSec 2 | Out-Null
    $yaVivo = $true
    Write-Host "El backend ya estaba en marcha." -ForegroundColor Yellow
} catch {
    $yaVivo = $false
}

if (-not $yaVivo) {
    $env:JARVIS_STT_AUTOSTART = if ($SinEscucha) { "false" } else { "true" }
    Write-Host "Arrancando el backend de JARKKO..." -ForegroundColor Cyan
    Start-Process -FilePath $python `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8765" `
        -WorkingDirectory $backend

    $listo = $false
    foreach ($intento in 1..30) {
        Start-Sleep -Milliseconds 700
        try {
            $respuesta = Invoke-RestMethod -Uri $salud -TimeoutSec 2
            $listo = $true
            break
        } catch {
            continue
        }
    }
    if (-not $listo) {
        Write-Host "El backend no respondio en 20 s. Revisa la ventana que se abrio." -ForegroundColor Red
        exit 2
    }
    Write-Host ("JARKKO {0} listo: {1} herramientas, voz: {2}" -f `
        $respuesta.version, $respuesta.tools_registered, ($respuesta.voice.engines -join " + ")) -ForegroundColor Green
}

# Estado de la escucha
try {
    $escucha = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/voice/listen/status" -TimeoutSec 3
    if ($escucha.running) {
        Write-Host ("Escucha activa. Di: {0}, abre YouTube" -f $escucha.wake_word) -ForegroundColor Green
    } else {
        Write-Host "Escucha apagada (POST /api/voice/listen/start para encenderla)." -ForegroundColor Yellow
    }
    if (-not $escucha.microphone.available) {
        Write-Host "Aviso: no hay microfono utilizable." -ForegroundColor Yellow
    } elseif ($escucha.running) {
        # Windows entrega silencio sin dar error cuando el micro esta muteado:
        # mas vale avisar ahora que dejar a JARKKO sordo sin explicacion.
        try {
            $nivel = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/voice/microphone/test?seconds=1" -TimeoutSec 8
            if (-not $nivel.ok) {
                # Mensajes en ASCII: la consola de Windows no siempre muestra acentos.
                Write-Host "Aviso: el microfono no entrega senal (nivel $($nivel.level))." -ForegroundColor Yellow
                Write-Host "  JARKKO hablara, pero no te oira. Revisa en Windows:" -ForegroundColor Yellow
                Write-Host "   1) Configuracion > Sistema > Sonido > Entrada: habla y mira si se mueve la barra" -ForegroundColor Yellow
                Write-Host "   2) la tecla de funcion que silencia el microfono del portatil" -ForegroundColor Yellow
                Write-Host "   3) el mezclador de volumen (nivel de entrada a 0)" -ForegroundColor Yellow
                Write-Host "  Detalle: GET /api/voice/microphone/test" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "No pude medir el nivel del microfono." -ForegroundColor Yellow
        }
    }
} catch {
    Write-Host "No pude consultar el estado de la escucha." -ForegroundColor Yellow
}

if ($SoloBackend) { exit 0 }

if (Test-Path $app) {
    Write-Host "Abriendo la aplicacion..." -ForegroundColor Cyan
    Start-Process -FilePath $app
} else {
    Write-Host "No encuentro la app en $app" -ForegroundColor Yellow
    Write-Host "Abre el chat en http://127.0.0.1:8765/docs mientras tanto."
}
