param(
  [Parameter(Mandatory = $true)]
  [string]$SqlServer,

  [Parameter(Mandatory = $true)]
  [string]$BackupFile,

  [string]$Database = "TITULACION_INTEC",
  [string]$SqlcmdPath = "sqlcmd",
  [string]$SqlUser = "",
  [string]$SqlPassword = ""
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $BackupFile)) {
  throw "No existe el archivo de respaldo: $BackupFile"
}

$authArgs = @()
if ($SqlUser) {
  if (-not $SqlPassword) {
    throw "SqlPassword es obligatorio cuando se usa SqlUser."
  }
  $authArgs = @("-U", $SqlUser, "-P", $SqlPassword)
} else {
  $authArgs = @("-E")
}

$backupPath = (Resolve-Path $BackupFile).Path.Replace("'", "''")
$rollbackSql = @"
ALTER DATABASE [$Database] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
RESTORE DATABASE [$Database] FROM DISK = N'$backupPath' WITH REPLACE, CHECKSUM;
ALTER DATABASE [$Database] SET MULTI_USER;
"@

Write-Host "Restaurando $Database desde $BackupFile"
& $SqlcmdPath @("-S", $SqlServer, "-d", "master", "-b", "-I") @authArgs @("-Q", $rollbackSql)
if ($LASTEXITCODE -ne 0) {
  throw "Rollback fallo con codigo $LASTEXITCODE."
}

Write-Host "Rollback completado para $Database."
