[CmdletBinding()]
param(
    [switch]$Restart
)

$ErrorActionPreference = 'Stop'

$port = 8002
$backendDir = Split-Path -Parent $PSScriptRoot
$repoDir = Split-Path -Parent $backendDir
$pythonExe = Join-Path $repoDir '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) {
    $pythonExe = Join-Path $backendDir '.venv\Scripts\python.exe'
}
$logDir = Join-Path $backendDir 'logs'
$logFile = Join-Path $logDir "uvicorn-$port.log"
$errorLogFile = Join-Path $logDir "uvicorn-$port-error.log"
$watchdogLog = Join-Path $logDir 'backend-watchdog.log'

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

function Write-WatchdogLog {
    param([string]$Message)
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $watchdogLog -Value "$timestamp $Message"
}

function Get-BackendListener {
    Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

function Wait-BackendReady {
    param([int]$TimeoutSeconds = 45)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $activeListener = Get-BackendListener
        if ($activeListener) {
            try {
                $response = Invoke-WebRequest `
                    -Uri "http://127.0.0.1:$port/health" `
                    -UseBasicParsing `
                    -TimeoutSec 2
                if ($response.StatusCode -eq 200) {
                    return $activeListener
                }
            }
            catch {
                # Uvicorn may already own the port while FastAPI is still loading.
            }
        }

        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)

    return $null
}

$listener = Get-BackendListener
if ($listener -and $Restart) {
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
    $commandLine = [string] $processInfo.CommandLine
    $escapedPythonExe = [regex]::Escape($pythonExe)
    $isProjectBackend = (
        $processInfo.Name -eq 'python.exe' -and
        $commandLine -match "^`"?$escapedPythonExe`"?\s" -and
        $commandLine -match '(app\.main:app|app[\\/]main\.py)' -and
        $commandLine -match '(--port\s+8002|--port=8002)'
    )

    if (-not $isProjectBackend) {
        $message = "Port $port is occupied by PID $($listener.OwningProcess), but it is not the project backend. It was not stopped."
        Write-WatchdogLog $message
        Write-Error $message
        exit 1
    }

    Write-Host "Restarting the backend on port $port (PID $($listener.OwningProcess))..."
    Write-WatchdogLog "Stopping backend PID $($listener.OwningProcess) for a controlled restart."
    Stop-Process -Id $listener.OwningProcess -Force

    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 250
        if (-not (Get-BackendListener)) {
            break
        }
    }

    $listener = Get-BackendListener
    if ($listener) {
        $message = "Port $port did not become available after stopping PID $($listener.OwningProcess)."
        Write-WatchdogLog $message
        Write-Error $message
        exit 1
    }
}

if ($listener) {
    Write-WatchdogLog "Backend already listening on $port with PID $($listener.OwningProcess)."
    Write-Host "Backend already active at http://127.0.0.1:$port (PID $($listener.OwningProcess))."
    Write-Host "Use -Restart only when you need to restart this instance."
    exit 0
}

if (-not (Test-Path $pythonExe)) {
    Write-WatchdogLog "Python executable not found: $pythonExe"
    exit 1
}

Write-WatchdogLog "Backend not listening on $port. Starting uvicorn."

$arguments = @(
    '-m',
    'uvicorn',
    'app.main:app',
    '--host',
    '127.0.0.1',
    '--port',
    "$port",
    '--proxy-headers',
    '--forwarded-allow-ips',
    '127.0.0.1,204.168.250.176',
    '--timeout-keep-alive',
    '300'
)

Start-Process -FilePath $pythonExe `
    -WindowStyle Hidden `
    -WorkingDirectory $backendDir `
    -ArgumentList $arguments `
    -RedirectStandardOutput $logFile `
    -RedirectStandardError $errorLogFile | Out-Null

$listener = Wait-BackendReady
if ($listener) {
    Write-WatchdogLog "Backend started on $port with PID $($listener.OwningProcess)."
    Write-Host "Backend started at http://127.0.0.1:$port (PID $($listener.OwningProcess))."
    exit 0
}

Write-WatchdogLog "Backend failed to start on $port."
if (Test-Path $errorLogFile) {
    Write-Host "Review the startup log: $errorLogFile"
}
exit 1
