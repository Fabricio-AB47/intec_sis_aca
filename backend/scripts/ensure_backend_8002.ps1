$ErrorActionPreference = 'Stop'

$port = 8007
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

$listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    Write-WatchdogLog "Backend already listening on $port with PID $($listener.OwningProcess)."
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

Start-Sleep -Seconds 6

$listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    Write-WatchdogLog "Backend started on $port with PID $($listener.OwningProcess)."
    exit 0
}

Write-WatchdogLog "Backend failed to start on $port."
exit 1
