param(
    [switch]$Apply,
    [string]$Actor = "TAREA_MOODLE_0000"
)

$ErrorActionPreference = "Stop"

$BackendRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RepositoryRoot = (Resolve-Path (Join-Path $BackendRoot "..")).Path
$Python = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
$SyncScript = Join-Path $BackendRoot "scripts\sync_moodle_grades.py"
$LogDirectory = Join-Path $BackendRoot "logs"
$LogFile = Join-Path $LogDirectory "moodle-grade-sync.log"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "No se encontró el intérprete virtual en $Python"
}

New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
Set-Location -LiteralPath $BackendRoot

$Arguments = @($SyncScript)
if ($Apply) {
    $Arguments += "--apply"
}
$Arguments += @("--actor", $Actor)

$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$Timestamp] Inicio de sincronización Moodle. Modo: $(if ($Apply) { 'aplicar' } else { 'vista previa' })." |
    Tee-Object -FilePath $LogFile -Append

& $Python @Arguments 2>&1 | Tee-Object -FilePath $LogFile -Append
$ExitCode = $LASTEXITCODE

$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$Timestamp] Fin de sincronización Moodle. Código: $ExitCode." |
    Tee-Object -FilePath $LogFile -Append

exit $ExitCode
