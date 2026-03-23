"""Telethon userbot для рассылки от имени аккаунта пользователя."""
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Сессия хранится как строка в текстовом файле (StringSession — без SQLite)
_SESSION_FILE = Path(__file__).parent.parent / "data" / "userbot_session.txt"

_client = None
_auth_state: dict = {}


def _api_params():
    try:
        return int(os.getenv("TELEGRAM_API_ID", "0")), os.getenv("TELEGRAM_API_HASH", "")
    except ValueError:
        return 0, ""


def _load_session_string() -> str:
    if _SESSION_FILE.exists():
        return _SESSION_FILE.read_text(encoding="utf-8").strip()
    return ""


def _save_session_string(s: str) -> None:
    _SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SESSION_FILE.write_text(s, encoding="utf-8")


def is_session_exists() -> bool:
    return _SESSION_FILE.exists() and bool(_load_session_string())


async def get_userbot():
    """Возвращает подключённый авторизованный Telethon клиент или None."""
    global _client
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        return None

    api_id, api_hash = _api_params()
    if not api_id or not api_hash:
        return None

    session_string = _load_session_string()
    if not session_string:
        return None

    # Если клиент уже создан с той же сессией — переиспользуем
    if _client is None:
        _client = TelegramClient(StringSession(session_string), api_id, api_hash)

    if not _client.is_connected():
        await _client.connect()

    if not await _client.is_user_authorized():
        logger.warning("userbot: session expired")
        _client = None
        return None

    return _client


async def disconnect():
    global _client
    if _client and _client.is_connected():
        await _client.disconnect()
    _client = None


# ---------------------------------------------------------------------------
# Auth flow
# ---------------------------------------------------------------------------

async def auth_request_code(phone: str) -> dict:
    """Шаг 1: отправить код на номер телефона."""
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        return {"ok": False, "error": "telethon not installed"}

    api_id, api_hash = _api_params()
    if not api_id or not api_hash:
        return {"ok": False, "error": "TELEGRAM_API_ID/HASH not configured"}

    try:
        # Создаём временный клиент в памяти (StringSession без файла)
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        result = await client.send_code_request(phone)
        _auth_state["client"] = client
        _auth_state["phone"] = phone
        _auth_state["hash"] = result.phone_code_hash
        logger.info("userbot: code sent to %s", phone)
        return {"ok": True, "phone_code_hash": result.phone_code_hash}
    except Exception as exc:
        logger.exception("userbot: failed to send code")
        return {"ok": False, "error": str(exc)}


async def auth_verify_code(code: str, password: str = "") -> dict:
    """Шаг 2: подтвердить код, сохранить сессию."""
    try:
        from telethon.errors import SessionPasswordNeededError
    except ImportError:
        return {"ok": False, "error": "telethon not installed"}

    client = _auth_state.get("client")
    phone = _auth_state.get("phone")
    phone_code_hash = _auth_state.get("hash")

    if not client or not phone or not phone_code_hash:
        return {"ok": False, "error": "Сессия авторизации устарела — запросите код заново"}

    try:
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
    except SessionPasswordNeededError:
        if not password:
            return {"ok": False, "need_password": True, "error": "Требуется пароль 2FA"}
        try:
            await client.sign_in(password=password)
        except Exception as exc:
            return {"ok": False, "error": f"Неверный пароль 2FA: {exc}"}
    except Exception as exc:
        logger.exception("userbot: sign_in failed")
        return {"ok": False, "error": str(exc)}

    # Сохраняем строку сессии в файл
    session_string = client.session.save()
    _save_session_string(session_string)

    # Сбрасываем глобальный клиент чтобы пересоздать с новой сессией
    global _client
    _client = None
    _auth_state.clear()

    logger.info("userbot: session saved successfully")
    return {"ok": True}


async def auth_get_me() -> Optional[str]:
    """Возвращает имя авторизованного пользователя или None."""
    client = await get_userbot()
    if not client:
        return None
    try:
        me = await client.get_me()
        name = f"{me.first_name or ''} {me.last_name or ''}".strip()
        return name or me.username or str(me.id)
    except Exception:
        return None
