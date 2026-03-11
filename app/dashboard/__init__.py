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

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

router.include_router(auth_router)
router.include_router(pages_router)
router.include_router(export_router)
router.include_router(settings_router)
router.include_router(properties_router)
router.include_router(media_router)
