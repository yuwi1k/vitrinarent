"""
Хранение и проверка пароля админа с хешированием (PBKDF2-HMAC-SHA256).
Приоритет: файл data/.admin_password → env ADMIN_PASSWORD.
При первом логине plain-text пароль автоматически мигрирует в хеш.
"""
import hashlib
import os
import secrets

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_PASSWORD_FILE = os.path.join(_PROJECT_ROOT, "data", ".admin_password")

_HASH_PREFIX = "pbkdf2:"
_ITERATIONS = 260_000


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS)
    return f"{_HASH_PREFIX}{salt}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    if not stored.startswith(_HASH_PREFIX):
        return password == stored
    payload = stored[len(_HASH_PREFIX):]
    if "$" not in payload:
        return False
    salt, dk_hex = payload.split("$", 1)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS)
    return secrets.compare_digest(dk.hex(), dk_hex)


def _read_stored_password() -> str:
    if os.path.isfile(_PASSWORD_FILE):
        try:
            with open(_PASSWORD_FILE, "r", encoding="utf-8") as f:
                p = f.read().strip()
                if p:
                    return p
        except OSError:
            pass
    return os.getenv("ADMIN_PASSWORD", "admin")


def get_admin_password() -> str:
    """Возвращает хранимый пароль/хеш (для внутреннего использования)."""
    return _read_stored_password()


def check_admin_password(password: str) -> bool:
    """Проверяет введённый пароль. При совпадении plain-text мигрирует в хеш."""
    stored = _read_stored_password()
    if not _verify_password(password, stored):
        return False
    if not stored.startswith(_HASH_PREFIX):
        set_admin_password(password)
    return True


def set_admin_password(new_password: str) -> None:
    """Сохраняет новый пароль в виде хеша в data/.admin_password."""
    dir_path = os.path.dirname(_PASSWORD_FILE)
    os.makedirs(dir_path, exist_ok=True)
    with open(_PASSWORD_FILE, "w", encoding="utf-8") as f:
        f.write(_hash_password(new_password))
