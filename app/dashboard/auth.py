"""
Вход и выход из дашборда.
"""
import os

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

from app.admin_password import get_admin_password
from app.dashboard.common import templates

router = APIRouter()


def _get_expected_username() -> str:
    return os.getenv("ADMIN_USERNAME", "admin")


@router.get("/login")
async def login_page(request: Request):
    """Страница входа в панель (форма)."""
    if request.session.get("is_admin"):
        return RedirectResponse(url="/dashboard", status_code=302)
    error = request.query_params.get("error")
    if error == "invalid":
        error = "Неверный логин или пароль"
    username = request.query_params.get("username") or ""
    return templates.TemplateResponse(
        "dashboard/login.html",
        {"request": request, "error": error, "username": username},
    )


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
):
    """Обработка формы входа: проверка учётных данных, установка сессии, редирект на /dashboard."""
    expected_username = _get_expected_username()
    expected_password = get_admin_password()
    if (username or "").strip() == expected_username and password == expected_password:
        request.session["is_admin"] = True
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(
        "dashboard/login.html",
        {"request": request, "error": "Неверный логин или пароль", "username": (username or "").strip()},
        status_code=200,
    )


@router.get("/logout")
async def logout(request: Request):
    """Выход: очистка сессии и редирект на страницу входа."""
    request.session.clear()
    return RedirectResponse(url="/dashboard/login", status_code=302)
