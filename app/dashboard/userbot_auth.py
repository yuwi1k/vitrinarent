"""Dashboard: авторизация Telethon юзербота."""
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

from app.dashboard.common import check_admin, templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/userbot-auth", dependencies=[Depends(check_admin)])
async def userbot_auth_page(request: Request):
    from app.userbot import is_session_exists, auth_get_me
    import os
    authorized = False
    username = None
    if is_session_exists():
        username = await auth_get_me()
        authorized = bool(username)
    return templates.TemplateResponse("dashboard/userbot_auth.html", {
        "request": request,
        "authorized": authorized,
        "username": username,
        "phone": os.getenv("TELEGRAM_USERBOT_PHONE", ""),
        "api_configured": bool(os.getenv("TELEGRAM_API_ID") and os.getenv("TELEGRAM_API_HASH")),
    })


@router.post("/userbot-auth/request-code", dependencies=[Depends(check_admin)])
async def request_code(request: Request):
    import os
    from app.userbot import auth_request_code
    body = await request.json()
    phone = body.get("phone") or os.getenv("TELEGRAM_USERBOT_PHONE", "")
    if not phone:
        return JSONResponse({"ok": False, "error": "Номер телефона не указан"})
    result = await auth_request_code(phone)
    return JSONResponse(result)


@router.post("/userbot-auth/verify-code", dependencies=[Depends(check_admin)])
async def verify_code(request: Request):
    from app.userbot import auth_verify_code
    body = await request.json()
    code = (body.get("code") or "").strip()
    password = (body.get("password") or "").strip()
    if not code:
        return JSONResponse({"ok": False, "error": "Код не введён"})
    result = await auth_verify_code(code, password)
    return JSONResponse(result)


@router.post("/userbot-auth/disconnect", dependencies=[Depends(check_admin)])
async def disconnect_userbot(request: Request):
    from app.userbot import disconnect
    import os
    from pathlib import Path
    await disconnect()
    session_path = Path(__file__).parent.parent.parent / "data" / "userbot.session"
    for ext in ["", "-journal", "-wal", "-shm"]:
        p = Path(str(session_path) + ext)
        if p.exists():
            p.unlink()
    return JSONResponse({"ok": True})
