param(
  [Parameter(Mandatory = $true)]
  [string]$SqlServer,

  [string]$Database = "TITULACION_INTEC",
  [string]$SqlcmdPath = "sqlcmd",
  [string]$SqlUser = "",
  [string]$SqlPassword = "",
  [string]$BackupDirectory = ".\backups",
  [switch]$SkipBackup,
  [switch]$TrustServerCertificate,
  [switch]$IncludePatchV9Rubricas
)

$ErrorActionPreference = "Stop"

function Invoke-SqlcmdChecked {
  param(
    [Parameter(Mandatory = $true)]
    [string]$TargetDatabase,

    [Parameter(Mandatory = $true)]
    [string[]]$ExtraArgs
  )

  $authArgs = @()
  if ($SqlUser) {
    if (-not $SqlPassword) {
      throw "SqlPassword es obligatorio cuando se usa SqlUser."
    }
    $authArgs = @("-U", $SqlUser, "-P", $SqlPassword)
  } else {
    $authArgs = @("-E")
  }

  $tlsArgs = @()
  if ($TrustServerCertificate) {
    $tlsArgs = @("-C")
  }

  & $SqlcmdPath @("-S", $SqlServer, "-d", $TargetDatabase, "-b", "-I") @tlsArgs @authArgs @ExtraArgs
  if ($LASTEXITCODE -ne 0) {
    throw "sqlcmd fallo con codigo $LASTEXITCODE."
  }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$sqlRoot = Join-Path $repoRoot "backend\sql"

if (-not $SkipBackup) {
  New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null
  $backupPath = Join-Path (Resolve-Path $BackupDirectory) "$Database-$(Get-Date -Format yyyyMMdd-HHmmss).bak"
  $backupSql = "BACKUP DATABASE [$Database] TO DISK = N'$($backupPath.Replace("'", "''"))' WITH INIT, CHECKSUM, COMPRESSION;"
  Write-Host "Creando respaldo previo: $backupPath"
  Invoke-SqlcmdChecked -TargetDatabase "master" -ExtraArgs @("-Q", $backupSql)
}

$scripts = @(
  "TITULACION_INTEC_PORTAL_COMPLETO_PROMPT_02.sql",
  "TITULACION_INTEC_COMPLEMENTO_MECANISMOS_COMPLEXIVO_DEFENSA.sql",
  "TITULACION_INTEC_COMPLEMENTO_PORTAL_GRUPOS_EVALUADORES.sql",
  "TITULACION_INTEC_COMPLEMENTO_DASHBOARD_RUBRICAS_AUDITORIA.sql",
  "TITULACION_INTEC_COMPLEMENTO_DOCUMENTOS_ACTAS_TITULOS.sql",
  "TITULACION_INTEC_FIX_NUMERO_REFRENDACION_DESDE_ACTA.sql",
  "TITULACION_INTEC_PROMPT_08_CIERRE.sql",
  "TITULACION_INTEC_QA_SMOKE.sql"
)

if ($IncludePatchV9Rubricas) {
  $scripts = @($scripts[0..($scripts.Count - 2)] + "TITULACION_INTEC_PARCHE_V9_EVALUADORES_VARIABLES_RUBRICAS.sql" + $scripts[-1])
}

foreach ($scriptName in $scripts) {
  $scriptPath = Join-Path $sqlRoot $scriptName
  if (-not (Test-Path $scriptPath)) {
    Write-Warning "No existe $scriptPath. Se omite."
    continue
  }

  Write-Host "Aplicando $scriptName"
  Invoke-SqlcmdChecked -TargetDatabase $Database -ExtraArgs @("-i", $scriptPath)
}

Write-Host "Migracion y smoke test completados para $Database."
