"""Telethon userbot для рассылки от имени аккаунта пользователя."""
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SESSION_PATH = Path(__file__).parent.parent / "data" / "userbot.session"

# Активный клиент для рассылки
_client = None

# Временный клиент во время процесса авторизации
_auth_state: dict = {}


def _api_params():
    try:
        return int(os.getenv("TELEGRAM_API_ID", "0")), os.getenv("TELEGRAM_API_HASH", "")
    except ValueError:
        return 0, ""


def is_session_exists() -> bool:
    return _SESSION_PATH.exists()


async def get_userbot():
    """Возвращает подключённый авторизованный Telethon клиент или None."""
    global _client
    try:
        from telethon import TelegramClient
    except ImportError:
        return None

    api_id, api_hash = _api_params()
    if not api_id or not api_hash:
        return None
    if not _SESSION_PATH.exists():
        return None

    if _client is None:
        _client = TelegramClient(str(_SESSION_PATH), api_id, api_hash)

    if not _client.is_connected():
        await _client.connect()

    if not await _client.is_user_authorized():
        logger.warning("userbot: session expired")
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
    """
    Шаг 1: отправить SMS-код на номер.
    Возвращает {"ok": True, "phone_code_hash": "..."} или {"ok": False, "error": "..."}
    """
    try:
        from telethon import TelegramClient
    except ImportError:
        return {"ok": False, "error": "telethon not installed"}

    api_id, api_hash = _api_params()
    if not api_id or not api_hash:
        return {"ok": False, "error": "TELEGRAM_API_ID/HASH not configured"}

    _SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        client = TelegramClient(str(_SESSION_PATH), api_id, api_hash)
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
    """
    Шаг 2: подтвердить код (и 2FA пароль если нужно).
    Возвращает {"ok": True} или {"ok": False, "need_password": True, "error": "..."}
    """
    client = _auth_state.get("client")
    phone = _auth_state.get("phone")
    phone_code_hash = _auth_state.get("hash")

    if not client or not phone or not phone_code_hash:
        return {"ok": False, "error": "Auth session not found, request code first"}

    try:
        from telethon.errors import SessionPasswordNeededError
    except ImportError:
        return {"ok": False, "error": "telethon not installed"}

    try:
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        _auth_state.clear()
        logger.info("userbot: authorized successfully")
        return {"ok": True}
    except SessionPasswordNeededError:
        if not password:
            return {"ok": False, "need_password": True, "error": "2FA password required"}
        try:
            await client.sign_in(password=password)
            _auth_state.clear()
            logger.info("userbot: authorized with 2FA")
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": f"Wrong 2FA password: {exc}"}
    except Exception as exc:
        logger.exception("userbot: sign_in failed")
        return {"ok": False, "error": str(exc)}


async def auth_get_me() -> Optional[str]:
    """Возвращает имя авторизованного пользователя или None."""
    client = await get_userbot()
    if not client:
        return None
    try:
        me = await client.get_me()
        return f"{me.first_name or ''} {me.last_name or ''}".strip() or me.username or str(me.id)
    except Exception:
        return None
