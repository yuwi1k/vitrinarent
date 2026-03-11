# Restore PostgreSQL from backup (via Docker Compose)
# Использование: .\scripts\restore_db.ps1 [путь_к_файлу.sql]
# Пример: .\scripts\restore_db.ps1 backups\vitrina_db_20250311_120000.sql

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $ProjectRoot) { $ProjectRoot = (Get-Location).Path }
Set-Location $ProjectRoot

$BackupFile = $args[0]
if (-not $BackupFile) {
    $BackupsDir = Join-Path $ProjectRoot "backups"
    $Latest = Get-ChildItem -Path $BackupsDir -Filter "vitrina_db_*.sql" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $Latest) {
        Write-Error "No backup file specified and no backups found in $BackupsDir"
        exit 1
    }
    $BackupFile = $Latest.FullName
    Write-Host "Using latest backup: $BackupFile"
}

if (-not (Test-Path $BackupFile)) {
    Write-Error "File not found: $BackupFile"
    exit 1
}

Write-Host "Restoring from: $BackupFile"
Write-Host "WARNING: This will replace current database. Continue? (y/N)"
$Confirm = Read-Host
if ($Confirm -ne "y" -and $Confirm -ne "Y") {
    Write-Host "Aborted."
    exit 0
}

Get-Content -Path $BackupFile -Encoding UTF8 -Raw | docker compose exec -T db psql -U postgres vitrina_db

if ($LASTEXITCODE -ne 0) {
    Write-Error "Restore failed."
    exit 1
}
Write-Host "Restore completed."
