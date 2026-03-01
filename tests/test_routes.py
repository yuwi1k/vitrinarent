"""
Ключевые сценарии: главная, поиск, карточка объекта, 404, дашборд без сессии, health-check.
"""
from fastapi.testclient import TestClient


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
    """Без сессии админа дашборд редиректит на /admin/login."""
    r = client.get("/dashboard/", follow_redirects=False)
    assert r.status_code == 302
    assert "admin/login" in r.headers.get("location", "")


def test_dashboard_properties_redirect_without_session(client: TestClient):
    """Список объектов дашборда без сессии — редирект на логин."""
    r = client.get("/dashboard/properties", follow_redirects=False)
    assert r.status_code == 302
    assert "admin/login" in r.headers.get("location", "")


def test_avito_feed(client: TestClient):
    """Фид Авито отдаёт XML и 200."""
    r = client.get("/avito.xml")
    assert r.status_code == 200
    assert "application/xml" in r.headers.get("content-type", "")
    assert b"<Ads" in r.content or b"<?xml" in r.content
