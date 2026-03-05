import os

from fastapi.testclient import TestClient

from app.main import app
from app.admin_password import get_admin_password


def test_debug_properties_form_receives_title():
    client = TestClient(app)
    username = os.getenv("ADMIN_USERNAME", "admin")
    password = get_admin_password()
    r_login = client.post("/dashboard/login", data={"username": username, "password": password})
    assert r_login.status_code in (200, 302, 303)

    # Получаем CSRF-токен с формы создания
    r_form = client.get("/dashboard/properties/new")
    assert r_form.status_code == 200
    html = r_form.text
    marker = 'name="_csrf_token" value="'
    idx = html.find(marker)
    assert idx != -1
    start = idx + len(marker)
    end = html.find('"', start)
    token = html[start:end]

    r_debug = client.post(
        "/dashboard/properties/_debug_form",
        data={
            "_csrf_token": token,
            "title": "DEBUG TITLE",
            "slug": "",
            "price": "1000",
            "area": "10",
            "deal_type": "Аренда",
            "category": "Офис",
            "is_active": "1",
        },
    )
    assert r_debug.status_code == 200
    payload = r_debug.json()
    form = payload.get("form", {})
    # Ожидаем, что поле title есть и содержит нашу строку
    assert "title" in form
    assert "DEBUG TITLE" in form["title"]

