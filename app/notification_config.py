"""
Конфигурация сценариев уведомлений по статистике объектов.
Все пороги читаются из data/settings.json (ключ "notification_thresholds")
с fallback на значения по умолчанию. Редактируются из дашборда.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Any

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SETTINGS_FILE = os.path.join(_PROJECT_ROOT, "data", "settings.json")


@dataclass
class ScenarioRule:
    key: str
    emoji: str
    title: str
    description: str
    advice: str
    enabled: bool = True
    # Пороги — интерпретируются в классификаторе
    min_views: int = 0
    max_views: int | None = None
    min_contacts: int = 0
    max_contacts: int | None = None
    min_favorites: int = 0
    min_conversion: float = 0.0
    max_conversion: float | None = None
    max_items_in_message: int = 10


SCENARIO_DEFAULTS: list[dict[str, Any]] = [
    {
        "key": "ghost",
        "emoji": "👻",
        "title": "Нет просмотров",
        "description": "Опубликованы, но 0 просмотров — возможно, проблема с выдачей.",
        "advice": "Проверьте категорию, заголовок и наличие фото.",
        "min_views": 0,
        "max_views": 0,
    },
    {
        "key": "low_views",
        "emoji": "📉",
        "title": "Мало просмотров",
        "description": "Объекты плохо видны на площадках.",
        "advice": "Улучшите заголовок, добавьте больше фото.",
        "min_views": 1,
        "max_views": 50,
    },
    {
        "key": "no_calls",
        "emoji": "👀",
        "title": "Смотрят, но не звонят",
        "description": "Много просмотров, но 0 контактов — что-то отпугивает.",
        "advice": "Пересмотрите цену, описание или фото.",
        "min_views": 50,
        "max_contacts": 0,
    },
    {
        "key": "low_conversion",
        "emoji": "🔻",
        "title": "Низкая конверсия",
        "description": "Интерес есть, но конверсия слишком низкая.",
        "advice": "Снизьте цену или улучшите описание.",
        "min_views": 100,
        "min_contacts": 1,
        "max_conversion": 1.0,
    },
    {
        "key": "favorites_no_calls",
        "emoji": "❤️",
        "title": "В избранном, но без звонков",
        "description": "Добавляют в избранное, но не звонят — вероятно, высокая цена.",
        "advice": "Рассмотрите снижение цены или спецпредложение.",
        "min_favorites": 5,
        "max_contacts": 0,
    },
    {
        "key": "not_published",
        "emoji": "🚫",
        "title": "Не опубликованы",
        "description": "Активные объекты, но не размещены ни на одной площадке.",
        "advice": "Запустите синхронизацию или проверьте фид.",
    },
    {
        "key": "leaders",
        "emoji": "🏆",
        "title": "Лидеры",
        "description": "Высокая конверсия — работают отлично.",
        "advice": "",
        "min_views": 200,
        "min_conversion": 5.0,
        "max_items_in_message": 5,
    },
]


def _read_json() -> dict:
    if os.path.isfile(_SETTINGS_FILE):
        try:
            with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except (OSError, json.JSONDecodeError):
            logger.warning("Failed to read %s", _SETTINGS_FILE, exc_info=True)
    return {}


def _write_json(data: dict) -> None:
    os.makedirs(os.path.dirname(_SETTINGS_FILE), exist_ok=True)
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _merge_rule(defaults: dict, overrides: dict) -> ScenarioRule:
    merged = {**defaults, **{k: v for k, v in overrides.items() if v is not None}}
    known_fields = {f.name for f in ScenarioRule.__dataclass_fields__.values()}
    filtered = {k: v for k, v in merged.items() if k in known_fields}
    return ScenarioRule(**filtered)


def get_scenarios() -> list[ScenarioRule]:
    """Возвращает список сценариев с учётом пользовательских порогов."""
    saved = _read_json().get("notification_thresholds", {})
    result = []
    for default in SCENARIO_DEFAULTS:
        override = saved.get(default["key"], {})
        result.append(_merge_rule(default, override))
    return result


def get_scenarios_for_edit() -> list[dict[str, Any]]:
    """Возвращает текущие значения всех сценариев для формы редактирования."""
    scenarios = get_scenarios()
    return [asdict(s) for s in scenarios]


def save_scenarios(updates: dict[str, dict[str, Any]]) -> None:
    """
    Сохраняет пользовательские пороги.
    updates = {"ghost": {"max_views": 0, "enabled": True}, "low_views": {"max_views": 30}, ...}
    """
    data = _read_json()
    current = data.get("notification_thresholds", {})
    for key, vals in updates.items():
        if key not in current:
            current[key] = {}
        current[key].update(vals)
    data["notification_thresholds"] = current
    _write_json(data)
