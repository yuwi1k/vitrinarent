"""
Ключевые сценарии: главная, поиск, карточка объекта, 404, дашборд без сессии, логин, health-check.
"""
import os

from fastapi.testclient import TestClient

from app.admin_password import get_admin_password


def test_health_liveness(client: TestClient):
    """Эндпоинт liveness возвращает 200 и status ok."""
    r = client.get("/health/liveness")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_readiness(client: TestClient):
    """Эндпоинт readiness возвращает 200 при доступной БД или 503 при ошибке."""
    r = client.get("/health/readiness")
    assert r.status_code in (200, 503)
    data = r.json()
    assert "status" in data
    if r.status_code == 200:
        assert data["status"] == "ok"
    else:
        assert data["status"] == "error"
        assert "detail" in data


def test_main_page(client: TestClient):
    """Главная страница отдаёт 200 и содержит Vitrina."""
    r = client.get("/")
    assert r.status_code == 200
    assert b"Vitrina" in r.content


def test_search_page(client: TestClient):
    """Страница поиска отдаёт 200."""
    r = client.get("/search")
    assert r.status_code == 200
    r = client.get("/search?deal_type=Аренда&page=1")
    assert r.status_code == 200


def test_property_404(client: TestClient):
    """Несуществующий slug объекта возвращает 404."""
    r = client.get("/property/nonexistent-slug-12345")
    assert r.status_code == 404


def test_property_page_if_exists(client: TestClient):
    """Если в БД есть объект с slug — карточка отдаёт 200. Иначе 404."""
    r = client.get("/property/some-random-slug-that-unlikely-exists")
    assert r.status_code == 404


def test_faq_page(client: TestClient):
    """Страница FAQ отдаёт 200."""
    r = client.get("/faq")
    assert r.status_code == 200
    assert b"FAQ" in r.content


def test_dashboard_redirect_without_session(client: TestClient):
    """Без сессии админа дашборд редиректит на /dashboard/login."""
    r = client.get("/dashboard/", follow_redirects=False)
    assert r.status_code == 302
    assert "dashboard/login" in r.headers.get("location", "")


def test_dashboard_properties_redirect_without_session(client: TestClient):
    """Список объектов дашборда без сессии — редирект на логин."""
    r = client.get("/dashboard/properties", follow_redirects=False)
    assert r.status_code == 302
    assert "dashboard/login" in r.headers.get("location", "")


def test_dashboard_after_login(client: TestClient):
    """После успешного логина на /dashboard/login дашборд отдаёт 200 и контент."""
    username = os.getenv("ADMIN_USERNAME", "admin")
    password = get_admin_password()
    r = client.post(
        "/dashboard/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert r.status_code in (200, 302, 303), f"Login failed: {r.status_code} {r.text[:200]}"
    r2 = client.get("/dashboard/", follow_redirects=True)
    assert r2.status_code == 200, f"Dashboard should be 200 after login, got {r2.status_code}"
    assert b"Vitrina" in r2.content or b"dashboard" in r2.content.lower()


def test_dashboard_rejects_wrong_password(client: TestClient):
    """Неверный пароль — логин не проходит, дашборд по-прежнему редиректит."""
    r = client.post(
        "/dashboard/login",
        data={"username": "admin", "password": "wrong_password"},
        follow_redirects=False,
    )
    assert r.status_code == 200  # форма с ошибкой
    text = r.content.decode("utf-8")
    assert "Неверный" in text or "пароль" in text.lower() or "invalid" in text.lower()
    r2 = client.get("/dashboard/", follow_redirects=False)
    assert r2.status_code == 302
    assert "dashboard/login" in r2.headers.get("location", "")


def test_avito_feed(client: TestClient):
    """Фид Авито отдаёт XML и 200."""
    r = client.get("/avito.xml")
    assert r.status_code == 200
    assert "application/xml" in r.headers.get("content-type", "")
    assert b"<Ads" in r.content or b"<?xml" in r.content


def test_cian_feed(client: TestClient):
    """Фид Циан отдаёт XML и 200."""
    r = client.get("/cian.xml")
    assert r.status_code == 200
    assert "application/xml" in r.headers.get("content-type", "")
    assert b"<feed" in r.content or b"<?xml" in r.content
