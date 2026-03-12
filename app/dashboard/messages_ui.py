import logging

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import JSONResponse

from app.dashboard.common import check_admin, templates
from app.avito_client import AvitoAutoloadClient

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/messages", dependencies=[Depends(check_admin)])
async def messages_page(request: Request):
    avito_client = AvitoAutoloadClient()
    avito_chats = []
    avito_error = None

    if avito_client.client_id and avito_client.client_secret:
        try:
            user_id = await avito_client.get_user_id()
            data = await avito_client.get_chats(user_id)
            avito_chats = data.get("chats", [])
        except Exception as e:
            avito_error = str(e)

    cian_messages = []
    cian_error = None

    return templates.TemplateResponse("dashboard/messages.html", {
        "request": request,
        "avito_chats": avito_chats,
        "cian_messages": cian_messages,
        "avito_error": avito_error,
        "cian_error": cian_error,
    })


@router.get("/messages/avito/{chat_id}", dependencies=[Depends(check_admin)])
async def avito_chat_detail(request: Request, chat_id: str):
    client = AvitoAutoloadClient()
    try:
        user_id = await client.get_user_id()
        data = await client.get_chat_messages(user_id, chat_id)
        messages = data.get("messages", [])
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    return JSONResponse({"ok": True, "messages": messages})


@router.post("/messages/avito/{chat_id}/send", dependencies=[Depends(check_admin)])
async def avito_send_message(chat_id: str, text: str = Form(...)):
    client = AvitoAutoloadClient()
    try:
        user_id = await client.get_user_id()
        result = await client.send_chat_message(user_id, chat_id, text)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    return JSONResponse({"ok": True, "result": result})
