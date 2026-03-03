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


def _parse_float(value: Optional[str]) -> Optional[float]:
    if not value or not value.strip():
        return None
    try:
        return float(value.strip().replace(",", "."))
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
    # Все активные объекты; и корневые, и дочерние (помещения)
    stmt = select(Property).where(Property.is_active == True)

    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(Property.title.ilike(pattern), Property.address.ilike(pattern)))
    if deal_type and deal_type != "Все":
        stmt = stmt.where(Property.deal_type == deal_type)
    if category and category != "Все":
        stmt = stmt.where(Property.category == category)

    # Цена: введённое значение используется как центр диапазона ±30%
    price_vals = []
    min_price_val = _parse_int(min_price)
    max_price_val = _parse_int(max_price)
    if min_price_val is not None:
        price_vals.append(min_price_val)
    if max_price_val is not None and max_price_val != min_price_val:
        price_vals.append(max_price_val)
    if price_vals:
        center_price = sum(price_vals) / len(price_vals)
        low_price = int(center_price * 0.7)
        high_price = int(center_price * 1.3)
        stmt = stmt.where(Property.price >= low_price, Property.price <= high_price)

    # Площадь: введённое значение используется как центр диапазона ±30%
    area_vals = []
    min_area_val = _parse_float(min_area)
    max_area_val = _parse_float(max_area)
    if min_area_val is not None:
        area_vals.append(min_area_val)
    if max_area_val is not None and max_area_val != min_area_val:
        area_vals.append(max_area_val)
    if area_vals:
        center_area = sum(area_vals) / len(area_vals)
        low_area = center_area * 0.7
        high_area = center_area * 1.3
        stmt = stmt.where(Property.area >= low_area, Property.area <= high_area)

    return stmt
