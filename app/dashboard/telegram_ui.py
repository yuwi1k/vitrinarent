import logging
import os

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

from app.dashboard.common import check_admin, templates
from app.telegram_broadcast import load_config

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/telegram-broadcast", dependencies=[Depends(check_admin)])
async def telegram_broadcast_page(request: Request):
    config = load_config()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    bot_username = None
    if bot_token:
        try:
            from app.telegram_bot_instance import get_bot
            bot = get_bot()
            me = await bot.get_me()
            bot_username = me.username
        except Exception:
            pass

    return templates.TemplateResponse("dashboard/telegram_broadcast.html", {
        "request": request,
        "config": config,
        "bot_username": bot_username,
    })


@router.post("/telegram-broadcast/send-now", dependencies=[Depends(check_admin)])
async def telegram_send_now(request: Request):
    """API для ручного запуска рассылки из дашборда."""
    try:
        from app.telegram_broadcast import broadcast_service
        result = await broadcast_service.send_next()
        return JSONResponse({"ok": True, "result": result})
    except Exception as exc:
        logger.exception("dashboard: broadcast send_now failed")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
