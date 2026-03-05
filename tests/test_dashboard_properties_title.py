import os

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.admin_password import get_admin_password
from app.main import app
from app.database import AsyncSessionLocal
from app.models import Property


def _login_as_admin(client: TestClient) -> None:
    username = os.getenv("ADMIN_USERNAME", "admin")
    password = get_admin_password()
    r = client.post("/dashboard/login", data={"username": username, "password": password})
    assert r.status_code in (200, 302, 303)


def _get_csrf_token_from_html(html: str) -> str:
    marker = 'name="_csrf_token" value="'
    idx = html.find(marker)
    assert idx != -1, "CSRF token field not found in form"
    start = idx + len(marker)
    end = html.find('"', start)
    assert end != -1
    return html[start:end]


def test_create_property_saves_title_and_status():
    client = TestClient(app)
    _login_as_admin(client)

    # GET form to initialize CSRF token
    r_form = client.get("/dashboard/properties/new")
    assert r_form.status_code == 200
    token = _get_csrf_token_from_html(r_form.text)

    title_value = "Тестовый объект pytest"

    # Создаём новый объект с title и is_active
    # Считаем количество объектов ДО
    import asyncio

    async def _count_props():
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(Property))
            return len(res.scalars().all())

    before_count = asyncio.run(_count_props())

    r_create = client.post(
        "/dashboard/properties/new",
        data={
            "_csrf_token": token,
            "title": title_value,
            "slug": "",
            "description": "",
            "price": "1000",
            "area": "10",
            "address": "",
            "deal_type": "Аренда",
            "category": "Офис",
            "is_active": "1",
        },
        follow_redirects=True,
    )
    # Должен успешно отработать (200 или редирект)
    assert r_create.status_code in (200, 302, 303)

    # Проверяем, что количество объектов увеличилось
    after_count = asyncio.run(_count_props())
    assert after_count == before_count + 1

    # Проверяем напрямую в БД, что title сохранился
    async def _get_latest():
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(Property).order_by(Property.id.desc()).limit(1))
            return res.scalar_one()

    latest = asyncio.run(_get_latest())
    assert latest.title == title_value


def test_edit_property_updates_title():
    client = TestClient(app)
    _login_as_admin(client)

    # Создаём объект как в предыдущем тесте
    r_form = client.get("/dashboard/properties/new")
    assert r_form.status_code == 200
    token = _get_csrf_token_from_html(r_form.text)

    r_create = client.post(
        "/dashboard/properties/new",
        data={
            "_csrf_token": token,
            "title": "Объект для редактирования",
            "slug": "",
            "description": "",
            "price": "1000",
            "area": "10",
            "address": "",
            "deal_type": "Аренда",
            "category": "Офис",
            "is_active": "1",
        },
        follow_redirects=False,
    )
    # После создания редирект на /dashboard/properties/edit/{id}
    assert r_create.status_code in (302, 303)
    location = r_create.headers.get("location") or ""
    assert "/dashboard/properties/edit/" in location
    edit_path = location

    # Получаем CSRF с формы редактирования
    r_edit_form = client.get(edit_path)
    assert r_edit_form.status_code == 200
    token2 = _get_csrf_token_from_html(r_edit_form.text)

    new_title = "Обновлённый заголовок pytest"

    r_update = client.post(
        edit_path,
        data={
            "_csrf_token": token2,
            "title": new_title,
            "slug": "",
            "description": "",
            "price": "2000",
            "area": "20",
            "address": "",
            "deal_type": "Аренда",
            "category": "Офис",
            "is_active": "1",
        },
        follow_redirects=True,
    )
    assert r_update.status_code in (200, 302, 303)

    async def _get_latest():
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(Property).order_by(Property.id.desc()).limit(1))
            return res.scalar_one()

    import asyncio

    latest = asyncio.run(_get_latest())
    assert latest.title == new_title

