"""
Хранение настроек сайта и фида Авито (контакты для объявлений).
Приоритет: data/settings.json, иначе переменные окружения.
Используется в дашборде (редактирование) и в feed.py (чтение).
"""
import json
import os

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SETTINGS_FILE = os.path.join(_PROJECT_ROOT, "data", "settings.json")

DEFAULTS = {
    "avito_manager_name": "",
    "avito_contact_phone": "",
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
            pass
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
        or "+79990000000"
    )


def get_settings_for_edit() -> dict:
    """Текущие значения для формы настроек (дашборд)."""
    s = _read_settings()
    return {
        "avito_manager_name": (s.get("avito_manager_name") or "").strip()
        or os.getenv("AVITO_MANAGER_NAME", os.getenv("MANAGER_NAME", "")),
        "avito_contact_phone": (s.get("avito_contact_phone") or "").strip()
        or os.getenv("AVITO_CONTACT_PHONE", os.getenv("CONTACT_PHONE", "")),
    }


def save_settings(avito_manager_name: str = "", avito_contact_phone: str = "") -> None:
    """Сохранить настройки из формы дашборда."""
    data = _read_settings()
    data["avito_manager_name"] = (avito_manager_name or "").strip()
    data["avito_contact_phone"] = (avito_contact_phone or "").strip()
    _write_settings(data)
