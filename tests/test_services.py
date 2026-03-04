"""
Тесты для app.services (поиск, фильтры).
"""
from sqlalchemy import select
from app.services import build_search_query
from app.models import Property


def test_build_search_query_filters_active():
    """По умолчанию поиск фильтрует только активные объекты."""
    stmt = build_search_query()
    compiled = stmt.compile(compile_kwargs={"literal_binds": True})
    text = str(compiled)
    # В запросе должно быть условие на is_active
    assert "is_active" in text or "IS_ACTIVE" in text.upper()


def test_build_search_query_deal_type_filter():
    """Фильтр по типу сделки сужает запрос."""
    stmt = build_search_query(deal_type="Аренда")
    compiled = stmt.compile(compile_kwargs={"literal_binds": True})
    text = str(compiled)
    assert "Аренда" in text


def test_build_search_query_category_filter():
    """Фильтр по категории сужает запрос."""
    stmt = build_search_query(category="Офис")
    compiled = stmt.compile(compile_kwargs={"literal_binds": True})
    text = str(compiled)
    assert "Офис" in text


def test_build_search_query_price_filters():
    """Фильтры min_price/max_price задают центр диапазона ±30% (см. services.py)."""
    stmt = build_search_query(min_price="100000", max_price="500000")
    compiled = stmt.compile(compile_kwargs={"literal_binds": True})
    text = str(compiled)
    # Центр (100000+500000)/2 = 300000 → low=210000, high=390000
    assert "210000" in text and "390000" in text
    assert "price" in text.lower()


def test_build_search_query_text_search():
    """Параметр q добавляет поиск по title/address."""
    stmt = build_search_query(q="Арбат")
    compiled = stmt.compile(compile_kwargs={"literal_binds": True})
    text = str(compiled)
    assert "Арбат" in text or "%" in text
