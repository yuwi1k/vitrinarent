"""
Публичные маршруты приложения: главная, поиск, FAQ, карточка объекта, фид Авито.
"""
import json
import logging
import math
import os
from typing import Optional

logger = logging.getLogger(__name__)

import bleach
from markupsafe import Markup
from fastapi import APIRouter, Request, Depends, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.config import PAGE_SIZE_PUBLIC
from app.database import get_db
from app.models import Property
from app.feed import generate_avito_feed_full
from app.feed_cian import generate_cian_feed
from app.feed_jcat import generate_jcat_feed
from app.services import build_search_query, group_properties_by_building, BUILDING_PREVIEW_COUNT
from app.settings_store import get_public_contacts
from app.sites import SITES

from datetime import datetime as _dt

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["now"] = _dt.now


def _tpl(request: Request, name: str) -> str:
    """Return site-specific template path."""
    site = getattr(request.state, "site", None)
    if site and site.template_prefix:
        return f"{site.template_prefix}{name}"
    return name


def _site_ctx(request: Request) -> dict:
    """Common site context for all templates."""
    site = getattr(request.state, "site", None) or SITES["vitrina"]
    return {
        "site": site,
        "site_name": site.name,
        "site_title_suffix": site.title_suffix,
        "site_logo": site.logo_text,
        "site_css": site.css_file,
        "site_contacts": site.contacts,
        "show_contacts": site.show_contacts,
        "nav_items": site.nav_items,
    }


def _base_url(request: Request) -> str:
    """Базовый URL сайта с учётом прокси (X-Forwarded-Proto/Host) для canonical и schema."""
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or getattr(request.url, "netloc", "") or "").strip()
    proto = (request.headers.get("x-forwarded-proto") or getattr(request.url, "scheme", "https") or "https").split(",")[0].strip().lower() or "https"
    if not host:
        host = getattr(request.url, "netloc", "") or "localhost:8000"
    return f"{proto}://{host}".rstrip("/")

# Разрешённые теги и атрибуты для описания объекта (защита от XSS)
ALLOWED_TAGS = ["p", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li", "a", "span"]
ALLOWED_ATTRS = {"a": ["href", "title", "target", "rel"]}


def _sanitize_html(value: Optional[str]) -> Markup:
    if not value or not value.strip():
        return Markup("")
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", "<br>\n")
    cleaned = bleach.clean(
        text,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        strip=True,
    )
    return Markup(cleaned)


templates.env.filters["sanitize_html"] = _sanitize_html


def _fmt_area(value) -> str:
    """Format area: drop .0 for whole numbers, keep one decimal otherwise."""
    if value is None:
        return "—"
    f = float(value)
    if f == int(f):
        return f"{int(f):,}".replace(",", " ")
    return f"{f:,.1f}".replace(",", " ")


templates.env.filters["fmt_area"] = _fmt_area

_SHORT_CATEGORY = {
    "Свободного назначения": "Свободное",
    "Торговая площадь": "Торговое",
    "Промышленное": "Промышленное",
}


def _short_category(value) -> str:
    if not value:
        return "—"
    return _SHORT_CATEGORY.get(value, value)


templates.env.filters["short_cat"] = _short_category


@router.get("/")
async def read_root(request: Request, db: AsyncSession = Depends(get_db)):
    stmt_count = select(func.count()).select_from(Property).where(Property.is_active == True)
    total_properties = (await db.execute(stmt_count)).scalar() or 0
    rent_count = (await db.execute(select(func.count()).select_from(Property).where(Property.is_active == True, Property.deal_type == "Аренда"))).scalar() or 0
    sale_count = (await db.execute(select(func.count()).select_from(Property).where(Property.is_active == True, Property.deal_type == "Продажа"))).scalar() or 0

    category_names = ["Офис", "Торговая площадь", "Свободного назначения", "Промышленное", "Склад", "Здание", "ГАБ"]
    cat_counts = {}
    for cat in category_names:
        cnt = (await db.execute(
            select(func.count()).select_from(Property).where(Property.is_active == True, Property.category == cat)
        )).scalar() or 0
        cat_counts[cat] = cnt

    base_url = _base_url(request)
    return templates.TemplateResponse(
        _tpl(request, "index.html"),
        {
            "request": request,
            "base_url": base_url,
            "total_properties": total_properties,
            "rent_count": rent_count,
            "sale_count": sale_count,
            "cat_counts": cat_counts,
            **get_public_contacts(),
            **_site_ctx(request),
        },
    )


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
    object_type: Optional[str] = Query(None, description="building|unit"),
):
    stmt = build_search_query(q, deal_type, category, min_price, max_price, min_area, max_area, object_type)
    stmt_ordered = _search_order_by(stmt, sort)

    result_all = await db.execute(stmt_ordered)
    all_filtered = result_all.unique().scalars().all()

    total_items = len(all_filtered)

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

    has_active_filters = bool(
        (deal_type and deal_type != "Все")
        or (category and category != "Все")
        or q
        or min_price
        or max_price
        or min_area
        or max_area
        or object_type
    )

    building_groups = group_properties_by_building(all_filtered, has_active_filters)

    return templates.TemplateResponse(
        _tpl(request, "search.html"),
        {
            "request": request,
            "base_url": _base_url(request),
            "building_groups": building_groups,
            "total_items": total_items,
            "preview_count": BUILDING_PREVIEW_COUNT,
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
            "object_type": object_type or "",
            "has_active_filters": has_active_filters,
            **get_public_contacts(),
            **_site_ctx(request),
        },
    )


@router.get("/map")
async def map_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    q: Optional[str] = None,
    deal_type: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[str] = None,
    max_price: Optional[str] = None,
    min_area: Optional[str] = None,
    max_area: Optional[str] = None,
):
    stmt = build_search_query(q, deal_type, category, min_price, max_price, min_area, max_area)
    result = await db.execute(stmt)
    all_props = result.scalars().all()

    map_properties = [
        {
            "id": p.id,
            "slug": p.slug or "",
            "title": p.title or "",
            "address": p.address or "",
            "category": p.category or "",
            "deal_type": p.deal_type or "",
            "area": p.area,
            "latitude": float(p.latitude),
            "longitude": float(p.longitude),
            "main_image": (p.main_image if (p.main_image and p.main_image.startswith("/")) else "/" + (p.main_image or "")) if p.main_image else "",
            "price": p.price,
        }
        for p in all_props
        if p.latitude is not None and p.longitude is not None
    ]

    return templates.TemplateResponse(
        _tpl(request, "map.html"),
        {
            "request": request,
            "base_url": _base_url(request),
            "map_properties": map_properties,
            "map_properties_json": json.dumps(map_properties),
            "total_items": len(map_properties),
            "yandex_maps_api_key": os.getenv("YANDEX_MAPS_API_KEY", ""),
            "deal_type": deal_type,
            "category": category,
            "q": q,
            "min_price": min_price,
            "max_price": max_price,
            "min_area": min_area,
            "max_area": max_area,
            **get_public_contacts(),
            **_site_ctx(request),
        },
    )


@router.get("/catalog/{slug}")
async def catalog_category_page(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    sort: Optional[str] = Query("date_desc"),
):
    from app.seo_categories import CATEGORY_MAP
    cat_data = CATEGORY_MAP.get(slug)
    if not cat_data:
        raise HTTPException(status_code=404, detail="Category not found")

    category_name = cat_data["category"]
    site = getattr(request.state, "site", None) or SITES["vitrina"]
    site_id = site.id

    stmt = build_search_query(category=category_name)
    stmt = _search_order_by(stmt, sort)
    result_all = await db.execute(stmt)
    all_filtered = result_all.unique().scalars().all()
    total_items = len(all_filtered)

    building_groups = group_properties_by_building(all_filtered, has_active_filters=True)

    base_url = _base_url(request)
    other_categories = [
        {"slug": s, "label": d["label"]}
        for s, d in CATEGORY_MAP.items() if s != slug
    ]

    return templates.TemplateResponse(
        _tpl(request, "catalog.html"),
        {
            "request": request,
            "base_url": base_url,
            "cat": cat_data,
            "cat_slug": slug,
            "site_id": site_id,
            "building_groups": building_groups,
            "total_items": total_items,
            "preview_count": BUILDING_PREVIEW_COUNT,
            "sort": sort or "date_desc",
            "other_categories": other_categories,
            "yandex_maps_api_key": os.getenv("YANDEX_MAPS_API_KEY", ""),
            **get_public_contacts(),
            **_site_ctx(request),
        },
    )


@router.get("/faq")
async def faq_page(request: Request):
    return templates.TemplateResponse(
        _tpl(request, "faq.html"),
        {"request": request, "base_url": _base_url(request), **get_public_contacts(), **_site_ctx(request)},
    )


@router.get("/about")
async def about_page(request: Request):
    tpl_name = _tpl(request, "about.html")
    try:
        templates.get_template(tpl_name)
    except Exception:
        raise HTTPException(status_code=404, detail="Page not found")
    return templates.TemplateResponse(
        tpl_name,
        {"request": request, "base_url": _base_url(request), **get_public_contacts(), **_site_ctx(request)},
    )


@router.get("/contacts")
async def contacts_page(request: Request):
    tpl_name = _tpl(request, "contacts.html")
    try:
        templates.get_template(tpl_name)
    except Exception:
        raise HTTPException(status_code=404, detail="Page not found")
    return templates.TemplateResponse(
        tpl_name,
        {"request": request, "base_url": _base_url(request), **get_public_contacts(), **_site_ctx(request)},
    )


@router.get("/property/{slug}")
async def read_property(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Property)
        .options(
            joinedload(Property.images),
            joinedload(Property.documents),
            selectinload(Property.children),
            selectinload(Property.parent).selectinload(Property.children),
            selectinload(Property.parent).joinedload(Property.images),
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
                selectinload(Property.parent).selectinload(Property.children),
                selectinload(Property.parent).joinedload(Property.images),
            )
            .where(Property.id == int(slug))
        )
        result = await db.execute(stmt)
        property = result.unique().scalars().first()
        if property and property.slug:
            return RedirectResponse(url=f"/property/{property.slug}", status_code=301)
    if not property:
        raise HTTPException(status_code=404, detail="Object not found")

    building = getattr(property, "parent", None) or property
    children_list = list(building.children or []) if hasattr(building, "children") else []
    building_nav_items = [(building.id, building.title or f"Объект #{building.id}", f"/property/{building.slug or building.id}")]
    for c in sorted(children_list, key=lambda x: x.id):
        building_nav_items.append((c.id, c.title or f"Объект #{c.id}", f"/property/{c.slug or c.id}"))

    has_own_media = bool(getattr(property, "main_image", None) or (getattr(property, "images", None) and len(property.images) > 0))
    display_for_media = (getattr(property, "parent", None) if property.parent and not has_own_media else None) or property

    if getattr(property, "parent", None):
        available_units = [
            child for child in (building.children or [])
            if child.is_active and child.id != property.id
        ]
    else:
        available_units = []

    site_url = _base_url(request)
    return templates.TemplateResponse(
        _tpl(request, "property-single.html"),
        {
            "request": request,
            "property": property,
            "available_units": available_units,
            "building_nav_items": building_nav_items,
            "display_for_media": display_for_media,
            "site_url": site_url,
            **get_public_contacts(),
            **_site_ctx(request),
        },
    )


@router.get("/sitemap.xml")
async def sitemap_xml(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    """
    Простой sitemap.xml для поисковых систем:
    - главная, поиск, FAQ
    - все активные объекты (Property.is_active == True).
    """
    # Базовый URL с учётом прокси
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc or "").strip()
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "https").split(",")[0].strip() or "https"
    base = f"{proto}://{host}".rstrip("/") if host else str(request.url.replace(path="", query="")).rstrip("/")

    from app.seo_categories import ALL_CATEGORY_SLUGS

    site = getattr(request.state, "site", None)
    static_pages = [
        ("/", "daily", "1.0"),
        ("/search", "daily", "0.9"),
        ("/map", "weekly", "0.7"),
    ]
    for cat_slug in ALL_CATEGORY_SLUGS:
        static_pages.append((f"/catalog/{cat_slug}", "daily", "0.8"))
    if site and site.id == "diapazon":
        static_pages.append(("/about", "monthly", "0.6"))
        static_pages.append(("/contacts", "monthly", "0.6"))
    else:
        static_pages.append(("/faq", "monthly", "0.5"))

    stmt = select(Property).where(Property.is_active == True)
    result = await db.execute(stmt)
    props = result.scalars().all()

    url_entries: list[str] = []
    for path, freq, prio in static_pages:
        url_entries.append(
            f"<url><loc>{base}{path}</loc>"
            f"<changefreq>{freq}</changefreq><priority>{prio}</priority></url>"
        )
    for p in props:
        slug = p.slug or str(p.id)
        lastmod = ""
        if p.updated_at:
            lastmod = f"<lastmod>{p.updated_at.strftime('%Y-%m-%d')}</lastmod>"
        elif p.created_at:
            lastmod = f"<lastmod>{p.created_at.strftime('%Y-%m-%d')}</lastmod>"
        url_entries.append(
            f"<url><loc>{base}/property/{slug}</loc>"
            f"{lastmod}<changefreq>weekly</changefreq><priority>0.6</priority></url>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(url_entries)
        + "</urlset>"
    )
    return Response(content=xml, media_type="application/xml")



@router.get("/avito.xml")
async def get_avito_feed_route(db: AsyncSession = Depends(get_db)):
    from app.settings_store import is_avito_feed_enabled
    if not is_avito_feed_enabled():
        empty = '<?xml version="1.0" encoding="UTF-8"?><Ads formatVersion="3" target="Avito.ru"/>'
        return Response(content=empty, media_type="application/xml")
    stmt = (
        select(Property)
        .where(Property.is_active == True, Property.publish_on_avito == True)
        .options(selectinload(Property.images))
    )
    result = await db.execute(stmt)
    properties = result.scalars().all()
    xml_content = generate_avito_feed_full(properties)
    return Response(content=xml_content, media_type="application/xml")


@router.get("/jcat.xml")
async def jcat_xml_feed(db: AsyncSession = Depends(get_db)):
    xml = await generate_jcat_feed(db)
    return Response(content=xml, media_type="application/xml; charset=utf-8")


@router.get("/cian.xml")
async def get_cian_feed_route(db: AsyncSession = Depends(get_db)):
    """Публичный XML-фид для импорта объявлений на Циан (URL указать в ЛК Циан)."""
    from app.settings_store import is_cian_feed_enabled
    if not is_cian_feed_enabled():
        empty = '<?xml version="1.0" encoding="UTF-8"?><feed version="2"/>'
        return Response(content=empty, media_type="application/xml")
    stmt = (
        select(Property)
        .where(Property.is_active == True, Property.publish_on_cian == True)
        .options(selectinload(Property.images))
    )
    result = await db.execute(stmt)
    properties = result.scalars().all()
    xml_content = generate_cian_feed(properties)
    return Response(content=xml_content, media_type="application/xml")
