from typing import Optional, List, Dict, Any
from sqlalchemy import select, or_
from app.models import Property


BUILDING_PREVIEW_COUNT = 3


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


def group_properties_by_building(
    properties: list,
    has_active_filters: bool = False,
) -> List[Dict[str, Any]]:
    """Group a flat list of properties into building groups + standalones.

    Returns list of dicts:
      - group:      {"type": "building", "building": Property, "units": [...], "total_units": int}
      - standalone: {"type": "standalone", "property": Property}
    """
    building_map: Dict[int, Dict[str, Any]] = {}
    standalones: list = []

    for prop in properties:
        if prop.parent_id is not None:
            bid = prop.parent_id
            if bid not in building_map:
                building_map[bid] = {"building": prop.parent, "units": []}
            building_map[bid]["units"].append(prop)
        else:
            active_children = [c for c in (prop.children or []) if c.is_active]
            if active_children:
                if prop.id not in building_map:
                    building_map[prop.id] = {"building": prop, "units": []}
                else:
                    building_map[prop.id]["building"] = prop
            else:
                standalones.append(prop)

    groups: List[Dict[str, Any]] = []

    for data in building_map.values():
        building = data["building"]
        matched = data["units"]
        all_active = [c for c in (building.children or []) if c.is_active] if building else []

        if not matched:
            units = all_active
        elif has_active_filters:
            units = matched
        else:
            units = all_active

        groups.append({
            "type": "building",
            "building": building,
            "units": units,
            "total_units": len(all_active),
        })

    for prop in standalones:
        groups.append({
            "type": "standalone",
            "property": prop,
        })

    return groups


def build_search_query(
    q: Optional[str] = None,
    deal_type: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[str] = None,
    max_price: Optional[str] = None,
    min_area: Optional[str] = None,
    max_area: Optional[str] = None,
    object_type: Optional[str] = None,
):
    from sqlalchemy.orm import selectinload

    stmt = select(Property).where(Property.is_active == True).options(
        selectinload(Property.children),
        selectinload(Property.parent).selectinload(Property.children),
    )

    if object_type == "building":
        stmt = stmt.where(Property.parent_id.is_(None))
    elif object_type == "unit":
        stmt = stmt.where(Property.parent_id.isnot(None))

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
