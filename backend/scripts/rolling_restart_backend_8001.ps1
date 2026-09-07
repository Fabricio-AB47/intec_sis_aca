[CmdletBinding()]
param(
    [int]$Port = 8001,
    [int]$ExpectedWorkers = 2
)

$ErrorActionPreference = 'Stop'
$backendDir = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $backendDir '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "No se encontro Python del backend: $pythonExe"
}

# Ejecuta las migraciones idempotentes antes de sustituir workers en servicio.
& $pythonExe -c "from app.services.screen_access import warm_screen_access_catalog; warm_screen_access_catalog()"
if ($LASTEXITCODE -ne 0) {
    throw 'No se pudo sincronizar el catalogo de pantallas.'
}

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
    Select-Object -First 1
$managerPid = [int]$listener.OwningProcess
$manager = Get-CimInstance Win32_Process -Filter "ProcessId = $managerPid"
$resolvedBackend = [System.IO.Path]::GetFullPath($backendDir)
if (-not $manager -or [string]$manager.CommandLine -notlike "*$resolvedBackend*" -or [string]$manager.CommandLine -notmatch "--port(?:=|\s+)$Port(?:\s|$)") {
    throw "El proceso que escucha en $Port no corresponde a este backend."
}

function Get-Workers {
    @(
        Get-CimInstance Win32_Process | Where-Object {
            [int]$_.ParentProcessId -eq $managerPid -and $_.Name -match '^python(?:\.exe)?$'
        }
    )
}

function Wait-Replacement {
    param([int[]]$PreviousIds)
    $deadline = (Get-Date).AddSeconds(90)
    do {
        Start-Sleep -Milliseconds 750
        $workers = @(Get-Workers)
        $newWorkers = @($workers | Where-Object { [int]$_.ProcessId -notin $PreviousIds })
        if ($workers.Count -ge $ExpectedWorkers -and $newWorkers.Count -gt 0) {
            try {
                $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 8
                if ($response.StatusCode -eq 200) {
                    return
                }
            }
            catch {
                # El worker nuevo aun esta iniciando.
            }
        }
    } while ((Get-Date) -lt $deadline)
    throw 'Uvicorn no reemplazo el worker dentro del tiempo esperado.'
}

$originalWorkers = @(Get-Workers)
if ($originalWorkers.Count -lt $ExpectedWorkers) {
    throw "Se esperaban $ExpectedWorkers workers y solo se encontraron $($originalWorkers.Count)."
}

foreach ($worker in $originalWorkers) {
    $previousIds = @(Get-Workers | ForEach-Object { [int]$_.ProcessId })
    Stop-Process -Id ([int]$worker.ProcessId) -ErrorAction Stop
    Wait-Replacement -PreviousIds $previousIds
}

$finalWorkers = @(Get-Workers)
Write-Host "Backend actualizado gradualmente: $($finalWorkers.Count) workers activos en el puerto $Port."
