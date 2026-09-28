<#
    Activa el cerebro de JARKKO (Groq, gratis).

    Con esto JARKKO puede opinar, resumir, conversar y entender ordenes que no
    tengan una regla escrita.  El plan gratuito da 1.000 peticiones al dia y 30
    por minuto, sin tarjeta.

    Consigue tu clave en https://console.groq.com/keys (empieza por "gsk_").
    La clave no se muestra en pantalla ni se escribe en ningun log.

        .\activar-cerebro-jarkko.ps1
#>

[CmdletBinding()]
param(
    [string]$Modelo = "openai/gpt-oss-120b"
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$env_file = Join-Path $raiz ".env"
$python = Join-Path $raiz ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "No encuentro el entorno de Python en $python" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $env_file)) {
    Copy-Item (Join-Path $raiz ".env.example") $env_file
    Write-Host "Cree backend\.env a partir de .env.example"
}

Write-Host ""
Write-Host "Cerebro de JARKKO - Groq (gratis, sin tarjeta)" -ForegroundColor Cyan
Write-Host "Saca tu clave en https://console.groq.com/keys  (empieza por gsk_)"
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

# Se reescriben SOLO las tres lineas del proveedor; el resto del .env queda igual.
$valores = @{
    "JARVIS_AI_PROVIDER" = "groq"
    "JARVIS_AI_API_KEY"  = $clave
    "JARVIS_AI_MODEL"    = $Modelo
}
$lineas = Get-Content $env_file
$vistas = @{}
$nuevas = foreach ($linea in $lineas) {
    $puesta = $linea
    foreach ($nombre in $valores.Keys) {
        if ($linea -match "^\s*$nombre\s*=") {
            $puesta = "$nombre=$($valores[$nombre])"
            $vistas[$nombre] = $true
        }
    }
    $puesta
}
foreach ($nombre in $valores.Keys) {
    if (-not $vistas.ContainsKey($nombre)) { $nuevas = $nuevas + "$nombre=$($valores[$nombre])" }
}

# UTF-8 sin BOM: con BOM, la primera variable del .env se leeria con basura delante.
$texto = ($nuevas -join "`r`n") + "`r`n"
[System.IO.File]::WriteAllText($env_file, $texto, (New-Object System.Text.UTF8Encoding($false)))
$clave = $null
Write-Host "Clave guardada en backend\.env (ese archivo esta en .gitignore)." -ForegroundColor Green

Write-Host ""
Write-Host "Probando la clave contra Groq..." -ForegroundColor Cyan
Push-Location $raiz
try {
    & $python -c @'
import asyncio, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from app.config import get_settings
from app.providers.groq import GroqProvider

get_settings.cache_clear()
s = get_settings()
p = GroqProvider(api_key=s.ai_api_key, model=s.ai_model)
r = asyncio.run(p.check())
if r.get("ok"):
    print(f"OK - el modelo {r['model']} responde.")
else:
    print(f"FALLO - {r.get('reason')}")
    sys.exit(1)
'@
    $codigo = $LASTEXITCODE
} finally {
    Pop-Location
}

Write-Host ""
if ($codigo -eq 0) {
    Write-Host "Cerebro activado. Cierra y abre JARKKO." -ForegroundColor Green
    Write-Host "Las ordenes normales (abrir, archivos, sistema) siguen resolviendose en tu equipo," -ForegroundColor DarkGray
    Write-Host "sin salir a internet. Solo lo que hay que pensar usa la nube." -ForegroundColor DarkGray
    Write-Host "Para apagarlo en cualquier momento: JARVIS_AI_PROVIDER=mock en backend\.env" -ForegroundColor DarkGray
} else {
    Write-Host "Revisa la clave o prueba otro modelo:" -ForegroundColor Yellow
    Write-Host "  .\activar-cerebro-jarkko.ps1 -Modelo openai/gpt-oss-20b" -ForegroundColor Yellow
}
exit $codigo
