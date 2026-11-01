# PostgreSQL backup (Windows PowerShell).
# Usage: ./backup_postgres.ps1 [-DatabaseUrl $env:DATABASE_URL] [-BackupDir .\backups] [-KeepDays 14]
param(
  [string]$DatabaseUrl = $env:DATABASE_URL,
  [string]$BackupDir = ".\backups",
  [int]$KeepDays = 14
)

if (-not $DatabaseUrl) {
  Write-Error "DATABASE_URL (or -DatabaseUrl) is required."
  exit 1
}

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$dumpFile = Join-Path $BackupDir "db_$timestamp.sql"
$archiveFile = Join-Path $BackupDir "db_$timestamp.sql.gz"

# pg_dump writes bytes directly to -f (PowerShell '>' would re-encode the stream).
& pg_dump --dbname="$DatabaseUrl" --no-password --format=plain --file="$dumpFile"
if ($LASTEXITCODE -ne 0) {
  Write-Error "pg_dump failed with exit code $LASTEXITCODE."
  exit $LASTEXITCODE
}

# Windows 10+ ships bsdtar, which can emit gzip.
& tar -czf $archiveFile -C $BackupDir (Split-Path $dumpFile -Leaf)
if ($LASTEXITCODE -ne 0) {
  Write-Error "Compression failed with exit code $LASTEXITCODE."
  exit $LASTEXITCODE
}
Remove-Item $dumpFile

Get-ChildItem $BackupDir -Filter "db_*.sql.gz" |
  Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDays) } |
  Remove-Item -Force

Write-Host "Backup created: $archiveFile"
