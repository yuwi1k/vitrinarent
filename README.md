## Vitrina Rent — каталог коммерческой недвижимости

Внутренний сайт‑каталог для агентов: поиск объектов, карточки с фото и документами, дашборд менеджеров, выгрузка фида Авито.

- **Backend**: FastAPI, SQLAlchemy 2 (async), PostgreSQL  
- **UI**: Jinja2‑шаблоны, Bootstrap/Tabler, адаптивная вёрстка  
- **Админка**: SQLAdmin + кастомный дашборд `/dashboard`  
- **Интеграция**: полный XML‑фид Авито (Коммерческая недвижимость)

---

## 1. Структура проекта

- `app/` — код приложения
  - `main.py` — точка входа FastAPI
  - `models.py` — модели БД (`Property`, `PropertyImage`, `PropertyDocument`)
  - `routers.py` — публичные страницы (`/`, `/search`, `/property/{slug}`, `/faq`, `/avito.xml`)
  - `dashboard.py` — дашборд менеджеров (`/dashboard/...`)
  - `admin_views.py` — SQLAdmin (`/admin/...`)
  - `services.py` — логика поиска
  - `feed.py` — генерация XML‑фидов Авито
  - `file_utils.py` — работа с файлами/папками и ресайз изображений
  - `database.py` — подключение к PostgreSQL (async/sync)
  - `config.py` — настройки из `.env`
  - `admin_password.py` / `settings_store.py` — пароль админа и настройки фида
- `templates/` — Jinja2‑шаблоны (публичные + дашборд + SQLAdmin)
- `static/` — статика (CSS/JS/шрифты) и загруженные файлы (`static/uploads/...`)
- `migrations/` — миграции Alembic
- `tests/` — pytest‑тесты
- `Dockerfile`, `docker-compose.yml` — образы приложения и PostgreSQL

---

## 2. Требования

- Python 3.11+ (разрабатывалось под 3.11/3.12)
- PostgreSQL 14+  
- pip / venv  
- (опционально) Docker + docker‑compose

---

## 3. Быстрый запуск локально (без Docker)

```bash
cd c:\vitrinarent
python -m venv venv
.\venv\Scripts\Activate.ps1   # Windows PowerShell
pip install -r requirements.txt
```

### 3.1. PostgreSQL

Создай БД (пример на Windows):

```powershell
psql -U postgres -c "CREATE DATABASE vitrina_db;"
```

### 3.2. Настройка `.env`

Скопируй `.env.example` в `.env` и заполни:

```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=пароль
POSTGRES_DB=vitrina_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

SESSION_SECRET_KEY=случайная_строка
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin

SITE_URL=http://127.0.0.1:8000
YANDEX_MAPS_API_KEY=

ENVIRONMENT=development
```

### 3.3. Миграции и запуск

```bash
alembic -c alembic.ini upgrade head
uvicorn app.main:app --reload
```

Приложение будет доступно на `http://127.0.0.1:8000`.

- Публичный сайт: `/`
- Поиск: `/search`
- Карточка объекта: `/property/{slug_or_id}`
- FAQ: `/faq`
- Публичный упрощённый фид Авито: `/avito.xml`
- Дашборд менеджеров: `/dashboard` (нужна авторизация)
- SQLAdmin: `/admin`

---

## 4. Авторизация и дашборд

1. Зайди на `/admin`.
2. Логин/пароль берутся из `.env` (`ADMIN_USERNAME` / `ADMIN_PASSWORD`) или файла `data/.admin_password`.
3. После успешного логина:
   - доступен SQLAdmin, модели и BaseView «Папки объектов»;
   - в дашборде (`/dashboard`) доступны:
     - главная с отчётами;
     - список объектов (`/dashboard/properties`);
     - формы создания/редактирования/копирования объекта;
     - управление файлами (`/dashboard/folders`);
     - настройки (контакты для фида) и смена пароля.

Пароль админа можно сменить в `/dashboard/settings/password` — он запишется в `data/.admin_password`.

---

## 5. Работа с объектами и файлами

### 5.1. Модель `Property`

Основные поля:

- `title` — название объекта
- `slug` — ЧПУ‑URL (уникальный)
- `description` — описание (с санитизацией HTML)
- `price` — цена
- `area` — площадь
- `address` — адрес (используется в поиске и фиде)
- `deal_type` — «Аренда» / «Продажа»
- `category` — тип (Офис, Торговая площадь, Склад, Здание и т.д.)
- `is_active` — активен ли объект
- `show_on_main` / `main_page_order` — показ и порядок на главной
- `latitude` / `longitude` — координаты для карты
- `parent_id` — иерархия (здание → помещения)
- `avito_object_type`, `avito_data` — тип и параметры для Авито
- `floors_total`, `floor_number`, `power_kw`, `ceiling_height` — доп. характеристики

Связанные сущности:

- `PropertyImage` — фото галереи
- `PropertyDocument` — прикреплённые документы

Файлы складываются в `static/uploads/properties/{улица}/{id_название}/Фото|Документы`.

### 5.2. Дашборд

- **Создание / редактирование**: вкладки `Основное`, `Коммерция`, `Медиа`, `Авито`, `Настройки`.
- **Копирование**:
  - создаётся новый объект;
  - копируются главное фото, все фото из галереи и документы в новую папку;
  - в форме редактирования новой копии можно поштучно удалять фото и документы.
- **Удаление**:
  - можно удалить объект вместе с дочерними или оставить дочерние как корневые;
  - после успешного удаления из БД папка объекта (с фото/доками) удаляется с диска.

---

## 6. Поиск

Логика в `app.services.build_search_query` и роуте `/search`.

Фильтры:

- текстовый поиск по `title` и `address`;
- тип сделки (`Аренда` / `Продажа`);
- категория;
- цена и площадь.

Для цены и площади введённые значения используются как **центр диапазона**:

- если заполнен `min_price` и/или `max_price` — считаем центр и берём окно ±30% (0.7–1.3) от центра;
- аналогично для `min_area` / `max_area`.

Сортировка на странице поиска:

- сначала новые / старые;
- цена по возрастанию / убыванию;
- площадь по возрастанию / убыванию.

---

## 7. Фид Авито

Модуль `app.feed`:

- `generate_avito_feed(properties)` — упрощённый фид для `/avito.xml`;
- `generate_avito_feed_full(properties)` — полный фид для `/dashboard/export/avito` (для загрузки на Авито).

Ключевые особенности:

- контакты (имя менеджера и телефон) берутся из `settings_store` (`data/settings.json`) или `.env`;
- используются отдельные шаблоны для «Продам» и «Сдам»;
- в `<Images>` попадает до 40 фото:
  - главное фото `main_image`;
  - все картинки из галереи `PropertyImage`, с преобразованием путей в абсолютные URL `SITE_URL + /static/...`.

Для корректной работы фида в продакшене **обязательно**:

- выставить актуальный `SITE_URL` в `.env` (с https и реальным доменом);
- обеспечить публичный доступ к `SITE_URL/static/...`.

---

## 8. Тесты

Запуск pytest (из venv):

```bash
cd c:\vitrinarent
.\venv\Scripts\Activate.ps1
python -m pytest tests/ -v
```

Покрываются:

- health‑эндпоинты;
- базовые публичные маршруты;
- редиректы дашборда без сессии;
- базовая структура XML фида;
- логика построения запроса поиска (`build_search_query`).

---

## 9. Деплой в продакшн (кратко)

Один из типовых вариантов:

1. Арендовать VPS (Ubuntu 22.04+), установить Docker и docker‑compose.
2. Склонировать репозиторий на сервер.
3. Создать `.env` на основе `.env.example` с боевыми значениями.
4. Поднять PostgreSQL через `docker-compose up -d` или использовать внешний кластер.
5. Собрать и запустить приложение:
   ```bash
   docker build -t vitrinarent-app .
   docker run -d --name vitrinarent-app --env-file .env -p 8000:8000 vitrinarent-app
   ```
6. Настроить Nginx как обратный прокси на `127.0.0.1:8000` и выпустить TLS‑сертификат (Let's Encrypt).
7. Выполнить миграции Alembic на сервере.

Подробнее по деплою см. комментарии в `Dockerfile`, `docker-compose.yml` и коде `app.main` (health‑чек и проверка секретов).

---

## 10. Полезные ссылки по коду

- Публичные роуты: `app/routers.py`
- Дашборд: `app/dashboard.py`, `templates/dashboard/*.html`
- SQLAdmin: `app/admin_views.py`
- Файлы и папки: `app/file_utils.py`, `templates/dashboard/folders.html`, `templates/dashboard/folder_view.html`
- Фид Авито: `app/feed.py`, `templates/dashboard/form.html` (вкладка «Авито»)

