import logging
import os

logger = logging.getLogger(__name__)


def _get_chat_id() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "")


class TelegramNotifier:
    """Односторонний notifier для системных уведомлений (ошибки фидов, дайджест и т.д.).
    Отправляет сообщения в TELEGRAM_CHAT_ID через единый aiogram.Bot."""

    @property
    def is_configured(self) -> bool:
        from app.telegram_bot_instance import get_bot
        try:
            bot = get_bot()
            return bool(bot.token and _get_chat_id())
        except RuntimeError:
            return False

    async def send_message(self, text: str, chat_id: str | None = None) -> None:
        if not _get_chat_id() and not chat_id:
            return
        target = chat_id or _get_chat_id()
        try:
            from app.telegram_bot_instance import get_bot
            bot = get_bot()
            await bot.send_message(chat_id=target, text=text)
        except Exception as exc:
            logger.warning("Failed to send Telegram message: %s", exc)

    async def send_moderation_alert(self, property_title: str, platform: str, error: str) -> None:
        text = f"⚠️ <b>Модерация {platform}</b>\n{property_title}\n{error}"
        await self.send_message(text)

    async def send_feed_error_alert(self, platform: str, errors_count: int, details: str) -> None:
        text = f"❌ <b>Ошибки фида {platform}</b>\nОшибок: {errors_count}\n{details}"
        await self.send_message(text)

    async def send_daily_digest(
        self, active_avito: int, active_cian: int, total_views: int, total_contacts: int,
        total_active: int = 0,
    ) -> None:
        avito_str = f"{active_avito}/{total_active}" if total_active else str(active_avito)
        cian_str = f"{active_cian}/{total_active}" if total_active else str(active_cian)
        text = (
            f"📊 <b>Дайджест за сутки</b>\n"
            f"Авито: {avito_str} объявлений\n"
            f"Циан: {cian_str} объявлений\n"
            f"Просмотры: {total_views}\n"
            f"Контакты: {total_contacts}"
        )
        await self.send_message(text)

    async def send_scheduler_error(self, job_name: str, error: str) -> None:
        text = f"🔴 <b>Ошибка планировщика</b>\nЗадача: {job_name}\n{error}"
        await self.send_message(text)

    async def send_feed_upload_result(
        self, platform: str, total: int, success: bool, details: str = "",
        total_active: int = 0,
    ) -> None:
        if success:
            count_str = f"{total}/{total_active}" if total_active else str(total)
            text = f"✅ <b>Автозагрузка {platform}</b>\nОбъектов в фиде: {count_str}"
            if details:
                text += f"\n{details}"
        else:
            text = f"❌ <b>Автозагрузка {platform} — ошибка</b>\n{details}"
        await self.send_message(text)

    async def send_sync_result(
        self, platform: str, updated: int, total_items: int, errors: int = 0,
    ) -> None:
        text = (
            f"🔄 <b>Синхронизация {platform}</b>\n"
            f"Обновлено: {updated} из {total_items}"
        )
        if errors:
            text += f"\n⚠️ С ошибками: {errors}"
        await self.send_message(text)

    async def send_stats_report(self, report: dict, scenarios: list) -> None:
        """Универсальный рендер отчёта — формат берётся из scenarios."""
        header = "📊 <b>Отчёт по статистике объектов</b>\n"

        for s in scenarios:
            items = report.get(s.key, [])
            if not items:
                continue

            limit = s.max_items_in_message
            lines = [f"{s.emoji} <b>{s.title} ({len(items)})</b>"]
            if s.description:
                lines.append(s.description)

            for it in items[:limit]:
                line = f"  • ID {it['id']} — {it['title']}"
                details = []
                if it.get("views"):
                    details.append(f"просм: {it['views']}")
                if it.get("favorites"):
                    details.append(f"избр: {it['favorites']}")
                if it.get("contacts"):
                    details.append(f"конт: {it['contacts']}")
                if it.get("conversion"):
                    details.append(f"конв: {it['conversion']}%")
                if details:
                    line += f" ({', '.join(details)})"
                lines.append(line)

            if len(items) > limit:
                lines.append(f"  ...и ещё {len(items) - limit}")
            if s.advice:
                lines.append(f"<i>Совет: {s.advice}</i>")

            await self.send_message(header + "\n".join(lines))


notifier = TelegramNotifier()
