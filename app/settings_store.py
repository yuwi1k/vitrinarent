"""
Хранение настроек сайта и фида Авито (контакты для объявлений).
Приоритет: data/settings.json, иначе переменные окружения.
Используется в дашборде (редактирование) и в feed.py (чтение).
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SETTINGS_FILE = os.path.join(_PROJECT_ROOT, "data", "settings.json")

DEFAULTS = {
    "avito_manager_name": "",
    "avito_contact_phone": "",
    "contact_phone": "",
    "contact_email": "",
    "contact_telegram": "",
}


def _read_settings() -> dict:
    """Прочитать настройки из data/settings.json."""
    if os.path.isfile(_SETTINGS_FILE):
        try:
            with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return {k: (v if v is not None else "") for k, v in data.items()}
        except (OSError, json.JSONDecodeError):
            logger.warning("Failed to read settings from %s, using defaults", _SETTINGS_FILE, exc_info=True)
    return {}


def _write_settings(data: dict) -> None:
    """Записать настройки в data/settings.json."""
    dir_path = os.path.dirname(_SETTINGS_FILE)
    os.makedirs(dir_path, exist_ok=True)
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_avito_manager_name() -> str:
    """Имя менеджера для фида Авито: из настроек или env."""
    s = _read_settings()
    v = (s.get("avito_manager_name") or "").strip()
    if v:
        return v
    return (
        os.getenv("AVITO_MANAGER_NAME", os.getenv("MANAGER_NAME", "")).strip()
        or "Менеджер Vitrina"
    )


def get_avito_contact_phone() -> str:
    """Телефон для фида Авито: из настроек или env."""
    s = _read_settings()
    v = (s.get("avito_contact_phone") or "").strip()
    if v:
        return v
    return (
        os.getenv("AVITO_CONTACT_PHONE", os.getenv("CONTACT_PHONE", "")).strip()
        or "+79102535534"
    )


def get_contact_phone() -> str:
    s = _read_settings()
    v = (s.get("contact_phone") or "").strip()
    if v:
        return v
    return os.getenv("CONTACT_PHONE", "").strip()


def get_contact_email() -> str:
    s = _read_settings()
    v = (s.get("contact_email") or "").strip()
    if v:
        return v
    return os.getenv("CONTACT_EMAIL", "").strip()


def get_contact_telegram() -> str:
    s = _read_settings()
    v = (s.get("contact_telegram") or "").strip()
    if v:
        return v
    return os.getenv("CONTACT_TELEGRAM", "").strip()


def get_public_contacts() -> dict:
    return {
        "contact_phone": get_contact_phone(),
        "contact_email": get_contact_email(),
        "contact_telegram": get_contact_telegram(),
    }


def get_settings_for_edit() -> dict:
    """Текущие значения для формы настроек (дашборд)."""
    s = _read_settings()
    return {
        "avito_manager_name": (s.get("avito_manager_name") or "").strip()
        or os.getenv("AVITO_MANAGER_NAME", os.getenv("MANAGER_NAME", "")),
        "avito_contact_phone": (s.get("avito_contact_phone") or "").strip()
        or os.getenv("AVITO_CONTACT_PHONE", os.getenv("CONTACT_PHONE", "")),
        "contact_phone": (s.get("contact_phone") or "").strip()
        or os.getenv("CONTACT_PHONE", ""),
        "contact_email": (s.get("contact_email") or "").strip()
        or os.getenv("CONTACT_EMAIL", ""),
        "contact_telegram": (s.get("contact_telegram") or "").strip()
        or os.getenv("CONTACT_TELEGRAM", ""),
    }


def save_settings(
    avito_manager_name: str = "",
    avito_contact_phone: str = "",
    contact_phone: str = "",
    contact_email: str = "",
    contact_telegram: str = "",
) -> None:
    """Сохранить настройки из формы дашборда."""
    data = _read_settings()
    data["avito_manager_name"] = (avito_manager_name or "").strip()
    data["avito_contact_phone"] = (avito_contact_phone or "").strip()
    data["contact_phone"] = (contact_phone or "").strip()
    data["contact_email"] = (contact_email or "").strip()
    data["contact_telegram"] = (contact_telegram or "").strip()
    _write_settings(data)


def is_avito_feed_enabled() -> bool:
    return _read_settings().get("avito_feed_enabled", True)


def set_avito_feed_enabled(val: bool) -> None:
    data = _read_settings()
    data["avito_feed_enabled"] = bool(val)
    _write_settings(data)


def is_cian_feed_enabled() -> bool:
    return _read_settings().get("cian_feed_enabled", True)


def set_cian_feed_enabled(val: bool) -> None:
    data = _read_settings()
    data["cian_feed_enabled"] = bool(val)
    _write_settings(data)
