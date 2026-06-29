$ErrorActionPreference = 'Stop'

$backendDir = 'C:\Users\Administrator\Documents\intec_sis_aca\backend'
$pythonExe = Join-Path $backendDir '.venv\Scripts\python.exe'
$logDir = Join-Path $backendDir 'logs'
$logFile = Join-Path $logDir 'uvicorn-8002.log'
$watchdogLog = Join-Path $logDir 'backend-watchdog.log'

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

function Write-WatchdogLog {
    param([string]$Message)
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $watchdogLog -Value "$timestamp $Message"
}

$listener = Get-NetTCPConnection -LocalPort 8002 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    Write-WatchdogLog "Backend already listening on 8002 with PID $($listener.OwningProcess)."
    exit 0
}

if (-not (Test-Path $pythonExe)) {
    Write-WatchdogLog "Python executable not found: $pythonExe"
    exit 1
}

Write-WatchdogLog "Backend not listening on 8002. Starting uvicorn."

$command = "& '$pythonExe' -m uvicorn app.main:app --host 127.0.0.1 --port 8002 --proxy-headers --forwarded-allow-ips 127.0.0.1,204.168.250.176 --timeout-keep-alive 300 *> '$logFile'"
Start-Process -FilePath 'powershell.exe' `
    -WindowStyle Hidden `
    -WorkingDirectory $backendDir `
    -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $command) | Out-Null

Start-Sleep -Seconds 6

$listener = Get-NetTCPConnection -LocalPort 8002 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    Write-WatchdogLog "Backend started on 8002 with PID $($listener.OwningProcess)."
    exit 0
}

Write-WatchdogLog "Backend failed to start on 8002."
exit 1
