import os
import time
from collections import defaultdict

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

load_dotenv()

# Rate limiting для логина: макс. 5 попыток в минуту с одного IP
_LOGIN_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_LOGIN_RATE_LIMIT = 5
_LOGIN_WINDOW_SEC = 60


def _login_url(request: Request) -> str:
    """URL страницы логина дашборда: тот же хост и схема (https если nginx передал X-Forwarded-Proto)."""
    try:
        proto = (request.headers.get("x-forwarded-proto") or "").strip().lower()
        if proto == "https":
            host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
            return f"https://{host.rstrip('/')}/dashboard/login"
        url = request.url.replace(path="/dashboard/login", query="")
        return str(url)
    except Exception:
        pass
    return "/dashboard/login"


class RequireDashboardAuthMiddleware(BaseHTTPMiddleware):
    """Редирект на /dashboard/login при заходе на /dashboard без авторизации (кроме /dashboard/login)."""
    async def dispatch(self, request: Request, call_next):
        path = (request.url.path or "").rstrip("/") or "/"
        if path.startswith("/dashboard") and not path.startswith("/dashboard/login"):
            session = request.scope.get("session")
            is_admin = isinstance(session, dict) and session.get("is_admin")
            if not is_admin:
                return RedirectResponse(url=_login_url(request), status_code=302)
        return await call_next(request)


class LoginRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/dashboard/login" and request.method == "POST":
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


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Простейшая защита от CSRF для форм дашборда.
    Проверяет токен из сессии против _csrf_token в форме / X-CSRF-Token заголовка.
    """

    async def dispatch(self, request: Request, call_next):
        method = request.method.upper()
        path = (request.url.path or "")
        # Логин оставляем без CSRF, чтобы не усложнять форму и тесты.
        if path == "/dashboard/login":
            return await call_next(request)
        if method in ("POST", "PUT", "PATCH", "DELETE") and path.startswith("/dashboard"):
            session = request.session or {}
            expected = session.get("_csrf_token")
            token = None

            # 1) Пытаемся взять токен из заголовка
            header_token = request.headers.get("X-CSRF-Token")
            if header_token:
                token = header_token
            else:
                # 2) Иначе аккуратно парсим тело, не трогая request.form(),
                #    чтобы не сломать последующую обработку Form-параметров FastAPI.
                content_type = (request.headers.get("content-type") or "").lower()
                try:
                    body_bytes = await request.body()
                    text = body_bytes.decode("utf-8", errors="ignore")
                except Exception:
                    text = ""

                if "application/x-www-form-urlencoded" in content_type and text:
                    from urllib.parse import parse_qs

                    parsed = parse_qs(text, keep_blank_values=True)
                    vals = parsed.get("_csrf_token") or []
                    token = vals[0] if vals else None
                elif "multipart/form-data" in content_type and text:
                    # Простейший парсер для multipart: ищем блок с name="_csrf_token"
                    marker = 'name="_csrf_token"'
                    idx = text.find(marker)
                    if idx != -1:
                        # Берём часть от маркера и ищем первую пустую строку,
                        # за которой идёт строка со значением токена.
                        tail = text[idx:].splitlines()
                        for i, line in enumerate(tail):
                            if not line.strip() and i + 1 < len(tail):
                                possible = tail[i + 1].strip()
                                if possible:
                                    token = possible
                                break

            if not expected or not token or token != expected:
                return JSONResponse(
                    {"detail": "CSRF token missing or invalid"},
                    status_code=403,
                )
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
    if exc.status_code == 302 and (exc.headers or {}).get("Location") == "/dashboard/login":
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
# Явно отдаём фон главной, чтобы картинка грузилась и за прокси, и из Docker
def _find_hero_bg():
    base = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "static", "images"))
    if not os.path.isdir(base):
        base = os.path.normpath(os.path.join("static", "images"))
    for name in ("hero_bg_1.png", "hero_bg_1.jpg"):
        path = os.path.join(base, name)
        if os.path.isfile(path):
            return path, "image/png" if name.endswith(".png") else "image/jpeg"
    return None, None


@app.get("/static/images/hero_bg_1.png", include_in_schema=False)
async def hero_background_image():
    path, media_type = _find_hero_bg()
    if not path:
        raise HTTPException(status_code=404, detail="Hero image not found")
    return FileResponse(path, media_type=media_type)


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/favicon.ico")
async def favicon():
    """Отдаём favicon из статики, чтобы убрать 404 в логах браузера."""
    return FileResponse("static/images/favicon.png")


@app.get("/robots.txt", include_in_schema=False)
async def robots_txt(request: Request) -> PlainTextResponse:
    """
    Динамический robots.txt:
    - Разрешаем индексацию всего, кроме /dashboard
    - Отдаём ссылку на sitemap.xml с учётом реального домена/схемы.
    """
    # Определяем базовый URL с учётом возможного прокси
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc or "").strip()
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "https").split(",")[0].strip() or "https"
    base = f"{proto}://{host}".rstrip("/") if host else str(request.url.replace(path="", query="")).rstrip("/")

    lines = [
        "User-agent: *",
        "Disallow: /dashboard/",
        "",
        f"Sitemap: {base}/sitemap.xml",
        "",
    ]
    return PlainTextResponse("\n".join(lines))


# Порядок middleware: последний add = первый при обработке запроса.
# Итоговый порядок обработки: Session -> CSRF -> RequireDashboardAuth -> LoginRateLimit -> app.
app.add_middleware(LoginRateLimitMiddleware)
app.add_middleware(RequireDashboardAuthMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY", "supersecretkey123") or "supersecretkey123",
)


# --- ПУБЛИЧНЫЕ МАРШРУТЫ ---
app.include_router(public_router)

# --- ДАШБОРД МЕНЕДЖЕРОВ (единственная панель управления) ---
app.include_router(dashboard_router)