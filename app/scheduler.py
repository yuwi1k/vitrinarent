import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

_MSK = timezone(timedelta(hours=3))

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.avito_client import AvitoAutoloadClient
from app.cian_client import CianApiClient
from app.database import AsyncSessionLocal
from app.feed import generate_avito_feed_full
from app.models import Property
from app.telegram_bot import notifier

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self) -> None:
        self.results: Dict[str, Dict[str, Any]] = {}

    def _mark_running(self, job_name: str) -> None:
        prev = self.results.get(job_name, {})
        self.results[job_name] = {**prev, "status": "running", "message": ""}

    def _record(self, job_name: str, status: str, message: str, started_at: float) -> None:
        self.results[job_name] = {
            "last_run": datetime.now(_MSK).isoformat(),
            "status": status,
            "message": message,
            "duration_ms": round((time.monotonic() - started_at) * 1000),
        }

    async def job_upload_avito_feed(self) -> None:
        self._mark_running("upload_avito_feed")
        t0 = time.monotonic()
        try:
            from app.settings_store import is_avito_feed_enabled
            if not is_avito_feed_enabled():
                self._record("upload_avito_feed", "skipped", "Avito feed disabled", t0)
                return

            async with AsyncSessionLocal() as db:
                stmt = (
                    select(Property)
                    .where(Property.is_active.is_(True), Property.publish_on_avito.is_(True))
                    .options(selectinload(Property.images))
                    .order_by(Property.id.asc())
                )
                result = await db.execute(stmt)
                properties = result.scalars().all()
                xml_bytes = generate_avito_feed_full(properties)

            client = AvitoAutoloadClient()
            resp = await client.upload_feed()
            msg = f"Uploaded feed ({len(properties)} props, {len(xml_bytes)} bytes). API: {resp.get('status_code')}"
            logger.info("scheduler: upload_avito_feed OK — %s", msg)
            self._record("upload_avito_feed", "ok", msg, t0)
            await notifier.send_feed_upload_result(
                "Avito", len(properties), True,
                f"API ответ: {resp.get('status_code')}",
            )
        except Exception as exc:
            logger.exception("scheduler: upload_avito_feed FAILED")
            self._record("upload_avito_feed", "error", str(exc), t0)
            await notifier.send_feed_upload_result("Avito", 0, False, str(exc))
            await notifier.send_scheduler_error("upload_avito_feed", str(exc))

    async def job_sync_avito_statuses(self) -> None:
        self._mark_running("sync_avito_statuses")
        t0 = time.monotonic()
        try:
            client = AvitoAutoloadClient()
            payload = await client.get_last_completed_report_items()
            items = payload.get("items") or []

            updated = skipped = not_found = 0
            async with AsyncSessionLocal() as db:
                for item in items:
                    ad_id = item.get("ad_id")
                    if not ad_id:
                        skipped += 1
                        continue
                    try:
                        prop_id = int(str(ad_id))
                    except ValueError:
                        skipped += 1
                        continue
                    row = await db.execute(select(Property).where(Property.id == prop_id))
                    prop = row.scalar_one_or_none()
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

            error_count = sum(
                1 for i in items
                if (i.get("errors") or []) + (i.get("warnings") or [])
            )
            msg = f"items={len(items)} updated={updated} skipped={skipped} not_found={not_found}"
            logger.info("scheduler: sync_avito_statuses OK — %s", msg)
            self._record("sync_avito_statuses", "ok", msg, t0)
            await notifier.send_sync_result("Avito", updated, len(items), error_count)
        except Exception as exc:
            logger.exception("scheduler: sync_avito_statuses FAILED")
            self._record("sync_avito_statuses", "error", str(exc), t0)
            await notifier.send_scheduler_error("sync_avito_statuses", str(exc))

    async def job_sync_cian_statuses(self) -> None:
        self._mark_running("sync_cian_statuses")
        t0 = time.monotonic()
        try:
            client = CianApiClient()
            all_announcements: list[dict] = []
            page = 1
            page_size = 100
            max_pages = 50
            while True:
                resp = await client.get_my_offers(page=page, page_size=page_size)
                result_data = (resp.get("result") or {}) if isinstance(resp.get("result"), dict) else {}
                announcements = result_data.get("announcements") or []
                all_announcements.extend(announcements)
                total = result_data.get("totalCount")
                if total is not None and len(all_announcements) >= total:
                    break
                if len(announcements) < page_size:
                    break
                page += 1
                if page > max_pages:
                    logger.warning("scheduler: CIAN sync pagination limit reached (%d pages)", max_pages)
                    break
                await asyncio.sleep(0.12)

            updated = skipped = not_found = 0
            async with AsyncSessionLocal() as db:
                for ann in all_announcements:
                    external_id = ann.get("externalId")
                    if external_id is None:
                        skipped += 1
                        continue
                    try:
                        prop_id = int(str(external_id))
                    except (ValueError, TypeError):
                        skipped += 1
                        continue
                    row = await db.execute(select(Property).where(Property.id == prop_id))
                    prop = row.scalar_one_or_none()
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

            msg = f"offers={len(all_announcements)} updated={updated} skipped={skipped} not_found={not_found}"
            logger.info("scheduler: sync_cian_statuses OK — %s", msg)
            self._record("sync_cian_statuses", "ok", msg, t0)
            await notifier.send_sync_result("Циан", updated, len(all_announcements))
        except Exception as exc:
            logger.exception("scheduler: sync_cian_statuses FAILED")
            self._record("sync_cian_statuses", "error", str(exc), t0)
            await notifier.send_scheduler_error("sync_cian_statuses", str(exc))

    async def job_collect_statistics(self) -> None:
        self._mark_running("collect_statistics")
        t0 = time.monotonic()
        try:
            avito_updated = cian_updated = 0

            avito_client = AvitoAutoloadClient()
            user_id = ""
            try:
                user_id = await avito_client.get_user_id()
            except Exception:
                logger.warning("scheduler: collect_statistics — could not get Avito user_id, skipping Avito stats")

            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Property).where(Property.is_active.is_(True)))
                props = result.scalars().all()

                if user_id:
                    avito_ids: list[tuple[int, int]] = []
                    for p in props:
                        ad = p.avito_data or {}
                        aid = ad.get("AvitoId") if isinstance(ad, dict) else None
                        if aid:
                            try:
                                avito_ids.append((p.id, int(str(aid))))
                            except (ValueError, TypeError):
                                pass

                    batch_size = 200
                    stats_map: Dict[int, Dict[str, Any]] = {}
                    for i in range(0, len(avito_ids), batch_size):
                        batch = avito_ids[i:i + batch_size]
                        item_ids = [aid for _, aid in batch]
                        try:
                            resp = await avito_client.get_items_stats(user_id, item_ids)
                            items_list = resp.get("result", {}).get("items") or resp.get("items") or []
                            for item in items_list:
                                avito_item_id = item.get("item_id") or item.get("itemId")
                                if not avito_item_id:
                                    continue
                                periods = item.get("stats") or []
                                total_views = sum(p.get("uniqViews", 0) for p in periods)
                                total_contacts = sum(p.get("uniqContacts", 0) for p in periods)
                                total_favorites = sum(p.get("uniqFavorites", 0) for p in periods)
                                stats_map[int(avito_item_id)] = {
                                    "views": total_views,
                                    "contacts": total_contacts,
                                    "favorites": total_favorites,
                                }
                        except Exception:
                            logger.warning("scheduler: collect_statistics — Avito stats batch failed", exc_info=True)
                        if i + batch_size < len(avito_ids):
                            await asyncio.sleep(0.2)

                    for prop_id, avito_item_id in avito_ids:
                        item_stats = stats_map.get(avito_item_id)
                        if not item_stats:
                            continue
                        row = await db.execute(select(Property).where(Property.id == prop_id))
                        prop_obj = row.scalar_one_or_none()
                        if not prop_obj:
                            continue
                        sd = dict(prop_obj.stats_data or {})
                        sd["avito_views"] = item_stats.get("views", 0)
                        sd["avito_contacts"] = item_stats.get("contacts", 0)
                        sd["avito_favorites"] = item_stats.get("favorites", 0)
                        prop_obj.stats_data = sd
                        flag_modified(prop_obj, "stats_data")
                        avito_updated += 1

                cian_client = CianApiClient()
                try:
                    cian_page = 1
                    while True:
                        cian_resp = await cian_client.get_my_offers(page=cian_page, page_size=100)
                        result_data = (cian_resp.get("result") or {}) if isinstance(cian_resp.get("result"), dict) else {}
                        announcements = result_data.get("announcements") or []
                        for ann in announcements:
                            ext_id = ann.get("externalId")
                            if ext_id is None:
                                continue
                            try:
                                prop_id = int(str(ext_id))
                            except (ValueError, TypeError):
                                continue
                            row = await db.execute(select(Property).where(Property.id == prop_id))
                            prop_obj = row.scalar_one_or_none()
                            if not prop_obj:
                                continue
                            sd = dict(prop_obj.stats_data or {})
                            ann_stats = ann.get("stats") or {}
                            total_stats = ann_stats.get("total") if isinstance(ann_stats.get("total"), dict) else {}
                            sd["cian_views"] = total_stats.get("views", 0) if total_stats else 0
                            sd["cian_contacts"] = total_stats.get("phoneShows", 0) if total_stats else 0
                            prop_obj.stats_data = sd
                            flag_modified(prop_obj, "stats_data")
                            cian_updated += 1
                        total_count = result_data.get("totalCount")
                        if total_count is not None and cian_page * 100 >= total_count:
                            break
                        if len(announcements) < 100:
                            break
                        cian_page += 1
                        if cian_page > 50:
                            break
                        await asyncio.sleep(0.12)
                except Exception:
                    logger.warning("scheduler: collect_statistics — CIAN stats failed", exc_info=True)

                await db.commit()

            msg = f"avito_updated={avito_updated} cian_updated={cian_updated}"
            logger.info("scheduler: collect_statistics OK — %s", msg)
            self._record("collect_statistics", "ok", msg, t0)
        except Exception as exc:
            logger.exception("scheduler: collect_statistics FAILED")
            self._record("collect_statistics", "error", str(exc), t0)
            await notifier.send_scheduler_error("collect_statistics", str(exc))

    async def job_daily_digest(self) -> None:
        self._mark_running("daily_digest")
        t0 = time.monotonic()
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Property).where(Property.is_active.is_(True)))
                props = result.scalars().all()

            total_views = sum(
                ((p.stats_data or {}).get("avito_views", 0) + (p.stats_data or {}).get("cian_views", 0))
                for p in props if isinstance(p.stats_data, dict)
            )
            total_contacts = sum(
                ((p.stats_data or {}).get("avito_contacts", 0) + (p.stats_data or {}).get("cian_contacts", 0))
                for p in props if isinstance(p.stats_data, dict)
            )
            active_avito = sum(
                1 for p in props
                if isinstance(p.avito_data, dict) and (p.avito_data or {}).get("AvitoStatus") == "active"
            )
            active_cian = sum(
                1 for p in props
                if isinstance(p.cian_data, dict) and (p.cian_data or {}).get("CianStatus") == "published"
            )
            await notifier.send_daily_digest(active_avito, active_cian, total_views, total_contacts)

            from app.notification_config import get_scenarios

            scenarios = get_scenarios()
            report: Dict[str, list] = {s.key: [] for s in scenarios}

            for p in props:
                sd = p.stats_data if isinstance(p.stats_data, dict) else {}
                title = p.title or f"Объект #{p.id}"

                has_avito = isinstance(p.avito_data, dict) and p.avito_data.get("AvitoId")
                has_cian = isinstance(p.cian_data, dict) and p.cian_data.get("CianOfferId")
                is_published = bool(has_avito or has_cian)

                views = sd.get("avito_views", 0) + sd.get("cian_views", 0)
                contacts = sd.get("avito_contacts", 0) + sd.get("cian_contacts", 0)
                favorites = sd.get("avito_favorites", 0)
                conv = round(contacts / views * 100, 1) if views > 0 else 0.0

                info: Dict[str, Any] = {
                    "id": p.id, "title": title,
                    "views": views, "contacts": contacts,
                    "favorites": favorites, "conversion": conv,
                }

                for s in scenarios:
                    if not s.enabled:
                        continue
                    if s.key == "not_published":
                        if not is_published:
                            report[s.key].append(info)
                        continue
                    if not is_published:
                        continue
                    if s.min_views and views < s.min_views:
                        continue
                    if s.max_views is not None and views > s.max_views:
                        continue
                    if s.max_contacts is not None and contacts > s.max_contacts:
                        continue
                    if s.min_contacts and contacts < s.min_contacts:
                        continue
                    if s.min_favorites and favorites < s.min_favorites:
                        continue
                    if s.min_conversion and conv < s.min_conversion:
                        continue
                    if s.max_conversion is not None and conv > s.max_conversion:
                        continue
                    report[s.key].append(info)

            if any(report[k] for k in report):
                await notifier.send_stats_report(report, scenarios)

            msg = f"views={total_views} contacts={total_contacts}"
            logger.info("scheduler: daily_digest OK — %s", msg)
            self._record("daily_digest", "ok", msg, t0)
        except Exception as exc:
            logger.exception("scheduler: daily_digest FAILED")
            self._record("daily_digest", "error", str(exc), t0)
            await notifier.send_scheduler_error("daily_digest", str(exc))

    async def job_check_errors_and_notify(self) -> None:
        self._mark_running("check_errors_and_notify")
        t0 = time.monotonic()
        try:
            avito_error_count = cian_error_count = 0

            cian_client = CianApiClient()
            try:
                order_data = await cian_client.get_order_report()
                order_result = order_data.get("result") or {}
                offers = order_result.get("offers") or []
                async with AsyncSessionLocal() as db:
                    for offer in offers:
                        offer_errors = offer.get("errors") or []
                        if not offer_errors:
                            continue
                        ext_id = offer.get("externalId")
                        if ext_id is None:
                            continue
                        try:
                            prop_id = int(str(ext_id))
                        except (ValueError, TypeError):
                            continue
                        row = await db.execute(select(Property).where(Property.id == prop_id))
                        prop = row.scalar_one_or_none()
                        if not prop:
                            continue
                        cd = dict(prop.cian_data or {})
                        cd["ImportErrors"] = [str(e) for e in offer_errors]
                        prop.cian_data = cd
                        flag_modified(prop, "cian_data")
                        cian_error_count += 1
                    await db.commit()
            except Exception:
                logger.warning("scheduler: check_errors — CIAN order report failed", exc_info=True)

            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Property).where(Property.is_active.is_(True)))
                props = result.scalars().all()

            for platform, data_attr, error_key in [
                ("Avito", "avito_data", "AutoloadErrors"),
                ("CIAN", "cian_data", "ImportErrors"),
            ]:
                error_props = []
                for p in props:
                    data = getattr(p, data_attr, None) or {}
                    if isinstance(data, dict) and data.get(error_key):
                        error_props.append(f"ID {p.id}: {p.title or '—'}")
                if error_props:
                    details = "\n".join(error_props[:20])
                    await notifier.send_feed_error_alert(platform, len(error_props), details)
                if platform == "Avito":
                    avito_error_count = len(error_props)

            msg = f"avito_errors={avito_error_count} cian_errors={cian_error_count}"
            logger.info("scheduler: check_errors_and_notify OK — %s", msg)
            self._record("check_errors_and_notify", "ok", msg, t0)
        except Exception as exc:
            logger.exception("scheduler: check_errors_and_notify FAILED")
            self._record("check_errors_and_notify", "error", str(exc), t0)
            await notifier.send_scheduler_error("check_errors_and_notify", str(exc))


    async def job_send_broadcast(self) -> None:
        self._mark_running("send_broadcast")
        t0 = time.monotonic()
        try:
            from app.telegram_broadcast import load_config, broadcast_service
            config = load_config()
            if not config.get("enabled", False):
                self._record("send_broadcast", "skipped", "Broadcast disabled", t0)
                return
            result = await broadcast_service.send_next()
            if result.get("ok"):
                msg = (
                    f"index={result['index'] + 1} "
                    f"channels={result['channels']} "
                    f"success={result['success']} fail={result['fail']}"
                )
                self._record("send_broadcast", "ok", msg, t0)
            else:
                self._record("send_broadcast", "skipped", result.get("reason", ""), t0)
        except Exception as exc:
            logger.exception("scheduler: send_broadcast FAILED")
            self._record("send_broadcast", "error", str(exc), t0)


scheduler_service = SchedulerService()

_scheduler: Optional[AsyncIOScheduler] = None


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        logger.warning("Scheduler already running, skipping start")
        return _scheduler

    _scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    now = datetime.now().replace(second=0, microsecond=0)
    offset_30m = now + timedelta(minutes=30)
    offset_1h = now + timedelta(hours=1)

    # misfire_grace_time — допустимое опоздание (в секундах) прежде чем job считается пропущенным
    _grace = 600  # 10 минут

    _scheduler.add_job(
        scheduler_service.job_upload_avito_feed,
        "interval", hours=3, id="upload_avito_feed",
        name="Upload Avito feed", misfire_grace_time=_grace,
    )
    _scheduler.add_job(
        scheduler_service.job_sync_avito_statuses,
        "interval", hours=3, start_date=offset_30m, id="sync_avito_statuses",
        name="Sync Avito statuses", misfire_grace_time=_grace,
    )
    _scheduler.add_job(
        scheduler_service.job_sync_cian_statuses,
        "interval", hours=3, start_date=offset_1h, id="sync_cian_statuses",
        name="Sync CIAN statuses", misfire_grace_time=_grace,
    )
    _scheduler.add_job(
        scheduler_service.job_collect_statistics,
        "interval", hours=1, id="collect_statistics",
        name="Collect statistics", misfire_grace_time=_grace,
    )
    _scheduler.add_job(
        scheduler_service.job_daily_digest,
        "cron", hour=9, minute=0, id="daily_digest",
        name="Daily digest", misfire_grace_time=_grace,
    )
    _scheduler.add_job(
        scheduler_service.job_check_errors_and_notify,
        "interval", hours=3, start_date=offset_30m, id="check_errors_and_notify",
        name="Check errors and notify", misfire_grace_time=_grace,
    )

    # Рассылка в Telegram-каналы
    try:
        from app.telegram_broadcast import load_config as _load_bc
        bc_config = _load_bc()
        bc_minutes = max(1, bc_config.get("interval_minutes", 60))
    except Exception:
        bc_minutes = 60
    _scheduler.add_job(
        scheduler_service.job_send_broadcast,
        "interval", minutes=bc_minutes, id="send_broadcast",
        name="Telegram broadcast", misfire_grace_time=_grace,
    )

    _scheduler.start()
    logger.info("Scheduler started with %d jobs", len(_scheduler.get_jobs()))
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
    _scheduler = None


def reschedule_broadcast(config: Dict[str, Any]) -> None:
    """Перезапускает или останавливает job рассылки при изменении конфига из бота."""
    global _scheduler
    if not _scheduler or not _scheduler.running:
        return
    job_id = "send_broadcast"
    enabled = config.get("enabled", False)
    minutes = max(1, config.get("interval_minutes", 60))
    try:
        existing = _scheduler.get_job(job_id)
        if enabled:
            if existing:
                _scheduler.reschedule_job(job_id, trigger="interval", minutes=minutes)
            else:
                _scheduler.add_job(
                    scheduler_service.job_send_broadcast,
                    "interval", minutes=minutes, id=job_id,
                    name="Telegram broadcast",
                )
            logger.info("scheduler: broadcast job rescheduled to %d min", minutes)
        else:
            if existing:
                _scheduler.pause_job(job_id)
                logger.info("scheduler: broadcast job paused")
    except Exception:
        logger.exception("scheduler: failed to reschedule broadcast job")


def get_scheduler_status() -> Dict[str, Any]:
    jobs_info = {}
    if _scheduler:
        for job in _scheduler.get_jobs():
            jobs_info[job.id] = {
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            }
    return {
        "running": bool(_scheduler and _scheduler.running),
        "jobs": jobs_info,
        "results": scheduler_service.results,
    }
