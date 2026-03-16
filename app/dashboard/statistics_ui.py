"""Страница статистики по объявлениям: просмотры, избранное, звонки, конверсия."""
import logging
from typing import Any

from fastapi import APIRouter, Request, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dashboard.common import check_admin, templates
from app.database import get_db
from app.models import Property
from app.scheduler import get_scheduler_status

logger = logging.getLogger(__name__)
router = APIRouter()


def _safe_int(val: Any) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


@router.get("/statistics", dependencies=[Depends(check_admin)])
async def statistics_page(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Property).where(Property.is_active.is_(True)).order_by(Property.id.desc())
    )
    props = result.scalars().all()

    totals = {
        "avito_views": 0, "avito_contacts": 0, "avito_favorites": 0,
        "cian_views": 0, "cian_contacts": 0,
        "total_views": 0, "total_contacts": 0, "total_favorites": 0,
    }

    rows: list[dict[str, Any]] = []
    for p in props:
        sd = p.stats_data if isinstance(p.stats_data, dict) else {}

        av = _safe_int(sd.get("avito_views"))
        ac = _safe_int(sd.get("avito_contacts"))
        af = _safe_int(sd.get("avito_favorites"))
        cv = _safe_int(sd.get("cian_views"))
        cc = _safe_int(sd.get("cian_contacts"))

        total_v = av + cv
        total_c = ac + cc
        conversion = round(total_c / total_v * 100, 1) if total_v > 0 else 0.0

        rows.append({
            "id": p.id,
            "title": p.title or f"Объект #{p.id}",
            "address": p.address or "",
            "avito_views": av,
            "avito_contacts": ac,
            "avito_favorites": af,
            "cian_views": cv,
            "cian_contacts": cc,
            "total_views": total_v,
            "total_contacts": total_c,
            "total_favorites": af,
            "conversion": conversion,
            "is_on_avito": p.is_on_avito,
            "is_on_cian": p.is_on_cian,
        })

        totals["avito_views"] += av
        totals["avito_contacts"] += ac
        totals["avito_favorites"] += af
        totals["cian_views"] += cv
        totals["cian_contacts"] += cc
        totals["total_views"] += total_v
        totals["total_contacts"] += total_c
        totals["total_favorites"] += af

    totals["conversion"] = (
        round(totals["total_contacts"] / totals["total_views"] * 100, 1)
        if totals["total_views"] > 0 else 0.0
    )

    sched = get_scheduler_status()
    collect_result = sched.get("results", {}).get("collect_statistics", {})
    last_collected = collect_result.get("last_run", "")
    if last_collected:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(last_collected)
            last_collected = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            pass

    return templates.TemplateResponse("dashboard/statistics.html", {
        "request": request,
        "rows": rows,
        "totals": totals,
        "count": len(rows),
        "last_collected": last_collected,
    })
