"""
Конфигурация приложения из переменных окружения (.env).
Пагинация, лимиты загрузок и прочие настройки.
"""
import os

# Загружаем .env при первом импорте (если ещё не загружен)
from dotenv import load_dotenv
load_dotenv()


def _int_env(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None or val.strip() == "":
        return default
    try:
        return int(val)
    except ValueError:
        return default


# Пагинация: публичный поиск и дашборд
PAGE_SIZE_PUBLIC = _int_env("PAGE_SIZE_PUBLIC", 12)
PAGE_SIZE_DASHBOARD = _int_env("PAGE_SIZE_DASHBOARD", 20)

# Лимит объектов на главной странице
MAIN_PAGE_LIMIT = _int_env("MAIN_PAGE_LIMIT", 3)

# Лимиты загрузки файлов (байты), опционально для будущей валидации
UPLOAD_MAX_FILE_SIZE = _int_env("UPLOAD_MAX_FILE_SIZE", 10 * 1024 * 1024)  # 10 MB по умолчанию
