$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
  throw "No se encontro el entorno virtual en $python. Ejecuta desde la raiz: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Set-Location $PSScriptRoot
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8007 --reload
