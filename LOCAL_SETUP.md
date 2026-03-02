# Запуск без Docker (локальный PostgreSQL)

Если Docker не установлен, поднимите PostgreSQL локально.

## 1. Установка PostgreSQL на Windows

**Через winget (рекомендуется):**
```powershell
winget install PostgreSQL.PostgreSQL
```

Или скачайте установщик: https://www.postgresql.org/download/windows/

При установке задайте пароль пользователя `postgres` и запомните его.

## 2. Создание базы данных

Откройте **pgAdmin** (устанавливается вместе с PostgreSQL) или выполните в PowerShell:

```powershell
# Путь может отличаться, обычно:
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE DATABASE vitrina_db;"
```

(Замените `16` на вашу версию PostgreSQL, если другая.)

## 3. Настройка .env

В корне проекта создайте или отредактируйте файл `.env`:

```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=ваш_пароль_от_postgres
POSTGRES_DB=vitrina_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

## 4. Миграции и запуск

```powershell
cd c:\vitrinarent
.\venv\Scripts\Activate.ps1
alembic -c alembic.ini upgrade head
uvicorn app.main:app --reload
```

После этого приложение будет подключаться к локальной БД.
