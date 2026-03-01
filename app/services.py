from typing import Optional
from sqlalchemy import select, or_
from app.models import Property


def _parse_int(value: Optional[str]) -> Optional[int]:
    if not value or not value.strip():
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def build_search_query(
    q: Optional[str] = None,
    deal_type: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[str] = None,
    max_price: Optional[str] = None,
    min_area: Optional[str] = None,
    max_area: Optional[str] = None,
):
    stmt = select(Property).where(Property.is_active == True)

    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(Property.title.ilike(pattern), Property.address.ilike(pattern)))
    if deal_type and deal_type != "Все":
        stmt = stmt.where(Property.deal_type == deal_type)
    if category and category != "Все":
        stmt = stmt.where(Property.category == category)

    min_price_val = _parse_int(min_price)
    max_price_val = _parse_int(max_price)
    if min_price_val is not None:
        stmt = stmt.where(Property.price >= min_price_val)
    if max_price_val is not None:
        stmt = stmt.where(Property.price <= max_price_val)

    if min_area and min_area.strip():
        try:
            stmt = stmt.where(Property.area >= float(min_area.strip()))
        except ValueError:
            pass
    if max_area and max_area.strip():
        try:
            stmt = stmt.where(Property.area <= float(max_area.strip()))
        except ValueError:
            pass

    return stmt
