# Backup PostgreSQL (vitrina_db) via Docker Compose
# Запуск: .\scripts\backup_db.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $ProjectRoot) { $ProjectRoot = (Get-Location).Path }
Set-Location $ProjectRoot

$BackupsDir = Join-Path $ProjectRoot "backups"
if (-not (Test-Path $BackupsDir)) {
    New-Item -ItemType Directory -Path $BackupsDir | Out-Null
}

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupFile = Join-Path $BackupsDir "vitrina_db_$Timestamp.sql"

Write-Host "Creating backup: $BackupFile"
docker compose exec -T db pg_dump -U postgres vitrina_db | Set-Content -Path $BackupFile -Encoding UTF8

if ($LASTEXITCODE -ne 0) {
    Write-Error "Backup failed (pg_dump exited with $LASTEXITCODE). Is 'db' container running?"
    exit 1
}

Write-Host "Backup saved: $BackupFile"
Get-Item $BackupFile | Select-Object Name, Length, LastWriteTime
