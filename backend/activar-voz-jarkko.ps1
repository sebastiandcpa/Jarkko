<#
    Activa la voz de identidad de JARKKO (ElevenLabs).

    Pide tu clave, la guarda en backend/.env y genera el cache de frases fijas:
    28 frases, 875 caracteres, UNA sola vez.  A partir de ahi ese audio sale del
    disco y no gasta ni un credito mas.

    La clave no se muestra en pantalla ni se escribe en ningun log.

        .\activar-voz-jarkko.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$env_file = Join-Path $raiz ".env"
$python = Join-Path $raiz ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "No encuentro el entorno de Python en $python" -ForegroundColor Red
    Write-Host "Crealo con:  py -3.12 -m venv .venv;  .venv\Scripts\pip install -r requirements.txt"
    exit 1
}
if (-not (Test-Path $env_file)) {
    Copy-Item (Join-Path $raiz ".env.example") $env_file
    Write-Host "Cree backend\.env a partir de .env.example"
}

Write-Host ""
Write-Host "Voz de JARKKO: WEXRePkZGpmcFLvCOaB1" -ForegroundColor Cyan
Write-Host "Necesito tu clave de ElevenLabs (elevenlabs.io -> tu perfil -> API Keys)."
Write-Host "No se vera mientras la escribes y no se mostrara despues." -ForegroundColor DarkGray
$segura = Read-Host "Clave" -AsSecureString
$puntero = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura)
try {
    $clave = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($puntero).Trim()
} finally {
    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($puntero)
}

if ([string]::IsNullOrWhiteSpace($clave)) {
    Write-Host "No escribiste ninguna clave. No cambie nada." -ForegroundColor Yellow
    exit 1
}
if ($clave -match "\s") {
    Write-Host "Esa clave tiene espacios: copiala otra vez completa." -ForegroundColor Yellow
    exit 1
}

# Se reescribe SOLO la linea de la clave; el resto del .env queda igual.
$lineas = Get-Content $env_file
$encontrada = $false
$nuevas = foreach ($linea in $lineas) {
    if ($linea -match "^\s*JARVIS_ELEVENLABS_API_KEY\s*=") {
        $encontrada = $true
        "JARVIS_ELEVENLABS_API_KEY=$clave"
    } else {
        $linea
    }
}
if (-not $encontrada) { $nuevas = $nuevas + "JARVIS_ELEVENLABS_API_KEY=$clave" }

# UTF-8 sin BOM: con BOM, la primera variable del .env se leeria con basura delante.
$texto = ($nuevas -join "`r`n") + "`r`n"
[System.IO.File]::WriteAllText($env_file, $texto, (New-Object System.Text.UTF8Encoding($false)))
$clave = $null
Write-Host "Clave guardada en backend\.env (ese archivo esta en .gitignore)." -ForegroundColor Green

Write-Host ""
Write-Host "Calculando el coste antes de gastar nada..." -ForegroundColor Cyan
Push-Location $raiz
try {
    & $python -m app.voice.build_cache --dry-run
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "No se pudo verificar la voz (mira el mensaje de arriba)." -ForegroundColor Yellow
        Write-Host "Lo mas comun: la voz no esta anadida a 'My Voices' en tu cuenta." -ForegroundColor Yellow
        exit $LASTEXITCODE
    }

    Write-Host ""
    $respuesta = Read-Host "Genero el cache con esos caracteres? (s/n)"
    if ($respuesta -notmatch "^[sSyY]") {
        Write-Host "Nada generado. La clave queda guardada para cuando quieras." -ForegroundColor Yellow
        exit 0
    }

    & $python -m app.voice.build_cache
    $codigo = $LASTEXITCODE
} finally {
    Pop-Location
}

if ($codigo -eq 0) {
    Write-Host ""
    Write-Host "Listo. Cierra y abre JARKKO: ya suena con su voz." -ForegroundColor Green
    Write-Host "JARVIS_ELEVENLABS_ALLOW_LIVE sigue en false, asi que no puede gastar mas cuota sola." -ForegroundColor DarkGray
}
exit $codigo
