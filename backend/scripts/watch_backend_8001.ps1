[CmdletBinding()]
param(
    [int]$Port = 8001,
    [int]$ExpectedWorkers = 2
)

$ErrorActionPreference = 'Stop'
$taskName = 'intec_sis_aca_backend'
$backendDir = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $backendDir 'logs'
$watchdogLog = Join-Path $logDir 'backend-8001-watchdog.log'

if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

function Write-WatchdogLog {
    param([string]$Message)
    Add-Content -LiteralPath $watchdogLog -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
}

function Get-BackendState {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $listener) {
        return [pscustomobject]@{ Healthy = $false; WorkerCount = 0; Reason = 'sin listener' }
    }

    $managerPid = [int]$listener.OwningProcess
    $workers = @(
        Get-CimInstance Win32_Process | Where-Object {
            [int]$_.ParentProcessId -eq $managerPid -and $_.Name -match '^python(?:\.exe)?$'
        }
    )
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 8
        $httpHealthy = $response.StatusCode -eq 200
    }
    catch {
        $httpHealthy = $false
    }

    $workerCount = $workers.Count
    return [pscustomobject]@{
        Healthy = $httpHealthy -and $workerCount -ge $ExpectedWorkers
        WorkerCount = $workerCount
        Reason = if (-not $httpHealthy) { 'health sin respuesta' } else { "$workerCount worker(s)" }
    }
}

$state = Get-BackendState
if ($state.Healthy) {
    exit 0
}

# Uvicorn puede estar reemplazando un worker; se confirma antes de reiniciar todo.
Start-Sleep -Seconds 10
$state = Get-BackendState
if ($state.Healthy) {
    Write-WatchdogLog "Recuperacion automatica completada ($($state.WorkerCount) workers)."
    exit 0
}

Write-WatchdogLog "Backend degradado: $($state.Reason). Reinicio controlado de la tarea."
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Start-ScheduledTask -TaskName $taskName

$deadline = (Get-Date).AddSeconds(90)
do {
    Start-Sleep -Seconds 2
    $state = Get-BackendState
    if ($state.Healthy) {
        Write-WatchdogLog "Backend recuperado con $($state.WorkerCount) workers."
        exit 0
    }
} while ((Get-Date) -lt $deadline)

Write-WatchdogLog "El backend no se recupero dentro del tiempo esperado: $($state.Reason)."
exit 1
