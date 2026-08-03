$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$port = 8002

if (-not (Test-Path $python)) {
  throw "No se encontro el entorno virtual en $python. Ejecuta desde la raiz: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
}

$listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
  Select-Object -First 1

if ($listener) {
  $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
  $commandLine = if ($process) { [string]$process.CommandLine } else { "" }

  if ($commandLine -like "*$repoRoot*" -and $commandLine -like "*uvicorn*") {
    Write-Host "Reiniciando backend anterior del proyecto (PID $($listener.OwningProcess))..."
    Stop-Process -Id $listener.OwningProcess -Force

    $deadline = (Get-Date).AddSeconds(8)
    do {
      Start-Sleep -Milliseconds 250
      $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    } while ($listener -and (Get-Date) -lt $deadline)

    if ($listener) {
      throw "No se pudo liberar el puerto $port. Proceso actual: $($listener.OwningProcess)."
    }
  } else {
    $owner = if ($process) { "$($process.Name) (PID $($process.ProcessId))" } else { "PID $($listener.OwningProcess)" }
    throw "El puerto $port esta ocupado por otro programa: $owner."
  }
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Set-Location $PSScriptRoot
& $python -m uvicorn app.main:app --host 127.0.0.1 --port $port --reload
