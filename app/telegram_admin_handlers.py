"""FSM-хендлеры для администраторов бота.
Управление рассылкой через inline-клавиатуру прямо в Telegram."""
import logging
import os
from typing import List

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

from app.telegram_broadcast import load_config, save_config, broadcast_service

logger = logging.getLogger(__name__)

router = Router(name="admin")


def _get_admin_ids() -> List[int]:
    raw = os.getenv("TELEGRAM_ADMIN_IDS", "")
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids


def _is_admin(user_id: int) -> bool:
    return user_id in _get_admin_ids()


# ---------------------------------------------------------------------------
# FSM States
# ---------------------------------------------------------------------------

class BroadcastForm(StatesGroup):
    choose_msg_index = State()
    enter_text = State()
    choose_photo_index = State()
    enter_photo = State()
    enter_channel = State()
    enter_interval = State()


# ---------------------------------------------------------------------------
# Inline keyboard builder
# ---------------------------------------------------------------------------

def _main_menu_keyboard() -> InlineKeyboardMarkup:
    config = load_config()
    enabled = config.get("enabled", False)
    toggle_label = "⏸ Приостановить" if enabled else "▶ Включить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Текст объявления", callback_data="bc:text"),
            InlineKeyboardButton(text="🖼 Фото",             callback_data="bc:photo"),
        ],
        [
            InlineKeyboardButton(text="💬 Каналы",           callback_data="bc:channels"),
            InlineKeyboardButton(text="⏱ Интервалы",        callback_data="bc:interval"),
        ],
        [
            InlineKeyboardButton(text="🚀 Запустить сейчас", callback_data="bc:send_now"),
            InlineKeyboardButton(text=toggle_label,          callback_data="bc:toggle"),
        ],
        [
            InlineKeyboardButton(text="📊 Статус",           callback_data="bc:status"),
            InlineKeyboardButton(text="📈 Статистика",       callback_data="bc:stats"),
        ],
    ])


def _msg_index_keyboard(action: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора номера объявления 1–7."""
    config = load_config()
    messages = config.get("messages", [])
    buttons = []
    row = []
    for i in range(7):
        msg = messages[i] if i < len(messages) else {}
        has_text = bool((msg.get("text") or "").strip())
        has_photo = bool(msg.get("photo_file_id"))
        icon = "✅" if (has_text or has_photo) else "⬜"
        row.append(InlineKeyboardButton(
            text=f"{icon} #{i + 1}",
            callback_data=f"bc:{action}:{i}",
        ))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="« Назад", callback_data="bc:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _channels_keyboard() -> InlineKeyboardMarkup:
    config = load_config()
    channels: List[str] = config.get("channels", [])
    buttons = []
    for ch in channels:
        buttons.append([
            InlineKeyboardButton(text=ch, callback_data="noop"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"bc:del_ch:{ch}"),
        ])
    buttons.append([InlineKeyboardButton(text="➕ Добавить канал", callback_data="bc:add_channel")])
    buttons.append([InlineKeyboardButton(text="« Назад", callback_data="bc:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _status_header(config: dict) -> str:
    enabled = config.get("enabled", False)
    channels = config.get("channels", [])
    interval = config.get("interval_minutes", 60)
    current = config.get("current_index", 0)
    if enabled:
        header = "📢 <b>Рассылка активна</b>\nАвтоматические циклы запущены."
    else:
        header = (
            "⏸ <b>Рассылка приостановлена</b>\n"
            "Автоматические циклы не будут запускаться.\n"
            "Ручной запуск через «Запустить сейчас» по-прежнему работает."
        )
    header += (
        f"\n\nСледующее: объявление #{current + 1} из 7"
        f"\nКаналов: {len(channels)} | Интервал: {interval} мин."
    )
    return header


async def _show_main_menu(message: Message, text: str | None = None) -> None:
    config = load_config()
    header = text or _status_header(config)
    await message.answer(header, reply_markup=_main_menu_keyboard())


async def _edit_main_menu(callback: CallbackQuery, text: str | None = None) -> None:
    config = load_config()
    header = text or _status_header(config)
    try:
        await callback.message.edit_text(header, reply_markup=_main_menu_keyboard())
    except Exception:
        await callback.message.answer(header, reply_markup=_main_menu_keyboard())


# ---------------------------------------------------------------------------
# /start command
# ---------------------------------------------------------------------------

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return  # не-администраторы обрабатываются в relay-хендлерах
    await state.clear()
    await _show_main_menu(message)


# ---------------------------------------------------------------------------
# Callback: главное меню
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "bc:menu")
async def cb_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await _edit_main_menu(callback)


# ---------------------------------------------------------------------------
# Callback: Статус
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "bc:status")
async def cb_status(callback: CallbackQuery) -> None:
    await callback.answer()
    text = broadcast_service.get_status_text()
    back = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Назад", callback_data="bc:menu")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=back)
    except Exception:
        await callback.message.answer(text, reply_markup=back)


# ---------------------------------------------------------------------------
# Callback: Статистика
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "bc:stats")
async def cb_stats(callback: CallbackQuery) -> None:
    await callback.answer()
    text = broadcast_service.get_stats_text()
    back = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Назад", callback_data="bc:menu")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=back)
    except Exception:
        await callback.message.answer(text, reply_markup=back)


# ---------------------------------------------------------------------------
# Callback: Включить / Приостановить
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "bc:toggle")
async def cb_toggle(callback: CallbackQuery) -> None:
    await callback.answer()
    config = load_config()
    config["enabled"] = not config.get("enabled", False)
    save_config(config)

    # Перезапускаем/останавливаем scheduler job
    try:
        from app.scheduler import reschedule_broadcast
        reschedule_broadcast(config)
    except Exception:
        logger.warning("broadcast: failed to reschedule job after toggle", exc_info=True)

    await _edit_main_menu(callback)


# ---------------------------------------------------------------------------
# Callback: Запустить сейчас
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "bc:send_now")
async def cb_send_now(callback: CallbackQuery) -> None:
    await callback.answer("Отправляю…")
    result = await broadcast_service.send_next()
    if result.get("ok"):
        idx = result["index"]
        ok = result["success"]
        fail = result["fail"]
        text = f"✅ Объявление #{idx + 1} отправлено: {ok} успешно, {fail} ошибок."
    else:
        reason = result.get("reason", "unknown")
        text = f"⚠️ Не удалось отправить: {reason}."
    await _edit_main_menu(callback, text + "\n\n" + _status_header(load_config()))


# ---------------------------------------------------------------------------
# Callback: Текст объявления — выбор номера
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "bc:text")
async def cb_text_choose(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(BroadcastForm.choose_msg_index)
    await state.update_data(action="text")
    try:
        await callback.message.edit_text(
            "Выберите номер объявления для редактирования текста:",
            reply_markup=_msg_index_keyboard("edit_text"),
        )
    except Exception:
        await callback.message.answer(
            "Выберите номер объявления:",
            reply_markup=_msg_index_keyboard("edit_text"),
        )


@router.callback_query(F.data.startswith("bc:edit_text:"))
async def cb_text_selected(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    index = int(callback.data.split(":")[-1])
    await state.set_state(BroadcastForm.enter_text)
    await state.update_data(msg_index=index)

    config = load_config()
    messages = config.get("messages", [])
    current_text = (messages[index].get("text") or "") if index < len(messages) else ""

    hint = f"Текущий текст:\n<i>{current_text[:200]}</i>\n\n" if current_text else ""
    back = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Отмена", callback_data="bc:menu")]
    ])
    try:
        await callback.message.edit_text(
            f"{hint}Введите новый текст для объявления <b>#{index + 1}</b>:",
            reply_markup=back,
        )
    except Exception:
        await callback.message.answer(
            f"{hint}Введите новый текст для объявления <b>#{index + 1}</b>:",
            reply_markup=back,
        )


@router.message(BroadcastForm.enter_text)
async def msg_enter_text(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    index = data.get("msg_index", 0)
    new_text = (message.text or "").strip()

    config = load_config()
    config["messages"][index]["text"] = new_text
    save_config(config)

    await state.clear()
    await message.answer(
        f"✅ Текст объявления <b>#{index + 1}</b> сохранён.",
        reply_markup=_main_menu_keyboard(),
    )


# ---------------------------------------------------------------------------
# Callback: Фото — выбор номера
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "bc:photo")
async def cb_photo_choose(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(BroadcastForm.choose_photo_index)
    try:
        await callback.message.edit_text(
            "Выберите номер объявления для загрузки фото:",
            reply_markup=_msg_index_keyboard("edit_photo"),
        )
    except Exception:
        await callback.message.answer(
            "Выберите номер объявления:",
            reply_markup=_msg_index_keyboard("edit_photo"),
        )


@router.callback_query(F.data.startswith("bc:edit_photo:"))
async def cb_photo_selected(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    index = int(callback.data.split(":")[-1])
    await state.set_state(BroadcastForm.enter_photo)
    await state.update_data(msg_index=index)

    config = load_config()
    messages = config.get("messages", [])
    has_photo = bool((messages[index].get("photo_file_id") or "") if index < len(messages) else False)

    hint = "У этого объявления уже есть фото.\n" if has_photo else ""
    back = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить фото", callback_data=f"bc:del_photo:{index}")],
        [InlineKeyboardButton(text="« Отмена", callback_data="bc:menu")],
    ])
    try:
        await callback.message.edit_text(
            f"{hint}Отправьте фото для объявления <b>#{index + 1}</b>:",
            reply_markup=back,
        )
    except Exception:
        await callback.message.answer(
            f"{hint}Отправьте фото для объявления <b>#{index + 1}</b>:",
            reply_markup=back,
        )


@router.message(BroadcastForm.enter_photo, F.photo)
async def msg_enter_photo(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    index = data.get("msg_index", 0)
    # Берём самое большое фото
    photo = message.photo[-1]
    file_id = photo.file_id

    config = load_config()
    config["messages"][index]["photo_file_id"] = file_id
    save_config(config)

    await state.clear()
    await message.answer(
        f"✅ Фото для объявления <b>#{index + 1}</b> сохранено.",
        reply_markup=_main_menu_keyboard(),
    )


@router.message(BroadcastForm.enter_photo)
async def msg_enter_photo_wrong(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    await message.answer("Пожалуйста, отправьте фото (не файл и не текст).")


@router.callback_query(F.data.startswith("bc:del_photo:"))
async def cb_del_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    index = int(callback.data.split(":")[-1])
    config = load_config()
    config["messages"][index]["photo_file_id"] = None
    save_config(config)
    await state.clear()
    await _edit_main_menu(callback, f"✅ Фото объявления #{index + 1} удалено.\n\n" + _status_header(load_config()))


# ---------------------------------------------------------------------------
# Callback: Каналы
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "bc:channels")
async def cb_channels(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    config = load_config()
    channels = config.get("channels", [])
    text = f"<b>Каналы для рассылки</b> ({len(channels)}):\n\nДля добавления нажмите «Добавить канал» и отправьте @username или числовой ID."
    try:
        await callback.message.edit_text(text, reply_markup=_channels_keyboard())
    except Exception:
        await callback.message.answer(text, reply_markup=_channels_keyboard())


@router.callback_query(F.data == "bc:add_channel")
async def cb_add_channel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(BroadcastForm.enter_channel)
    back = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Отмена", callback_data="bc:channels")]
    ])
    try:
        await callback.message.edit_text(
            "Отправьте @username канала или его числовой ID (например <code>-1001234567890</code>):",
            reply_markup=back,
        )
    except Exception:
        await callback.message.answer(
            "Отправьте @username канала или его числовой ID:",
            reply_markup=back,
        )


@router.message(BroadcastForm.enter_channel)
async def msg_enter_channel(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    channel = (message.text or "").strip()
    if not channel:
        await message.answer("Введите корректный @username или ID канала.")
        return

    config = load_config()
    channels: List[str] = config.get("channels", [])
    if channel in channels:
        await message.answer(
            f"⚠️ Канал <code>{channel}</code> уже в списке.",
            reply_markup=_channels_keyboard(),
        )
    else:
        channels.append(channel)
        config["channels"] = channels
        save_config(config)
        await message.answer(
            f"✅ Канал <code>{channel}</code> добавлен.",
            reply_markup=_channels_keyboard(),
        )
    await state.clear()


@router.callback_query(F.data.startswith("bc:del_ch:"))
async def cb_del_channel(callback: CallbackQuery) -> None:
    await callback.answer()
    channel = callback.data[len("bc:del_ch:"):]
    config = load_config()
    channels: List[str] = config.get("channels", [])
    if channel in channels:
        channels.remove(channel)
        config["channels"] = channels
        save_config(config)
    config = load_config()
    channels = config.get("channels", [])
    text = f"<b>Каналы для рассылки</b> ({len(channels)}):"
    try:
        await callback.message.edit_text(text, reply_markup=_channels_keyboard())
    except Exception:
        await callback.message.answer(text, reply_markup=_channels_keyboard())


# ---------------------------------------------------------------------------
# Callback: Интервал
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "bc:interval")
async def cb_interval(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(BroadcastForm.enter_interval)
    config = load_config()
    current = config.get("interval_minutes", 60)
    back = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Отмена", callback_data="bc:menu")]
    ])
    try:
        await callback.message.edit_text(
            f"Текущий интервал: <b>{current} мин.</b>\n\nВведите новый интервал в минутах (минимум 1):",
            reply_markup=back,
        )
    except Exception:
        await callback.message.answer(
            f"Текущий интервал: <b>{current} мин.</b>\n\nВведите новый интервал в минутах:",
            reply_markup=back,
        )


@router.message(BroadcastForm.enter_interval)
async def msg_enter_interval(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) < 1:
        await message.answer("Введите целое число минут (минимум 1).")
        return

    minutes = int(text)
    config = load_config()
    config["interval_minutes"] = minutes
    save_config(config)

    # Перезапускаем job с новым интервалом
    try:
        from app.scheduler import reschedule_broadcast
        reschedule_broadcast(config)
    except Exception:
        logger.warning("broadcast: failed to reschedule job after interval change", exc_info=True)

    await state.clear()
    await message.answer(
        f"✅ Интервал установлен: <b>{minutes} мин.</b>",
        reply_markup=_main_menu_keyboard(),
    )


# ---------------------------------------------------------------------------
# noop callback (заглушка для не-кликабельных кнопок)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()
