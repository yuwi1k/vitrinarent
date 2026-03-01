"""
Хранение и чтение пароля админа: приоритет у файла data/.admin_password, иначе — переменная окружения ADMIN_PASSWORD.
Смена пароля из дашборда записывает новый пароль в файл.
"""
import os

# Корень проекта (родитель каталога app)
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_PASSWORD_FILE = os.path.join(_PROJECT_ROOT, "data", ".admin_password")


def get_admin_password() -> str:
    """Текущий пароль: из файла data/.admin_password, иначе из env ADMIN_PASSWORD."""
    if os.path.isfile(_PASSWORD_FILE):
        try:
            with open(_PASSWORD_FILE, "r", encoding="utf-8") as f:
                p = f.read().strip()
                if p:
                    return p
        except OSError:
            pass
    return os.getenv("ADMIN_PASSWORD", "admin")


def set_admin_password(new_password: str) -> None:
    """Сохранить новый пароль в data/.admin_password."""
    dir_path = os.path.dirname(_PASSWORD_FILE)
    os.makedirs(dir_path, exist_ok=True)
    with open(_PASSWORD_FILE, "w", encoding="utf-8") as f:
        f.write(new_password)
