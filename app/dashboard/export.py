"""
Экспорт фидов (Авито, Циан), CSV и синхронизация статусов.
"""
import asyncio
import csv
import io
import logging
import os

from fastapi import APIRouter, Request, Depends

logger = logging.getLogger(__name__)
from fastapi.responses import Response, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.database import get_db
from app.dashboard.common import check_admin, templates
from app.models import Property
from app.feed import generate_avito_feed_full
from app.feed_cian import generate_cian_feed
from app.avito_client import AvitoAutoloadClient
from app.cian_client import CianApiClient

router = APIRouter()


@router.get("/export/avito", dependencies=[Depends(check_admin)])
async def export_avito_feed(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Property)
        .where(Property.is_active.is_(True), Property.publish_on_avito.is_(True))
        .options(selectinload(Property.images))
        .order_by(Property.id.asc())
    )
    result = await db.execute(stmt)
    properties = result.scalars().all()
    xml_bytes = generate_avito_feed_full(properties)
    return Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": 'attachment; filename="avito_feed.xml"'},
    )


@router.get("/export/avito-new", dependencies=[Depends(check_admin)])
async def export_avito_feed_new(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Property)
        .where(Property.is_active.is_(True), Property.publish_on_avito.is_(True))
        .options(selectinload(Property.images))
        .order_by(Property.id.asc())
    )
    result = await db.execute(stmt)
    all_properties = result.scalars().all()
    properties = []
    for p in all_properties:
        data = getattr(p, "avito_data", None)
        avito_id = ""
        if isinstance(data, dict):
            v = data.get("AvitoId")
            avito_id = str(v).strip() if v is not None else ""
        if not avito_id:
            properties.append(p)
    xml_bytes = generate_avito_feed_full(properties)
    return Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": 'attachment; filename="avito_feed_new.xml"'},
    )


@router.get("/export/avito-autoload-new", dependencies=[Depends(check_admin)])
async def export_avito_feed_new_autoload(db: AsyncSession = Depends(get_db)):
    """
    Запускает автозагрузку по настроенному фиду Авито через Autoload API.
    Возвращает JSON с кратким результатом.
    """
    client = AvitoAutoloadClient()
    try:
        result_payload = await client.upload_feed()
        return JSONResponse(
            {
                "ok": True,
                "message": "Автозагрузка через Autoload API Авито запущена.",
                "api_result": result_payload,
            }
        )
    except Exception as exc:
        logger.exception("Avito autoload upload failed")
        return JSONResponse(
            {
                "ok": False,
                "error": str(exc),
            },
            status_code=500,
        )


@router.get("/avito/sync", dependencies=[Depends(check_admin)])
async def avito_sync_autoload_statuses(db: AsyncSession = Depends(get_db)):
    """
    Синхронизирует статусы автозагрузки из последнего завершённого отчёта:
    проставляет AvitoId и статус в avito_data по полю ad_id (наш Property.id в фиде).
    """
    client = AvitoAutoloadClient()
    try:
        payload = await client.get_last_completed_report_items()
    except Exception as exc:
        logger.exception("Avito sync failed")
        return JSONResponse(
            {
                "ok": False,
                "error": str(exc),
            },
            status_code=500,
        )

    items = payload.get("items") or []
    updated = 0
    skipped = 0
    not_found = 0
    for item in items:
        ad_id = item.get("ad_id")
        if not ad_id:
            skipped += 1
            continue
        try:
            prop_id = int(str(ad_id))
        except ValueError:
            logger.warning("Avito sync: invalid ad_id=%s, skipping", ad_id)
            skipped += 1
            continue
        result = await db.execute(select(Property).where(Property.id == prop_id))
        prop = result.scalar_one_or_none()
        if not prop:
            not_found += 1
            continue
        data = dict(getattr(prop, "avito_data", None) or {})
        avito_id = item.get("avito_id")
        if avito_id is not None:
            data["AvitoId"] = str(avito_id)
        section = item.get("section") or {}
        section_slug = section.get("slug")
        if section_slug:
            data["AutoloadSectionSlug"] = section_slug
        avito_status = item.get("avito_status")
        if avito_status:
            data["AvitoStatus"] = avito_status
        avito_date_end = item.get("avito_date_end")
        if avito_date_end:
            data["AvitoDateEnd"] = str(avito_date_end)[:10]
        avito_url = item.get("url")
        if avito_url:
            data["AvitoUrl"] = avito_url
        item_errors = item.get("errors") or []
        item_warnings = item.get("warnings") or []
        autoload_errors = item_errors + item_warnings
        if autoload_errors:
            data["AutoloadErrors"] = autoload_errors
        elif "AutoloadErrors" in data:
            del data["AutoloadErrors"]
        prop.avito_data = data
        flag_modified(prop, "avito_data")
        updated += 1

    await db.commit()
    return JSONResponse(
        {
            "ok": True,
            "updated": updated,
            "total_items": len(items),
            "skipped": skipped,
            "not_found": not_found,
        }
    )


@router.get("/export/cian", dependencies=[Depends(check_admin)])
async def export_cian_feed(db: AsyncSession = Depends(get_db)):
    """Скачать XML-фид для выгрузки на Циан (коммерческая недвижимость)."""
    stmt = (
        select(Property)
        .where(Property.is_active.is_(True), Property.publish_on_cian.is_(True))
        .options(selectinload(Property.images))
        .order_by(Property.id.asc())
    )
    result = await db.execute(stmt)
    properties = result.scalars().all()
    xml_bytes = generate_cian_feed(properties)
    return Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": 'attachment; filename="cian_feed.xml"'},
    )


@router.get("/cian/import-status", dependencies=[Depends(check_admin)])
async def cian_import_status():
    """Получить состояние последнего импорта фида на Циан (get-last-order-info)."""
    client = CianApiClient()
    try:
        data = await client.get_last_order_info()
        return JSONResponse({"ok": True, "data": data})
    except Exception as exc:
        logger.exception("CIAN import-status check failed")
        return JSONResponse(
            {"ok": False, "error": str(exc)},
            status_code=500,
        )


@router.get("/cian/sync", dependencies=[Depends(check_admin)])
async def cian_sync_offer_statuses(db: AsyncSession = Depends(get_db)):
    """
    Синхронизирует статусы объявлений из API Циан (get-my-offers).
    Сопоставление по externalId = Property.id, сохраняет CianOfferId и статус в cian_data.
    """
    client = CianApiClient()
    try:
        all_announcements = []
        page = 1
        page_size = 100
        max_pages = 50
        while True:
            resp = await client.get_my_offers(page=page, page_size=page_size)
            result = (resp.get("result") or {}) if isinstance(resp.get("result"), dict) else {}
            announcements = result.get("announcements") or []
            all_announcements.extend(announcements)
            total = result.get("totalCount")
            if total is not None and len(all_announcements) >= total:
                break
            if len(announcements) < page_size:
                break
            page += 1
            if page > max_pages:
                logger.warning("CIAN sync: reached max_pages=%d limit, stopping pagination", max_pages)
                break
            await asyncio.sleep(0.12)
    except Exception as exc:
        logger.exception("CIAN sync failed")
        return JSONResponse(
            {"ok": False, "error": str(exc)},
            status_code=500,
        )

    updated = 0
    skipped = 0
    not_found = 0
    for ann in all_announcements:
        external_id = ann.get("externalId")
        if external_id is None:
            skipped += 1
            continue
        try:
            prop_id = int(str(external_id))
        except (ValueError, TypeError):
            logger.warning("CIAN sync: invalid externalId=%s, skipping", external_id)
            skipped += 1
            continue
        result = await db.execute(select(Property).where(Property.id == prop_id))
        prop = result.scalar_one_or_none()
        if not prop:
            not_found += 1
            continue
        data = dict(getattr(prop, "cian_data", None) or {})
        cian_id = ann.get("id")
        if cian_id is not None:
            data["CianOfferId"] = str(cian_id)
        status = ann.get("status")
        if status:
            data["CianStatus"] = status
        prop.cian_data = data
        flag_modified(prop, "cian_data")
        updated += 1

    await db.commit()
    return JSONResponse(
        {
            "ok": True,
            "updated": updated,
            "total_offers": len(all_announcements),
            "skipped": skipped,
            "not_found": not_found,
        }
    )


@router.get("/cian/register-feed", dependencies=[Depends(check_admin)])
async def cian_register_feed_info(request: Request):
    site_url = os.getenv("SITE_URL", "http://127.0.0.1:8000").rstrip("/")
    feed_url = f"{site_url}/cian.xml"
    return templates.TemplateResponse("dashboard/cian_register_feed.html", {
        "request": request,
        "feed_url": feed_url,
    })


@router.get("/export/csv", dependencies=[Depends(check_admin)])
async def export_properties_csv(db: AsyncSession = Depends(get_db)):
    stmt = select(Property).order_by(Property.parent_id.asc().nullsfirst(), Property.id.asc())
    result = await db.execute(stmt)
    properties = result.scalars().all()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["id", "parent_id", "title", "slug", "deal_type", "category", "price", "area", "address", "is_active"])
    for p in properties:
        writer.writerow([
            p.id,
            p.parent_id or "",
            (p.title or ""),
            (p.slug or ""),
            (p.deal_type or ""),
            (p.category or ""),
            p.price or 0,
            p.area or 0,
            (p.address or ""),
            "да" if p.is_active else "нет",
        ])
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="properties.csv"'},
    )
