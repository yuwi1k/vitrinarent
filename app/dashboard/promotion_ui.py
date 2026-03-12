import logging
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dashboard.common import check_admin, templates
from app.models import Property
from app.avito_client import AvitoAutoloadClient

logger = logging.getLogger(__name__)
router = APIRouter()

AVITO_VAS_OPTIONS = [
    ("highlight", "Highlight — выделение цветом (7 дн.)"),
    ("xl", "XL — большой размер (7 дн.)"),
    ("x2_1", "x2 — до 2× просмотров (1 дн.)"),
    ("x2_7", "x2 — до 2× просмотров (7 дн.)"),
    ("x5_1", "x5 — до 5× просмотров (1 дн.)"),
    ("x5_7", "x5 — до 5× просмотров (7 дн.)"),
    ("x10_1", "x10 — до 10× просмотров (1 дн.)"),
    ("x10_7", "x10 — до 10× просмотров (7 дн.)"),
]


@router.get("/promotion", dependencies=[Depends(check_admin)])
async def promotion_page(request: Request, db: AsyncSession = Depends(get_db)):
    stmt = select(Property).where(Property.is_active.is_(True)).order_by(Property.title.asc())
    result = await db.execute(stmt)
    properties = result.scalars().all()
    return templates.TemplateResponse("dashboard/promotion.html", {
        "request": request,
        "properties": properties,
        "vas_options": AVITO_VAS_OPTIONS,
    })


@router.post("/promotion/avito/apply-vas", dependencies=[Depends(check_admin)])
async def apply_avito_vas(
    property_id: int = Form(...),
    vas_slug: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    prop = await db.get(Property, property_id)
    if not prop:
        return JSONResponse({"ok": False, "error": "Property not found"}, status_code=404)
    ad = prop.avito_data or {}
    avito_id = ad.get("AvitoId")
    if not avito_id:
        return JSONResponse({"ok": False, "error": "Объявление не опубликовано на Авито (нет AvitoId)"}, status_code=400)
    client = AvitoAutoloadClient()
    try:
        user_id = await client.get_user_id()
        result = await client.apply_vas(user_id, int(avito_id), vas_slug)
        return JSONResponse({"ok": True, "result": result})
    except Exception as e:
        logger.exception("VAS apply failed")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
