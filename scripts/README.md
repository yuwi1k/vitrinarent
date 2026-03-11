# Скрипты резервного копирования БД

Резервные копии PostgreSQL (база `vitrina_db`) создаются через `pg_dump` внутри контейнера Docker.

## Создание бекапа

**Windows (PowerShell):**
```powershell
.\scripts\backup_db.ps1
```

**Linux/macOS:**
```bash
chmod +x scripts/backup_db.sh
./scripts/backup_db.sh
```

Файлы сохраняются в папку `backups/` с именем вида `vitrina_db_YYYYMMDD_HHMMSS.sql`.

Перед запуском убедитесь, что контейнеры подняты: `docker compose up -d` (или уже запущены).

## Восстановление из бекапа

**Windows:**
```powershell
.\scripts\restore_db.ps1 backups\vitrina_db_20250311_120000.sql
# или без аргумента — будет выбран последний по времени файл из backups/
.\scripts\restore_db.ps1
```

**Linux/macOS:**
```bash
./scripts/restore_db.sh backups/vitrina_db_20250311_120000.sql
# или
./scripts/restore_db.sh
```

Восстановление перезаписывает текущее состояние БД. Скрипт запросит подтверждение.

## Автоматический бекап каждые 24 часа

В `docker-compose.yml` добавлен сервис **`backup`**: контейнер раз в 24 часа создаёт дамп БД и сохраняет его в `backups/`.

При запуске `docker compose up -d` сервис `backup` поднимается вместе с `db` и `app`. Первый бекап делается сразу после старта, следующие — каждые 86400 секунд (24 часа). Логи можно смотреть так:

```bash
docker compose logs -f backup
```

Интервал можно изменить через переменную окружения (в `docker-compose.yml` или `.env`):  
`BACKUP_INTERVAL_SECONDS=86400` (по умолчанию 24 часа).

## Ручная автоматизация (альтернатива)

- **Windows:** Планировщик заданий — запуск `powershell -File "…\scripts\backup_db.ps1"` по расписанию.
- **Linux:** cron, например ежедневно в 3:00:  
  `0 3 * * * /path/to/vitrinarent/scripts/backup_db.sh`

Папка `backups/` добавлена в `.gitignore`, чтобы дампы не попадали в репозиторий.
