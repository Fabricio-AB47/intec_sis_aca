param(
    [string]$TaskName = "INTEC - Sincronización nocturna de notas Moodle",
    [string]$StartTime = "00:00"
)

$ErrorActionPreference = "Stop"

$Runner = (Resolve-Path (Join-Path $PSScriptRoot "run_moodle_grade_sync.ps1")).Path
$PowerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$TaskCommand = "`"$PowerShell`" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$Runner`" -Apply"

& schtasks.exe /Create /F /SC DAILY /ST $StartTime /TN $TaskName /TR $TaskCommand
if ($LASTEXITCODE -ne 0) {
    throw "No se pudo registrar la tarea programada. Ejecute PowerShell con los permisos requeridos."
}

Write-Host "Tarea registrada: $TaskName"
Write-Host "Horario diario: $StartTime"
Write-Host "Ejecutor: $Runner"
