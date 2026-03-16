"""
Генерация XML-фида для выгрузки объявлений на Циан (импорт по URL фида).

Формат: официальная схема v2 (feed_version=2, тег <object>).
Категории и enum-значения — по официальной документации:
  https://www.cian.ru/xml_import/doc/#common_cat  (общие категории и поля)

Категории аренды: freeAppointmentObjectRent, officeRent, warehouseRent, industryRent,
shoppingAreaRent, buildingRent, garageRent, commercialLandRent.
Категории продажи: freeAppointmentObjectSale, officeSale, warehouseSale и др. (см. раздел выше).
BargainTerms для аренды: PaymentPeriod, LeaseType; ConditionType, Layout, InputType, Building/Type — по доке.
"""
import logging
import os
import re
from typing import List, Tuple

from lxml import etree

logger = logging.getLogger(__name__)


def _cdata_safe(s: str) -> str:
    return (s or "").replace("]]>", "]]]]><![CDATA[>")


def _prepare_description(text: str) -> str:
    """Convert newlines to <br> for feed descriptions (CIAN supports HTML in CDATA)."""
    s = (text or "").strip()
    if not s:
        return "Описание отсутствует"
    return s.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>\n")


def _get_cian_contacts() -> tuple[str, str]:
    """(manager_name, contact_phone) для фида Циан."""
    try:
        from app.settings_store import get_avito_manager_name, get_avito_contact_phone
        return get_avito_manager_name(), get_avito_contact_phone()
    except ImportError:
        logger.debug("settings_store not available for CIAN feed, falling back to env vars")
    manager = os.getenv("AVITO_MANAGER_NAME", os.getenv("MANAGER_NAME", "Менеджер")) or "Менеджер"
    phone = os.getenv("AVITO_CONTACT_PHONE", os.getenv("CONTACT_PHONE", "+79102535534")) or "+79102535534"
    return manager.strip(), phone.strip()


def _parse_phone(phone: str) -> Tuple[str, str]:
    """Разбивает телефон на код страны и номер (только цифры)."""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("8") and len(digits) >= 11:
        digits = "7" + digits[1:]
    if digits.startswith("7") and len(digits) >= 11:
        return "+7", digits[1:11]
    if len(digits) >= 10:
        return "+7", digits[-10:]
    return "+7", digits or "0000000000"


# Маппинг типа здания (форма/русский) -> enum Циан Building/Type (полный список по доке #common_cat)
CIAN_BUILDING_TYPE_MAP = {
    "Бизнес-центр": "businessCenter",
    "Торговый центр": "shoppingCenter",
    "Административное здание": "administrativeBuilding",
    "Жилой дом": "residentialHouse",
    "Другой": "other",
    "businessCenter": "businessCenter",
    "shoppingCenter": "shoppingCenter",
    "administrativeBuilding": "administrativeBuilding",
    "officeBuilding": "officeBuilding",
    "free": "free",
    # Расширенный список из документации Циан (здание, офис, склад, производство, торговая площадь)
    "businessCenter2": "businessCenter2",
    "businessHouse": "businessHouse",
    "businessPark": "businessPark",
    "businessQuarter": "businessQuarter",
    "businessQuarter2": "businessQuarter2",
    "industrialComplex": "industrialComplex",
    "industrialPark": "industrialPark",
    "industrialSite": "industrialSite",
    "industrialWarehouseComplex": "industrialWarehouseComplex",
    "logisticsCenter": "logisticsCenter",
    "logisticsComplex": "logisticsComplex",
    "logisticsPark": "logisticsPark",
    "mansion": "mansion",
    "manufactureBuilding": "manufactureBuilding",
    "manufacturingFacility": "manufacturingFacility",
    "modular": "modular",
    "multifunctionalComplex": "multifunctionalComplex",
    "officeAndHotelComplex": "officeAndHotelComplex",
    "officeAndResidentialComplex": "officeAndResidentialComplex",
    "officeAndWarehouse": "officeAndWarehouse",
    "officeAndWarehouseComplex": "officeAndWarehouseComplex",
    "officeCenter": "officeCenter",
    "officeComplex": "officeComplex",
    "officeIndustrialComplex": "officeIndustrialComplex",
    "officeQuarter": "officeQuarter",
    "old": "old",
    "outlet": "outlet",
    "propertyComplex": "propertyComplex",
    "residentialComplex": "residentialComplex",
    "shoppingAndBusinessComplex": "shoppingAndBusinessComplex",
    "shoppingAndCommunityCenter": "shoppingAndCommunityCenter",
    "shoppingAndEntertainmentCenter": "shoppingAndEntertainmentCenter",
    "shoppingAndWarehouseComplex": "shoppingAndWarehouseComplex",
    "shoppingComplex": "shoppingComplex",
    "specializedShoppingCenter": "specializedShoppingCenter",
    "standaloneBuilding": "standaloneBuilding",
    "technopark": "technopark",
    "tradeAndExhibitionComplex": "tradeAndExhibitionComplex",
    "tradingHouse": "tradingHouse",
    "tradingOfficeComplex": "tradingOfficeComplex",
    "warehouse": "warehouse",
    "warehouseComplex": "warehouseComplex",
}

# Допустимые значения ConditionType (Помещение свободного назначения)
CIAN_CONDITION_TYPES = {
    "cosmeticRepairsRequired",
    "design",
    "finishing",
    "majorRepairsRequired",
    "office",
    "typical",
}

# Отделка/состояние -> ConditionType
CIAN_CONDITION_TYPE_MAP = {
    "Без отделки": "finishing",
    "Чистовая": "typical",
    "Офисная": "office",
    "cosmeticRepairsRequired": "cosmeticRepairsRequired",
    "design": "design",
    "finishing": "finishing",
    "majorRepairsRequired": "majorRepairsRequired",
    "office": "office",
    "typical": "typical",
}

# Планировка -> Layout
CIAN_LAYOUT_MAP = {
    "Кабинетная": "cabinet",
    "Открытая": "openSpace",
    "Смешанная": "mixed",
    "Коридорная": "corridorplan",
    "cabinet": "cabinet",
    "openSpace": "openSpace",
    "mixed": "mixed",
    "corridorplan": "corridorplan",
}

# Вход -> InputType
CIAN_INPUT_TYPE_MAP = {
    "С улицы": "commonFromStreet",
    "Со двора": "commonFromYard",
    "commonFromStreet": "commonFromStreet",
    "commonFromYard": "commonFromYard",
    "separateFromStreet": "separateFromStreet",
    "separateFromYard": "separateFromYard",
}

# Парковка -> Building/Parking/Type
CIAN_PARKING_TYPE_MAP = {
    "Нет": None,
    "На улице": "open",
    "В здании": "underground",
    "ground": "ground",
    "multilevel": "multilevel",
    "open": "open",
    "roof": "roof",
    "underground": "underground",
}


def generate_cian_feed(properties: list) -> bytes:
    """
    Генерирует XML-фид для Циан по схеме v2 (Помещение свободного назначения).
    ExternalId = property.id для сопоставления с объявлениями в API.
    """
    site_url = os.getenv("SITE_URL", "http://127.0.0.1:8000").rstrip("/")
    manager_name, contact_phone = _get_cian_contacts()
    country_code, number = _parse_phone(contact_phone)

    root = etree.Element("feed")
    etree.SubElement(root, "feed_version").text = "2"

    for prop in properties:
        obj = etree.SubElement(root, "object")

        deal_type = (getattr(prop, "deal_type", None) or "").strip()
        cian_data = getattr(prop, "cian_data", None) or {}
        if not isinstance(cian_data, dict):
            cian_data = {}
        # Категория из формы: для аренды и продажи (officeRent, officeSale и т.д.)
        if deal_type == "Продажа":
            cat = (cian_data.get("CianCategory") or "freeAppointmentObjectSale").strip()
            if not cat or cat.endswith("Rent"):
                cat = "freeAppointmentObjectSale"
            etree.SubElement(obj, "Category").text = cat
        else:
            cat = (cian_data.get("CianCategory") or "freeAppointmentObjectRent").strip()
            if not cat or cat.endswith("Sale"):
                cat = "freeAppointmentObjectRent"
            etree.SubElement(obj, "Category").text = cat

        etree.SubElement(obj, "ExternalId").text = str(prop.id)

        desc_raw = (getattr(prop, "description", None) or "Описание отсутствует").strip()
        if len(desc_raw) < 15:
            desc_raw = desc_raw + " " + "Коммерческое помещение." * 2
        desc = _prepare_description(desc_raw[:3000])
        desc_el = etree.fromstring(
            f"<Description><![CDATA[{_cdata_safe(desc)}]]></Description>"
        )
        obj.append(desc_el)

        etree.SubElement(obj, "Address").text = (
            (getattr(prop, "address", None) or "Москва").strip() or "Москва"
        )

        lat = getattr(prop, "latitude", None)
        lng = getattr(prop, "longitude", None)
        if lat is not None and lng is not None:
            try:
                coords = etree.SubElement(obj, "Coordinates")
                etree.SubElement(coords, "Lat").text = str(float(lat))
                etree.SubElement(coords, "Lng").text = str(float(lng))
            except (TypeError, ValueError):
                logger.warning("CIAN feed: invalid coordinates for property %s: lat=%s lng=%s", prop.id, lat, lng)

        phones = etree.SubElement(obj, "Phones")
        phone_schema = etree.SubElement(phones, "PhoneSchema")
        etree.SubElement(phone_schema, "CountryCode").text = country_code
        etree.SubElement(phone_schema, "Number").text = number

        area_val = float(prop.area) if prop.area is not None else 0
        etree.SubElement(obj, "TotalArea").text = str(area_val)

        floor_val = cian_data.get("Floor")
        if floor_val is not None and str(floor_val).strip():
            try:
                etree.SubElement(obj, "FloorNumber").text = str(int(float(str(floor_val).strip())))
            except (ValueError, TypeError):
                logger.warning("CIAN feed: invalid floor value for property %s: %s", prop.id, floor_val)
        elif getattr(prop, "floor_number", None) is not None:
            etree.SubElement(obj, "FloorNumber").text = str(int(prop.floor_number))

        # ConditionType: из формы (enum) или маппинг из Decoration
        condition_raw = (cian_data.get("ConditionType") or "").strip()
        if condition_raw in CIAN_CONDITION_TYPES:
            condition = condition_raw
        else:
            deco = (cian_data.get("Decoration") or "").strip() or (getattr(prop, "decoration", None) or "").strip()
            condition = CIAN_CONDITION_TYPE_MAP.get(deco) or "office"
        etree.SubElement(obj, "ConditionType").text = condition

        # Layout: из формы (русский или enum) или по умолчанию cabinet
        layout_raw = (cian_data.get("Layout") or "").strip() or (getattr(prop, "layout_type", None) or "").strip()
        layout = (
            CIAN_LAYOUT_MAP.get(layout_raw)
            or CIAN_LAYOUT_MAP.get(layout_raw.capitalize() if layout_raw else "")
            or "cabinet"
        )
        etree.SubElement(obj, "Layout").text = layout

        # Фото: первое с IsDefault=true, остальные по порядку
        image_urls: List[str] = []
        if getattr(prop, "main_image", None) and (prop.main_image or "").strip():
            url = prop.main_image if prop.main_image.startswith("/") else "/" + (prop.main_image or "")
            image_urls.append(site_url + url.strip())
        for img in sorted(getattr(prop, "images", []) or [], key=lambda x: getattr(x, "sort_order", 0)):
            if getattr(img, "image_url", None) and (img.image_url or "").strip():
                url = img.image_url if img.image_url.startswith("/") else "/" + (img.image_url or "")
                full = site_url + url
                if full not in image_urls:
                    image_urls.append(full)
        if image_urls:
            layout_photo = etree.SubElement(obj, "LayoutPhoto")
            etree.SubElement(layout_photo, "FullUrl").text = image_urls[0]
            etree.SubElement(layout_photo, "IsDefault").text = "true"
            photos_el = etree.SubElement(obj, "Photos")
            for i, url in enumerate(image_urls[:50]):
                photo_schema = etree.SubElement(photos_el, "PhotoSchema")
                etree.SubElement(photo_schema, "FullUrl").text = url
                etree.SubElement(photo_schema, "IsDefault").text = "true" if i == 0 else "false"

        # InputType: из формы или маппинг из Entrance
        input_type_raw = (cian_data.get("InputType") or "").strip()
        if input_type_raw and input_type_raw in CIAN_INPUT_TYPE_MAP:
            input_type = input_type_raw
        else:
            entrance = (cian_data.get("Entrance") or "").strip() or (getattr(prop, "entrance_type", None) or "").strip()
            input_type = CIAN_INPUT_TYPE_MAP.get(entrance) or "commonFromStreet"
        etree.SubElement(obj, "InputType").text = input_type

        # Building
        building = etree.SubElement(obj, "Building")
        bld_name = (getattr(prop, "title", None) or "Объект").strip() or "Объект"
        etree.SubElement(building, "Name").text = bld_name[:500]
        floors_val = cian_data.get("FloorsTotal")
        if floors_val is not None and str(floors_val).strip():
            try:
                etree.SubElement(building, "FloorsCount").text = str(int(float(str(floors_val).strip())))
            except (ValueError, TypeError):
                logger.warning("CIAN feed: invalid FloorsTotal for property %s: %s, defaulting to 1", prop.id, floors_val)
                etree.SubElement(building, "FloorsCount").text = "1"
        elif getattr(prop, "floors_total", None) is not None:
            etree.SubElement(building, "FloorsCount").text = str(int(prop.floors_total))
        else:
            etree.SubElement(building, "FloorsCount").text = "1"
        etree.SubElement(building, "TotalArea").text = str(area_val)
        heating_raw = (getattr(prop, "heating_type", None) or "").strip()
        heating_map = {"Центральное": "central", "Автономное": "autonomous", "Нет": "none"}
        etree.SubElement(building, "HeatingType").text = heating_map.get(heating_raw, "central")
        ceiling_val = cian_data.get("CeilingHeight")
        if ceiling_val is not None and str(ceiling_val).strip():
            try:
                etree.SubElement(building, "CeilingHeight").text = str(float(str(ceiling_val).strip().replace(",", ".")))
            except (ValueError, TypeError):
                logger.warning("CIAN feed: invalid CeilingHeight for property %s: %s", prop.id, ceiling_val)
        elif getattr(prop, "ceiling_height", None) is not None:
            etree.SubElement(building, "CeilingHeight").text = str(prop.ceiling_height)
        bld_type_raw = (cian_data.get("BuildingType") or "").strip() or (getattr(prop, "building_type", None) or "").strip()
        bld_type = CIAN_BUILDING_TYPE_MAP.get(bld_type_raw) or "other"
        etree.SubElement(building, "Type").text = bld_type
        etree.SubElement(building, "StatusType").text = "operational"
        parking_raw = (cian_data.get("ParkingType") or "").strip() or (getattr(prop, "parking_type", None) or "").strip()
        parking_type = CIAN_PARKING_TYPE_MAP.get(parking_raw)
        if parking_type:
            parking_el = etree.SubElement(building, "Parking")
            etree.SubElement(parking_el, "Type").text = parking_type

        # PublishTerms
        publish = etree.SubElement(obj, "PublishTerms")
        etree.SubElement(publish, "PromotionType").text = "noPromotion"

        # BargainTerms: по доке Циан аренда — Price, PriceType, Currency, PaymentPeriod, LeaseType, VatType;
        # продажа — Price, Currency, VatType, ContractType (leaseAssignment | sale), без PriceType/PaymentPeriod/LeaseType
        bargain = etree.SubElement(obj, "BargainTerms")
        price_val = int(prop.price) if prop.price is not None else 0
        etree.SubElement(bargain, "Price").text = str(price_val)
        currency_raw = (cian_data.get("Currency") or "rur").strip().lower() or "rur"
        currency = currency_raw if currency_raw in ("eur", "rur", "usd") else "rur"
        etree.SubElement(bargain, "Currency").text = currency
        vat_raw = (cian_data.get("VatType") or "included").strip().lower() or "included"
        etree.SubElement(bargain, "VatType").text = vat_raw if vat_raw in ("included", "usn") else "included"
        if deal_type == "Продажа":
            # По доке для продажи: Price, Currency, VatType, ContractType (без PriceType)
            contract_raw = (cian_data.get("ContractType") or "sale").strip().lower() or "sale"
            contract = contract_raw if contract_raw in ("leaseassignment", "sale") else "sale"
            if contract == "leaseassignment":
                etree.SubElement(bargain, "ContractType").text = "leaseAssignment"
            else:
                etree.SubElement(bargain, "ContractType").text = "sale"
        else:
            etree.SubElement(bargain, "PriceType").text = "all"
            payment_period = (cian_data.get("PaymentPeriod") or "monthly").strip() or "monthly"
            if payment_period not in ("annual", "monthly"):
                payment_period = "monthly"
            etree.SubElement(bargain, "PaymentPeriod").text = payment_period
            lease_type = (cian_data.get("LeaseType") or "direct").strip() or "direct"
            if lease_type not in ("direct", "sublease"):
                rental = (cian_data.get("RentalType") or "").strip().lower() or (getattr(prop, "rental_type", None) or "").strip().lower()
                lease_type = "sublease" if "суб" in rental or rental == "sublease" else "direct"
            etree.SubElement(bargain, "LeaseType").text = lease_type

        # Title (опционально, 8-33 символов)
        title = (getattr(prop, "title", None) or "Объект").strip() or "Объект"
        if 8 <= len(title) <= 33:
            etree.SubElement(obj, "Title").text = title
        else:
            short = title[:33].strip() if len(title) > 33 else title
            if len(short) >= 8:
                etree.SubElement(obj, "Title").text = short
            else:
                etree.SubElement(obj, "Title").text = (short + " коммерческая недвижимость")[:33]

    return etree.tostring(
        root, pretty_print=True, encoding="UTF-8", xml_declaration=True
    )
