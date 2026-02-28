import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqladmin import Admin
from starlette.middleware.sessions import SessionMiddleware

from app.database import engine
from app.admin_views import (
    AdminAuth,
    PropertyAdmin,
    PropertyImageAdmin,
    PropertyDocumentAdmin,
    ObjectFoldersView,
)
from app.routers import router as public_router

# Инициализируем приложение (схема БД — через миграции Alembic)
app = FastAPI(
    title="Vitrina Real Estate",
    description="Внутренний каталог коммерческой недвижимости"
)

# --- ПОДКЛЮЧЕНИЕ СТАТИКИ И ШАБЛОНОВ ---
app.mount("/static", StaticFiles(directory="static"), name="static")

# Сессионный middleware для хранения логина админа
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY", "123"),
)


# --- ПУБЛИЧНЫЕ МАРШРУТЫ ---
app.include_router(public_router)

# --- ПОДКЛЮЧЕНИЕ АДМИНКИ ---
authentication_backend = AdminAuth(
    secret_key=os.getenv("ADMIN_SECRET_KEY", "123")
)
admin = Admin(app, engine, authentication_backend=authentication_backend)
admin.add_base_view(ObjectFoldersView)
admin.add_view(PropertyAdmin)
admin.add_view(PropertyImageAdmin)
admin.add_view(PropertyDocumentAdmin)