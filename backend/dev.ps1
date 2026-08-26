[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$fastapi = Join-Path $repoRoot '.venv\Scripts\fastapi.exe'
$portUtilities = Join-Path $PSScriptRoot 'scripts\backend_port_utils.ps1'
$port = 8002

. $portUtilities

if (-not (Test-Path $python)) {
    throw "No se encontro el entorno virtual en $python. Ejecuta desde la raiz: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
}

$listener = Get-ProjectBackendListeners -Port $port | Select-Object -First 1
if ($listener) {
    Write-Host "Cerrando la instancia anterior del backend en el puerto $port (PID $($listener.OwningProcess))..."
    Stop-ProjectBackendOnPort -Port $port -RepoDir $repoRoot | Out-Null
}

$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

Set-Location $PSScriptRoot
Write-Host "Iniciando FastAPI con recarga en http://127.0.0.1:$port ..."

if (Test-Path $fastapi) {
    & $fastapi dev app/main.py --host 127.0.0.1 --port $port
}
else {
    & $python -m fastapi dev app/main.py --host 127.0.0.1 --port $port
}
