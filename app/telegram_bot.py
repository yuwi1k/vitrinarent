import logging
import os

import httpx

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self) -> None:
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    async def send_message(self, text: str, parse_mode: str = "HTML") -> None:
        if not self.is_configured:
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    json={"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode},
                )
        except Exception:
            logger.exception("Failed to send Telegram message")

    async def send_moderation_alert(self, property_title: str, platform: str, error: str) -> None:
        text = f"⚠️ <b>Модерация {platform}</b>\n{property_title}\n{error}"
        await self.send_message(text)

    async def send_feed_error_alert(self, platform: str, errors_count: int, details: str) -> None:
        text = f"❌ <b>Ошибки фида {platform}</b>\nОшибок: {errors_count}\n{details}"
        await self.send_message(text)

    async def send_daily_digest(
        self, active_avito: int, active_cian: int, total_views: int, total_contacts: int,
    ) -> None:
        text = (
            f"📊 <b>Дайджест за сутки</b>\n"
            f"Авито: {active_avito} объявлений\n"
            f"Циан: {active_cian} объявлений\n"
            f"Просмотры: {total_views}\n"
            f"Контакты: {total_contacts}"
        )
        await self.send_message(text)

    async def send_scheduler_error(self, job_name: str, error: str) -> None:
        text = f"🔴 <b>Ошибка планировщика</b>\nЗадача: {job_name}\n{error}"
        await self.send_message(text)

    async def send_feed_upload_result(
        self, platform: str, total: int, success: bool, details: str = "",
    ) -> None:
        if success:
            text = f"✅ <b>Автозагрузка {platform}</b>\nОбъектов в фиде: {total}"
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
