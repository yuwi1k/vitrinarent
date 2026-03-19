"""Relay-хендлеры: пересылка сообщений агентов в support-чат и ответы обратно."""
import logging
import os
from typing import List

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

logger = logging.getLogger(__name__)

router = Router(name="relay")


def _get_admin_ids() -> List[int]:
    raw = os.getenv("TELEGRAM_ADMIN_IDS", "")
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids


def _get_support_chat_id() -> str:
    return os.getenv("TELEGRAM_SUPPORT_CHAT_ID", "")


def _is_admin(user_id: int) -> bool:
    return user_id in _get_admin_ids()


# ---------------------------------------------------------------------------
# Хендлер: любое сообщение от не-администратора (агента)
# ---------------------------------------------------------------------------

@router.message(~Command("start"))
async def agent_message(message: Message) -> None:
    """Пересылает сообщение агента в support-чат и сохраняет маппинг в БД."""
    if _is_admin(message.from_user.id):
        return  # администраторы обрабатываются в admin_handlers

    support_chat = _get_support_chat_id()
    if not support_chat:
        logger.warning("relay: TELEGRAM_SUPPORT_CHAT_ID not set, cannot relay message")
        await message.answer(
            "Спасибо за ваше сообщение! Мы свяжемся с вами в ближайшее время."
        )
        return

    from_user = message.from_user
    name = (from_user.full_name or "").strip() or "Неизвестный"
    username = f"@{from_user.username}" if from_user.username else f"ID {from_user.id}"
    header = f"📩 <b>Сообщение от агента</b>\n👤 {name} ({username})\n\n"

    try:
        from app.telegram_bot_instance import get_bot
        bot = get_bot()

        # Пересылаем сообщение в support-чат
        if message.photo:
            # Фото с подписью
            caption = (message.caption or "").strip()
            forwarded = await bot.send_photo(
                chat_id=support_chat,
                photo=message.photo[-1].file_id,
                caption=header + caption if caption else header.rstrip("\n"),
            )
        elif message.document:
            caption = (message.caption or "").strip()
            forwarded = await bot.send_document(
                chat_id=support_chat,
                document=message.document.file_id,
                caption=header + caption if caption else header.rstrip("\n"),
            )
        elif message.voice:
            forwarded = await bot.send_voice(
                chat_id=support_chat,
                voice=message.voice.file_id,
                caption=header.rstrip("\n"),
            )
        else:
            text = (message.text or "").strip()
            forwarded = await bot.send_message(
                chat_id=support_chat,
                text=header + text,
            )

        # Сохраняем маппинг forwarded_msg_id → from_chat_id в БД
        await _save_forward_map(
            from_chat_id=message.chat.id,
            forwarded_msg_id=forwarded.message_id,
        )

        await message.answer(
            "✉️ Ваше сообщение получено. Сотрудник ответит вам в ближайшее время."
        )

    except Exception:
        logger.exception("relay: failed to forward message from %s", message.chat.id)
        await message.answer(
            "Извините, произошла ошибка. Попробуйте повторить позже."
        )


# ---------------------------------------------------------------------------
# Хендлер /start для агентов (не-администраторов)
# ---------------------------------------------------------------------------

@router.message(Command("start"))
async def agent_start(message: Message) -> None:
    if _is_admin(message.from_user.id):
        return
    await message.answer(
        "Здравствуйте! 👋\n\n"
        "Напишите ваш вопрос, и наш сотрудник ответит вам в ближайшее время."
    )


# ---------------------------------------------------------------------------
# Хендлер: ответы из support-чата → агенту
# ---------------------------------------------------------------------------

@router.message(F.reply_to_message)
async def support_reply(message: Message) -> None:
    """Когда сотрудник в support-чате отвечает на пересланное сообщение,
    бот пересылает ответ обратно агенту."""
    support_chat = _get_support_chat_id()
    if not support_chat:
        return

    # Проверяем, что это ответ из support-чата
    try:
        chat_id_str = str(message.chat.id)
        support_str = str(support_chat)
        # Числовые ID могут приходить без -100 префикса — нормализуем
        if not (chat_id_str == support_str or chat_id_str == support_str.lstrip("-")):
            return
    except Exception:
        return

    replied_msg_id = message.reply_to_message.message_id
    from_chat_id = await _get_original_chat_id(replied_msg_id)

    if not from_chat_id:
        return

    try:
        from app.telegram_bot_instance import get_bot
        bot = get_bot()
        reply_text = (message.text or message.caption or "").strip()
        if reply_text:
            await bot.send_message(
                chat_id=from_chat_id,
                text=f"💬 <b>Ответ сотрудника:</b>\n\n{reply_text}",
            )
        elif message.photo:
            await bot.send_photo(
                chat_id=from_chat_id,
                photo=message.photo[-1].file_id,
                caption="💬 <b>Ответ сотрудника:</b>",
            )
    except Exception:
        logger.exception("relay: failed to relay reply to %s", from_chat_id)


# ---------------------------------------------------------------------------
# БД операции
# ---------------------------------------------------------------------------

async def _save_forward_map(from_chat_id: int, forwarded_msg_id: int) -> None:
    try:
        from app.database import AsyncSessionLocal
        from app.models import TelegramForwardMap
        async with AsyncSessionLocal() as db:
            record = TelegramForwardMap(
                from_chat_id=from_chat_id,
                forwarded_msg_id=forwarded_msg_id,
            )
            db.add(record)
            await db.commit()
    except Exception:
        logger.exception("relay: failed to save forward map")


async def _get_original_chat_id(forwarded_msg_id: int) -> int | None:
    try:
        from sqlalchemy import select
        from app.database import AsyncSessionLocal
        from app.models import TelegramForwardMap
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(TelegramForwardMap).where(
                    TelegramForwardMap.forwarded_msg_id == forwarded_msg_id
                )
            )
            record = result.scalar_one_or_none()
            return record.from_chat_id if record else None
    except Exception:
        logger.exception("relay: failed to get original chat_id")
        return None
