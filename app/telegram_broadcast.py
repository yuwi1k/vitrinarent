"""Сервис рассылки: управление конфигом и отправка объявлений в каналы."""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "data" / "telegram_broadcast.json"

_DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "channels": [],
    "interval_minutes": 60,
    "current_index": 0,
    "sent_counts": [0, 0, 0, 0, 0, 0, 0],
    "last_sent_at": None,
    "messages": [{"text": "", "photo_file_id": None} for _ in range(7)],
}


def load_config() -> Dict[str, Any]:
    if not _CONFIG_PATH.exists():
        save_config(_DEFAULT_CONFIG.copy())
        return _DEFAULT_CONFIG.copy()
    try:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        # Гарантируем наличие всех ключей
        for key, val in _DEFAULT_CONFIG.items():
            if key not in data:
                data[key] = val
        # Гарантируем ровно 7 сообщений
        while len(data["messages"]) < 7:
            data["messages"].append({"text": "", "photo_file_id": None})
        data["messages"] = data["messages"][:7]
        # Гарантируем ровно 7 счётчиков
        while len(data["sent_counts"]) < 7:
            data["sent_counts"].append(0)
        data["sent_counts"] = data["sent_counts"][:7]
        return data
    except Exception:
        logger.exception("Failed to load broadcast config, using defaults")
        return _DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class BroadcastService:

    async def send_to_channel(self, channel: str, index: int) -> bool:
        """Отправить объявление с заданным индексом в конкретный канал.
        Возвращает True при успехе."""
        from app.telegram_bot_instance import get_bot
        config = load_config()
        messages: List[Dict] = config.get("messages", [])
        if index < 0 or index >= len(messages):
            return False
        msg = messages[index]
        text = (msg.get("text") or "").strip()
        photo_file_id = msg.get("photo_file_id")
        if not text and not photo_file_id:
            logger.warning("broadcast: message %d is empty, skipping", index + 1)
            return False
        try:
            bot = get_bot()
            if photo_file_id:
                await bot.send_photo(
                    chat_id=channel,
                    photo=photo_file_id,
                    caption=text or None,
                )
            else:
                await bot.send_message(chat_id=channel, text=text)
            return True
        except Exception as exc:
            logger.warning("broadcast: error for channel %s: %s", channel, exc)
            return False

    async def send_next(self) -> Dict[str, Any]:
        """Отправить следующее объявление по ротации во все каналы.
        Возвращает dict с результатами."""
        config = load_config()
        channels: List[str] = config.get("channels", [])
        if not channels:
            logger.info("broadcast: no channels configured, skipping")
            return {"ok": False, "reason": "no_channels"}

        index: int = config.get("current_index", 0) % 7
        success_count = 0
        fail_count = 0
        for channel in channels:
            ok = await self.send_to_channel(channel, index)
            if ok:
                success_count += 1
            else:
                fail_count += 1

        # Обновляем статистику
        config["sent_counts"][index] = config["sent_counts"][index] + success_count
        config["current_index"] = (index + 1) % 7
        config["last_sent_at"] = datetime.now(timezone.utc).isoformat()
        save_config(config)

        logger.info(
            "broadcast: sent message #%d to %d channels (ok=%d fail=%d)",
            index + 1, len(channels), success_count, fail_count,
        )
        return {
            "ok": True,
            "index": index,
            "channels": len(channels),
            "success": success_count,
            "fail": fail_count,
        }

    def get_status_text(self) -> str:
        """Текст статуса для отображения в боте."""
        config = load_config()
        enabled = config.get("enabled", False)
        channels = config.get("channels", [])
        interval = config.get("interval_minutes", 60)
        current = config.get("current_index", 0)
        last_sent = config.get("last_sent_at")

        status = "✅ Активна" if enabled else "⏸ Приостановлена"
        next_msg = current + 1

        lines = [
            f"<b>Статус рассылки:</b> {status}",
            f"<b>Следующее объявление:</b> #{next_msg} из 7",
            f"<b>Каналов:</b> {len(channels)}",
            f"<b>Интервал:</b> {interval} мин.",
        ]
        if last_sent:
            try:
                dt = datetime.fromisoformat(last_sent)
                lines.append(f"<b>Последняя отправка:</b> {dt.strftime('%d.%m.%Y %H:%M')} UTC")
            except Exception:
                pass
        if channels:
            lines.append("\n<b>Каналы:</b>\n" + "\n".join(f"  • {c}" for c in channels))
        return "\n".join(lines)

    def get_stats_text(self) -> str:
        """Текст статистики отправок."""
        config = load_config()
        counts: List[int] = config.get("sent_counts", [0] * 7)
        messages: List[Dict] = config.get("messages", [])
        last_sent = config.get("last_sent_at")

        lines = ["<b>📈 Статистика рассылки</b>\n"]
        for i in range(7):
            msg = messages[i] if i < len(messages) else {}
            text_preview = (msg.get("text") or "")[:40].strip()
            has_photo = bool(msg.get("photo_file_id"))
            count = counts[i] if i < len(counts) else 0
            icon = "🖼" if has_photo else "📝"
            preview = f"{icon} {text_preview}…" if text_preview else f"{icon} (пусто)"
            lines.append(f"#{i + 1} — отправлено: <b>{count}</b> раз\n    {preview}")

        if last_sent:
            try:
                dt = datetime.fromisoformat(last_sent)
                lines.append(f"\n<b>Последняя отправка:</b> {dt.strftime('%d.%m.%Y %H:%M')} UTC")
            except Exception:
                pass
        return "\n".join(lines)


broadcast_service = BroadcastService()
