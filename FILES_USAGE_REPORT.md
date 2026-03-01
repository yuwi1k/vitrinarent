# Отчёт об использовании файлов проекта Vitrina Real Estate

Проверка: какие файлы реально используются в коде и шаблонах, какие — нет.

---

## 1. Python-модули (`app/`)

| Файл | Использование |
|------|----------------|
| `main.py` | Точка входа приложения (uvicorn). Импортирует: database, admin_views, routers, dashboard. |
| `database.py` | Импортируется: main, models, migrations/env.py. |
| `models.py` | Импортируется: database (Base), routers, dashboard, admin_views, services, migrations/env.py. |
| `routers.py` | Подключается в main. Импортирует: database (get_db), models, feed, services. |
| `dashboard.py` | Подключается в main. Импортирует: database, models, file_utils, admin_password. |
| `admin_views.py` | Подключается в main (SQLAdmin). Импортирует: database (SessionLocal), admin_password, models, feed, file_utils. |
| `feed.py` | Импортируется: routers (публичный /avito.xml), admin_views. |
| `services.py` | Импортируется: routers (build_search_query). |
| `file_utils.py` | Импортируется: dashboard, admin_views. |
| `admin_password.py` | Импортируется: admin_views, dashboard. |

**Итог:** все модули в `app/` используются.

---

## 2. Шаблоны (`templates/`)

### Используются в коде (роутеры отдают эти шаблоны)

| Шаблон | Где используется |
|--------|-------------------|
| `index.html` | `routers.py` — главная |
| `search.html` | `routers.py` — поиск |
| `faq.html` | `routers.py` — FAQ |
| `property-single.html` | `routers.py` — карточка объекта |
| `dashboard/base.html` | Наследуют: home, list, form, folders, folder_view, settings_password |
| `dashboard/home.html` | `dashboard.py` — главная дашборда |
| `dashboard/list.html` | `dashboard.py` — список объектов |
| `dashboard/form.html` | `dashboard.py` — создание/редактирование объекта |
| `dashboard/folders.html` | `dashboard.py` — список папок |
| `dashboard/folder_view.html` | `dashboard.py` — просмотр папки объекта |
| `dashboard/settings_password.html` | `dashboard.py` — смена пароля |
| `sqladmin/folders.html` | `admin_views.py` — кастомная страница папок SQLAdmin |

**Примечание:** `sqladmin/layout.html` подключается в `sqladmin/folders.html` через `extends` — это шаблон из пакета SQLAdmin, не из нашего репозитория.

### Не используются (удалены)

| Шаблон | Статус |
|--------|--------|
| ~~`properties.html`~~ | Удалён (не использовался ни одним роутом). |
| ~~`services.html`~~ | Удалён (не использовался ни одним роутом). |

---

## 3. Миграции и Alembic

- **`alembic.ini`** — используется. В нём указано `script_location = migrations`, то есть активная папка миграций — **`migrations/`**.
- **`migrations/env.py`** — используется при запуске `alembic upgrade head` (читается из папки `migrations/`).
- **`migrations/script.py.mako`** — шаблон для генерации новых миграций.
- **`migrations/versions/`** — все файлы миграций в этой папке учитываются Alembic:
  - `1c244b3d39e1_init_postgres.py`
  - `add_avito_data_json.py`
  - `add_property_image_sort_order.py`
  - `add_avito_object_type.py`

Папка **`alembic/`** (в корне проекта) — **удалена** (не использовалась: в `alembic.ini` указано `script_location = migrations`).

**Итог:** в использовании только `migrations/` и `alembic.ini`.

---

## 4. Статика (`static/`)

### Файлы, на которые есть ссылки в используемых шаблонах

- **Изображения:**  
  `images/favicon.png`, `images/hero_bg_1.png`, `images/hero_bg_2.png`, `images/hero_bg_1.jpg`
- **Шрифты:**  
  `fonts/icomoon/style.css`, `fonts/flaticon/font/flaticon.css`
- **CSS:**  
  `css/tiny-slider.css`, `css/aos.css`, `css/style.css`
- **JS:**  
  `js/bootstrap.bundle.min.js`, `js/tiny-slider.js`, `js/aos.js`, `js/navbar.js`, `js/custom.js`, `js/counter.js`

Дашборд использует Tabler из CDN, локальная статика дашборда в шаблонах не подключается.

### Файлы статики без ссылок (удалены)

Удалены как неиспользуемые:
- `css/bootstrap-reboot.css`, `css/bootstrap-grid.css`, `css/bootstrap-utilities.css` (Bootstrap уже в `style.css`).
- `css/index.html`, `images/index.html`, `js/index.html`, `fonts/index.html` (демо-страницы набора шаблона).

Оставлены без изменений (часть наборов иконок):
- `fonts/icomoon/demo-files/`, `demo.html`, `selection.json`, `Read Me.txt`, `fonts/flaticon/` (backup, scss, html) — при желании можно удалить позже.

### Специальные каталоги

- **`static/uploads/`** — загружаемые файлы (фото, документы объектов). Создаются и заполняются приложением, не часть «исходного кода».
- **`static/documents/`** — по аналогии с uploads, могут быть загруженные документы. Не участвуют в проверке «используется ли файл в коде».

---

## 5. Тесты (`tests/`)

| Файл | Использование |
|------|----------------|
| `conftest.py` | Pytest подхватывает автоматически; создаёт фикстуру `client` (TestClient для app). |
| `test_routes.py` | Тесты маршрутов; используют фикстуру `client`. |
| `__init__.py` | Пустой пакетный файл; для импорта пакета не обязателен, но не мешает. |

**Итог:** все файлы в `tests/` используются при запуске pytest.

---

## 6. Прочие файлы в корне

| Файл | Использование |
|------|----------------|
| `requirements.txt` | Установка зависимостей (pip install -r requirements.txt). |
| `.env`, `.env.example` | Конфигурация и пример переменных окружения. |
| `docker-compose.yml` | Запуск PostgreSQL для разработки/деплоя. |
| `ANALYSIS_REPORT.md` | Документация (анализ проекта). |
| `FILES_USAGE_REPORT.md` | Этот отчёт. |

---

## Краткая сводка

| Категория | В использовании | Не в использовании |
|-----------|------------------|----------------------|
| **app/*.py** | Все 10 модулей | — |
| **Шаблоны** | index, search, faq, property-single, dashboard/*, sqladmin/folders | **properties.html**, **services.html** |
| **Миграции** | `migrations/`, `alembic.ini` | Папка **alembic/** (дубликат) |
| **Статика** | Указанные выше css, js, images, fonts (style.css, icomoon/style.css, flaticon.css и т.д.) | bootstrap-reboot/grid/utilities.css, index.html в static, демо/служебные файлы шрифтов |
| **Тесты** | conftest.py, test_routes.py, __init__.py | — |

Если нужно, могу предложить конкретные команды или правки для удаления неиспользуемых файлов (например, только шаблоны и статика).
