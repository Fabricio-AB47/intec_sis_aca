param(
    [string]$TaskName = "INTEC - Cambios de notas Moodle",
    [ValidateRange(1, 60)]
    [int]$IntervalMinutes = 5
)

$ErrorActionPreference = "Stop"

$BackendRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$EnvironmentFile = Join-Path $BackendRoot ".env"

function Get-EnvironmentValue {
    param([Parameter(Mandatory = $true)][string]$Name)

    if (-not (Test-Path -LiteralPath $EnvironmentFile)) {
        return ""
    }

    $prefix = "$Name="
    $line = Get-Content -LiteralPath $EnvironmentFile |
        Where-Object {
            $trimmed = $_.Trim()
            -not $trimmed.StartsWith("#") -and $trimmed.StartsWith($prefix)
        } |
        Select-Object -Last 1
    if ($null -eq $line) {
        return ""
    }

    return $line.Trim().Substring($prefix.Length).Trim().Trim('"').Trim("'")
}

$ApplyEnabled = (Get-EnvironmentValue -Name "MOODLE_GRADE_SYNC_APPLY_ENABLED").ToLowerInvariant()
$ChangesEnabled = (Get-EnvironmentValue -Name "MOODLE_GRADE_SYNC_CHANGES_ENABLED").ToLowerInvariant()
$Mappings = Get-EnvironmentValue -Name "MOODLE_GRADE_SYNC_MAPPINGS"

if ($ApplyEnabled -notin @("true", "1", "yes", "on")) {
    throw "La escritura automática no está habilitada. Configure MOODLE_GRADE_SYNC_APPLY_ENABLED=true."
}
if ($ChangesEnabled -notin @("true", "1", "yes", "on")) {
    throw "La detección de cambios no está habilitada. Configure MOODLE_GRADE_SYNC_CHANGES_ENABLED=true."
}
if ([string]::IsNullOrWhiteSpace($Mappings)) {
    throw "No existen relaciones autorizadas. Configure MOODLE_GRADE_SYNC_MAPPINGS=curso_moodle:periodo_intec antes de instalar la tarea."
}
foreach ($Mapping in $Mappings.Split(',')) {
    if ($Mapping.Trim() -notmatch '^\d+\s*:\s*\d+$') {
        throw "MOODLE_GRADE_SYNC_MAPPINGS contiene una relación inválida: $($Mapping.Trim())."
    }
}

$Runner = (Resolve-Path (Join-Path $PSScriptRoot "run_moodle_grade_sync.ps1")).Path
$PowerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$TaskCommand = (
    "`"$PowerShell`" -NoProfile -NonInteractive -ExecutionPolicy Bypass " +
    "-File `"$Runner`" -Apply -Actor `"TAREA_MOODLE_CAMBIOS`""
)

& schtasks.exe /Create /F /SC MINUTE /MO $IntervalMinutes /TN $TaskName /TR $TaskCommand
if ($LASTEXITCODE -ne 0) {
    throw "No se pudo registrar la tarea periódica. Ejecute PowerShell con los permisos requeridos."
}

Write-Host "Tarea registrada: $TaskName"
Write-Host "Intervalo: cada $IntervalMinutes minuto(s)"
Write-Host "Alcance: únicamente calificaciones de la sección Evaluación"
Write-Host "Ejecutor: $Runner"
