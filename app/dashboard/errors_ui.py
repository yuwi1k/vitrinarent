from fastapi import APIRouter, Request, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dashboard.common import check_admin, templates
from app.models import Property

router = APIRouter()


@router.get("/feed-errors", dependencies=[Depends(check_admin)])
async def feed_errors_page(request: Request, db: AsyncSession = Depends(get_db)):
    stmt = select(Property).where(Property.is_active.is_(True)).order_by(Property.id.asc())
    result = await db.execute(stmt)
    all_props = result.scalars().all()
    errors = []
    for p in all_props:
        avito_errs: list = []
        cian_errs: list = []
        ad = p.avito_data or {}
        cd = p.cian_data or {}
        if isinstance(ad, dict) and ad.get("AutoloadErrors"):
            avito_errs = ad["AutoloadErrors"] if isinstance(ad["AutoloadErrors"], list) else [str(ad["AutoloadErrors"])]
        if isinstance(cd, dict) and cd.get("ImportErrors"):
            cian_errs = cd["ImportErrors"] if isinstance(cd["ImportErrors"], list) else [str(cd["ImportErrors"])]
        if avito_errs or cian_errs:
            errors.append({"property": p, "avito_errors": avito_errs, "cian_errors": cian_errs})
    return templates.TemplateResponse("dashboard/feed_errors.html", {"request": request, "errors": errors})
