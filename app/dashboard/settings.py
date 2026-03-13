"""
Настройки дашборда: смена пароля, контакты для фидов, пороги уведомлений.
"""
import json

from fastapi import APIRouter, Request, Depends, Form
from app.admin_password import check_admin_password, set_admin_password
from app.dashboard.common import check_admin, templates
from app.notification_config import get_scenarios_for_edit, save_scenarios
from app.settings_store import get_settings_for_edit, save_settings

router = APIRouter()


@router.get("/settings/password", dependencies=[Depends(check_admin)])
async def settings_password_form(request: Request):
    return templates.TemplateResponse(
        "dashboard/settings_password.html",
        {"request": request, "error": None, "success": False},
    )


@router.post("/settings/password", dependencies=[Depends(check_admin)])
async def settings_password_change(
    request: Request,
    current_password: str = Form(""),
    new_password: str = Form(""),
    new_password_confirm: str = Form(""),
):
    error = None
    if not current_password.strip():
        error = "Введите текущий пароль."
    elif not check_admin_password(current_password):
        error = "Текущий пароль неверен."
    elif not new_password.strip():
        error = "Введите новый пароль."
    elif len(new_password) < 6:
        error = "Новый пароль должен быть не короче 6 символов."
    elif new_password != new_password_confirm:
        error = "Повтор нового пароля не совпадает."
    if error:
        return templates.TemplateResponse(
            "dashboard/settings_password.html",
            {"request": request, "error": error, "success": False},
            status_code=400,
        )
    set_admin_password(new_password)
    return templates.TemplateResponse(
        "dashboard/settings_password.html",
        {"request": request, "error": None, "success": True},
    )


@router.get("/settings", dependencies=[Depends(check_admin)])
async def settings_form(request: Request):
    settings_data = get_settings_for_edit()
    return templates.TemplateResponse(
        "dashboard/settings.html",
        {"request": request, "settings": settings_data, "error": None, "success": False},
    )


@router.post("/settings", dependencies=[Depends(check_admin)])
async def settings_save(
    request: Request,
    avito_manager_name: str = Form(""),
    avito_contact_phone: str = Form(""),
    contact_phone: str = Form(""),
    contact_email: str = Form(""),
    contact_telegram: str = Form(""),
):
    save_settings(
        avito_manager_name=avito_manager_name,
        avito_contact_phone=avito_contact_phone,
        contact_phone=contact_phone,
        contact_email=contact_email,
        contact_telegram=contact_telegram,
    )
    settings_data = get_settings_for_edit()
    return templates.TemplateResponse(
        "dashboard/settings.html",
        {"request": request, "settings": settings_data, "error": None, "success": True},
    )


@router.get("/settings/notifications", dependencies=[Depends(check_admin)])
async def notification_settings_form(request: Request):
    return templates.TemplateResponse(
        "dashboard/settings_notifications.html",
        {"request": request, "scenarios": get_scenarios_for_edit(), "error": None, "success": False},
    )


@router.post("/settings/notifications", dependencies=[Depends(check_admin)])
async def notification_settings_save(request: Request):
    form = await request.form()
    scenarios = get_scenarios_for_edit()
    updates: dict[str, dict] = {}

    int_fields = ("min_views", "max_views", "min_contacts", "max_contacts",
                  "min_favorites", "max_items_in_message")
    float_fields = ("min_conversion", "max_conversion")

    for s in scenarios:
        key = s["key"]
        updates[key] = {}

        enabled_val = form.get(f"{key}__enabled")
        updates[key]["enabled"] = enabled_val == "on"

        for fld in int_fields:
            raw = (form.get(f"{key}__{fld}") or "").strip()
            if raw == "" or raw == "—":
                updates[key][fld] = None
            else:
                try:
                    updates[key][fld] = int(raw)
                except ValueError:
                    pass

        for fld in float_fields:
            raw = (form.get(f"{key}__{fld}") or "").strip()
            if raw == "" or raw == "—":
                updates[key][fld] = None
            else:
                try:
                    updates[key][fld] = float(raw)
                except ValueError:
                    pass

    save_scenarios(updates)
    return templates.TemplateResponse(
        "dashboard/settings_notifications.html",
        {"request": request, "scenarios": get_scenarios_for_edit(), "error": None, "success": True},
    )
