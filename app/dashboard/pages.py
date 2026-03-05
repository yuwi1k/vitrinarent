"""
Главная страница дашборда и список объектов.
"""
from typing import Optional

from fastapi import APIRouter, Request, Depends
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import PAGE_SIZE_DASHBOARD
from app.database import get_db
from app.dashboard.common import check_admin, templates
from app.models import Property

router = APIRouter()


@router.get("/", dependencies=[Depends(check_admin)])
async def dashboard_home(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    total_r = await db.execute(select(func.count(Property.id)))
    total = total_r.scalar() or 0
    active_r = await db.execute(select(func.count(Property.id)).where(Property.is_active.is_(True)))
    active_count = active_r.scalar() or 0
    on_main_r = await db.execute(select(func.count(Property.id)).where(Property.show_on_main.is_(True)))
    on_main_count = on_main_r.scalar() or 0
    rent_r = await db.execute(select(func.count(Property.id)).where(Property.deal_type == "Аренда"))
    rent_count = rent_r.scalar() or 0
    sale_r = await db.execute(select(func.count(Property.id)).where(Property.deal_type == "Продажа"))
    sale_count = sale_r.scalar() or 0
    avito_rows_r = await db.execute(select(Property.avito_data))
    avito_rows = avito_rows_r.scalars().all()
    avito_published = 0
    for data in avito_rows:
        if not data or not isinstance(data, dict):
            continue
        v = data.get("AvitoId")
        if v is not None and str(v).strip():
            avito_published += 1
    avito_not_published = max(0, (total or 0) - avito_published)
    return templates.TemplateResponse(
        "dashboard/home.html",
        {
            "request": request,
            "total": total,
            "active_count": active_count,
            "on_main_count": on_main_count,
            "rent_count": rent_count,
            "sale_count": sale_count,
            "avito_published": avito_published,
            "avito_not_published": avito_not_published,
        },
    )


def _order_clause(sort_by: Optional[str], order: Optional[str]):
    """Возвращает выражение order_by (по умолчанию id desc)."""
    asc = order and order.lower() == "asc"
    if sort_by == "price":
        return Property.price.asc().nullslast() if asc else Property.price.desc().nullslast()
    if sort_by == "title":
        return Property.title.asc().nullslast() if asc else Property.title.desc().nullslast()
    return Property.id.asc() if asc else Property.id.desc()


@router.get("/properties", dependencies=[Depends(check_admin)])
async def list_properties(
    request: Request,
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    q: Optional[str] = None,
    deal_type: Optional[str] = None,
    category: Optional[str] = None,
    is_active: Optional[str] = None,
    sort_by: Optional[str] = None,
    order: Optional[str] = None,
    id_or_slug: Optional[str] = None,
):
    if page < 1:
        page = 1
    stmt = select(Property).options(
        selectinload(Property.images),
        selectinload(Property.children),
    )
    count_stmt = select(func.count(Property.id))
    stmt = stmt.where(Property.parent_id.is_(None))
    count_stmt = count_stmt.where(Property.parent_id.is_(None))

    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(Property.title.ilike(pattern), Property.address.ilike(pattern)))
        count_stmt = count_stmt.where(or_(Property.title.ilike(pattern), Property.address.ilike(pattern)))
    if deal_type and deal_type.strip() and deal_type != "Все":
        stmt = stmt.where(Property.deal_type == deal_type.strip())
        count_stmt = count_stmt.where(Property.deal_type == deal_type.strip())
    if category and category.strip() and category != "Все":
        stmt = stmt.where(Property.category == category.strip())
        count_stmt = count_stmt.where(Property.category == category.strip())
    if is_active is not None and is_active != "" and is_active != "all":
        if is_active in ("1", "true", "yes"):
            stmt = stmt.where(Property.is_active.is_(True))
            count_stmt = count_stmt.where(Property.is_active.is_(True))
        else:
            stmt = stmt.where(Property.is_active.is_(False))
            count_stmt = count_stmt.where(Property.is_active.is_(False))
    if id_or_slug and id_or_slug.strip():
        term = id_or_slug.strip()
        try:
            sid = int(term)
            stmt = stmt.where(Property.id == sid)
            count_stmt = count_stmt.where(Property.id == sid)
        except ValueError:
            stmt = stmt.where(Property.slug.ilike(f"%{term}%"))
            count_stmt = count_stmt.where(Property.slug.ilike(f"%{term}%"))

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0
    total_pages = max(1, (total + PAGE_SIZE_DASHBOARD - 1) // PAGE_SIZE_DASHBOARD)
    stmt = stmt.order_by(_order_clause(sort_by, order))
    stmt = stmt.offset((page - 1) * PAGE_SIZE_DASHBOARD).limit(PAGE_SIZE_DASHBOARD)
    result = await db.execute(stmt)
    properties = result.scalars().all()
    pages = list(range(1, total_pages + 1))
    property_groups = [(p, sorted(getattr(p, "children", None) or [], key=lambda c: c.id)) for p in properties]
    return templates.TemplateResponse(
        "dashboard/list.html",
        {
            "request": request,
            "properties": properties,
            "property_groups": property_groups,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "pages": pages,
            "q": q or "",
            "deal_type": deal_type or "Все",
            "category": category or "Все",
            "is_active": is_active if is_active not in (None, "") else "all",
            "sort_by": sort_by or "id",
            "order": order or "desc",
            "id_or_slug": id_or_slug or "",
        },
    )
