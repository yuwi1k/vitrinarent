"""
Публичные маршруты приложения: главная, поиск, FAQ, карточка объекта, фид Авито.
"""
import json
import math
import os
from typing import Optional

import bleach
from fastapi import APIRouter, Request, Depends, HTTPException, Query, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.database import get_db
from app.models import Property
from app.feed import generate_avito_feed
from app.services import build_search_query

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Разрешённые теги и атрибуты для описания объекта (защита от XSS)
ALLOWED_TAGS = ["p", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li", "a", "span"]
ALLOWED_ATTRS = {"a": ["href", "title", "target", "rel"]}


def _sanitize_html(value: Optional[str]) -> str:
    if not value or not value.strip():
        return ""
    return bleach.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        strip=True,
    )


templates.env.filters["sanitize_html"] = _sanitize_html


@router.get("/")
async def read_root(request: Request, db: AsyncSession = Depends(get_db)):
    # Ровно 3 объекта, выбранных в админке для показа на главной (порядок по main_page_order)
    stmt_main = (
        select(Property)
        .where(Property.is_active == True, Property.show_on_main == True)
        .order_by(Property.main_page_order.is_(None), Property.main_page_order.asc(), Property.id.desc())
        .limit(3)
    )
    result = await db.execute(stmt_main)
    properties = result.scalars().all()

    stmt_count = select(func.count()).select_from(Property).where(Property.is_active == True)
    total_properties = (await db.execute(stmt_count)).scalar() or 0
    rent_count = (await db.execute(select(func.count()).select_from(Property).where(Property.is_active == True, Property.deal_type == "Аренда"))).scalar() or 0
    sale_count = (await db.execute(select(func.count()).select_from(Property).where(Property.is_active == True, Property.deal_type == "Продажа"))).scalar() or 0

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "properties": properties,
            "total_properties": total_properties,
            "rent_count": rent_count,
            "sale_count": sale_count,
        },
    )


PAGE_SIZE = 12


def _search_order_by(stmt, sort: Optional[str]):
    """Применяет сортировку к запросу поиска."""
    if sort == "price_asc":
        return stmt.order_by(Property.price.asc(), Property.id.desc())
    if sort == "price_desc":
        return stmt.order_by(Property.price.desc(), Property.id.desc())
    if sort == "area_asc":
        return stmt.order_by(Property.area.asc(), Property.id.desc())
    if sort == "area_desc":
        return stmt.order_by(Property.area.desc(), Property.id.desc())
    if sort == "date_asc":
        return stmt.order_by(Property.id.asc())
    return stmt.order_by(Property.id.desc())


@router.get("/search")
async def search_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    q: Optional[str] = None,
    deal_type: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[str] = None,
    max_price: Optional[str] = None,
    min_area: Optional[str] = None,
    max_area: Optional[str] = None,
    sort: Optional[str] = Query("date_desc", description="price_asc|price_desc|area_asc|area_desc|date_desc|date_asc"),
):
    stmt = build_search_query(q, deal_type, category, min_price, max_price, min_area, max_area)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_items = (await db.execute(count_stmt)).scalar() or 0
    total_pages = math.ceil(total_items / PAGE_SIZE) if total_items > 0 else 1

    stmt_ordered = _search_order_by(stmt, sort)

    # Все отфильтрованные объекты для карты (без пагинации)
    result_map = await db.execute(stmt_ordered)
    all_filtered = result_map.scalars().all()
    map_properties = [
        {
            "id": p.id,
            "slug": p.slug or "",
            "title": p.title or "",
            "address": p.address or "",
            "category": p.category or "",
            "latitude": float(p.latitude),
            "longitude": float(p.longitude),
            "main_image": (p.main_image if (p.main_image and p.main_image.startswith("/")) else "/" + (p.main_image or "")) if p.main_image else "",
            "price": p.price,
        }
        for p in all_filtered
        if p.latitude is not None and p.longitude is not None
    ]

    stmt_page = stmt_ordered.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    result = await db.execute(stmt_page)
    properties = result.scalars().all()
    pages = list(range(1, total_pages + 1))

    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "properties": properties,
            "page": page,
            "total_pages": total_pages,
            "total_items": total_items,
            "pages": pages,
            "map_properties": map_properties,
            "map_properties_json": json.dumps(map_properties),
            "yandex_maps_api_key": os.getenv("YANDEX_MAPS_API_KEY", ""),
            "q": q,
            "deal_type": deal_type,
            "category": category,
            "min_price": min_price,
            "max_price": max_price,
            "min_area": min_area,
            "max_area": max_area,
            "sort": sort or "date_desc",
        },
    )


@router.get("/faq")
async def faq_page(request: Request):
    return templates.TemplateResponse("faq.html", {"request": request})


@router.get("/property/{slug}")
async def read_property(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Property)
        .options(
            joinedload(Property.images),
            joinedload(Property.documents),
            selectinload(Property.children),
        )
        .where(Property.slug == slug)
    )
    result = await db.execute(stmt)
    property = result.unique().scalars().first()
    if not property and slug.isdigit():
        stmt = (
            select(Property)
            .options(
                joinedload(Property.images),
                joinedload(Property.documents),
                selectinload(Property.children),
            )
            .where(Property.id == int(slug))
        )
        result = await db.execute(stmt)
        property = result.unique().scalars().first()
    if not property:
        raise HTTPException(status_code=404, detail="Object not found")

    # Логика «Доступные площади в этом здании»:
    # - если это здание (нет parent) — показываем всех его активных детей;
    # - если это часть (есть parent) — сначала показываем само здание,
    #   затем всех его активных детей, кроме текущей части.
    if getattr(property, "parent", None):
        building = property.parent
        available_units = []
        if building.is_active:
            available_units.append(building)
        for child in building.children or []:
            if child.is_active and child.id != property.id:
                available_units.append(child)
    else:
        building = property
        available_units = [child for child in (building.children or []) if child.is_active]

    site_url = os.getenv("SITE_URL", "http://127.0.0.1:8000").rstrip("/")
    return templates.TemplateResponse(
        "property-single.html",
        {
            "request": request,
            "property": property,
            "available_units": available_units,
            "site_url": site_url,
        },
    )


@router.get("/avito.xml")
async def get_avito_feed_route(db: AsyncSession = Depends(get_db)):
    stmt = select(Property).where(Property.is_active == True)
    result = await db.execute(stmt)
    properties = result.scalars().all()
    xml_content = generate_avito_feed(properties)
    return Response(content=xml_content, media_type="application/xml")
