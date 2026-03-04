import os
import time
from collections import defaultdict

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqladmin import Admin
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

load_dotenv()

# Rate limiting для логина: макс. 5 попыток в минуту с одного IP
_LOGIN_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_LOGIN_RATE_LIMIT = 5
_LOGIN_WINDOW_SEC = 60


def _login_url(request: Request) -> str:
    """URL страницы логина: тот же хост и схема (https если nginx передал X-Forwarded-Proto)."""
    try:
        proto = (request.headers.get("x-forwarded-proto") or "").strip().lower()
        if proto == "https":
            host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
            return f"https://{host.rstrip('/')}/admin/login"
        url = request.url.replace(path="/admin/login", query="")
        return str(url)
    except Exception:
        pass
    return "/admin/login"


class RequireDashboardAuthMiddleware(BaseHTTPMiddleware):
    """Редирект на /admin/login при заходе на /dashboard без авторизации."""
    async def dispatch(self, request: Request, call_next):
        path = request.url.path.rstrip("/") or "/"
        if path.startswith("/dashboard"):
            is_admin = getattr(request, "session", None)
            if is_admin is not None and isinstance(is_admin, dict):
                is_admin = is_admin.get("is_admin")
            if not is_admin:
                return RedirectResponse(url=_login_url(request), status_code=302)
        return await call_next(request)


class LoginRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/admin/login" and request.method == "POST":
            client = request.client.host if request.client else "unknown"
            now = time.monotonic()
            # Удаляем старые попытки
            _LOGIN_ATTEMPTS[client] = [t for t in _LOGIN_ATTEMPTS[client] if now - t < _LOGIN_WINDOW_SEC]
            if len(_LOGIN_ATTEMPTS[client]) >= _LOGIN_RATE_LIMIT:
                return JSONResponse(
                    {"detail": "Слишком много попыток входа. Подождите минуту."},
                    status_code=429,
                )
            _LOGIN_ATTEMPTS[client].append(now)
        return await call_next(request)


def _require_production_secrets() -> None:
    """В production запрещаем дефолтные секреты."""
    if os.getenv("ENVIRONMENT", "").lower() != "production" and os.getenv("PRODUCTION", "").lower() not in ("1", "true", "yes"):
        return
    secret = os.getenv("SESSION_SECRET_KEY")
    if not secret or secret.strip() == "" or secret == "supersecretkey123":
        raise RuntimeError(
            "В production задайте SESSION_SECRET_KEY в .env (уникальное значение). "
            "Не используйте значение по умолчанию."
        )
    admin_pass = os.getenv("ADMIN_PASSWORD")
    if not admin_pass or admin_pass.strip() == "" or admin_pass == "admin":
        raise RuntimeError(
            "В production задайте ADMIN_PASSWORD в .env (надёжный пароль). "
            "Не используйте значение по умолчанию."
        )


_require_production_secrets()

from app.database import engine
from app.admin_views import (
    AdminAuth,
    PropertyAdmin,
    PropertyImageAdmin,
    PropertyDocumentAdmin,
    ObjectFoldersView,
)
from app.routers import router as public_router
from app.dashboard import router as dashboard_router

# Инициализируем приложение (схема БД — через миграции Alembic)
app = FastAPI(
    title="Vitrina Real Estate",
    description="Внутренний каталог коммерческой недвижимости"
)


# Редирект при HTTPException(302) — чтобы зависимости дашборда перенаправляли на логин по той же схеме (https)
@app.exception_handler(HTTPException)
async def http_exception_redirect(request: Request, exc: HTTPException):
    if exc.status_code == 302 and (exc.headers or {}).get("Location") == "/admin/login":
        return RedirectResponse(url=_login_url(request), status_code=302)
    if exc.status_code == 302 and "Location" in (exc.headers or {}):
        return RedirectResponse(url=exc.headers["Location"], status_code=302)
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# --- HEALTH-CHECK для деплоя и оркестрации ---
@app.get("/health/liveness")
def health_liveness():
    """Проверка, что приложение живо. Используется оркестраторами (Kubernetes, Docker)."""
    return {"status": "ok"}


@app.get("/health/readiness")
async def health_readiness():
    """Проверка готовности (в т.ч. доступность БД)."""
    try:
        from sqlalchemy import text
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        return JSONResponse(
            {"status": "error", "detail": str(e)},
            status_code=503,
        )
    return {"status": "ok"}


# --- ПОДКЛЮЧЕНИЕ СТАТИКИ И ШАБЛОНОВ ---
app.mount("/static", StaticFiles(directory="static"), name="static")

# Порядок middleware: Session, затем авторизация/лимиты (X-Forwarded-Proto проверяем в _login_url)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY", "supersecretkey123") or "supersecretkey123",
)
app.add_middleware(RequireDashboardAuthMiddleware)
app.add_middleware(LoginRateLimitMiddleware)


# --- ПУБЛИЧНЫЕ МАРШРУТЫ ---
app.include_router(public_router)

# --- ДАШБОРД МЕНЕДЖЕРОВ ---
app.include_router(dashboard_router)

# --- ПОДКЛЮЧЕНИЕ АДМИНКИ ---
authentication_backend = AdminAuth(
    secret_key=os.getenv("SESSION_SECRET_KEY", "supersecretkey123") or "supersecretkey123",
)
admin = Admin(app, engine, authentication_backend=authentication_backend)
admin.add_base_view(ObjectFoldersView)
admin.add_view(PropertyAdmin)
admin.add_view(PropertyImageAdmin)
admin.add_view(PropertyDocumentAdmin)