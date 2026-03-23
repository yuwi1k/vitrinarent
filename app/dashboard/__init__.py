"""
Кастомная панель управления (Dashboard): FastAPI + Jinja2 + Bootstrap 5.
Единственная точка входа для управления; логин через свою форму /dashboard/login.

Роуты разнесены по модулям: auth, pages, properties, export, settings, media.
"""
from fastapi import APIRouter

from app.dashboard.auth import router as auth_router
from app.dashboard.pages import router as pages_router
from app.dashboard.properties import router as properties_router
from app.dashboard.export import router as export_router
from app.dashboard.settings import router as settings_router
from app.dashboard.media import router as media_router
from app.dashboard.scheduler_ui import router as scheduler_router
from app.dashboard.errors_ui import router as errors_router
from app.dashboard.messages_ui import router as messages_router
from app.dashboard.promotion_ui import router as promotion_router
from app.dashboard.statistics_ui import router as statistics_router
from app.dashboard.telegram_ui import router as telegram_router
from app.dashboard.userbot_auth import router as userbot_router

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

router.include_router(auth_router)
router.include_router(pages_router)
router.include_router(export_router)
router.include_router(settings_router)
router.include_router(properties_router)
router.include_router(media_router)
router.include_router(scheduler_router)
router.include_router(errors_router)
router.include_router(messages_router)
router.include_router(promotion_router)
router.include_router(statistics_router)
router.include_router(telegram_router)
router.include_router(userbot_router)
