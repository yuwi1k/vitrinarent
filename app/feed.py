"""
Единый модуль генерации XML-фида для Авито (Коммерческая недвижимость).
- generate_avito_feed: упрощённый фид для публичного /avito.xml
- generate_avito_feed_full: полный фид для экспорта из дашборда (шаблоны Продам/Сдам).
Контакты: из app.settings_store (файл data/settings.json) или .env.
"""
import logging
import os
from typing import List, Tuple

from lxml import etree

logger = logging.getLogger(__name__)

# Импорт после определения путей приложения
def _get_avito_contacts() -> Tuple[str, str]:
    """(manager_name, contact_phone) для фида Авито."""
    try:
        from app.settings_store import get_avito_manager_name, get_avito_contact_phone
        return get_avito_manager_name(), get_avito_contact_phone()
    except ImportError:
        logger.debug("settings_store not available for Avito feed, falling back to env vars")
    manager = os.getenv("AVITO_MANAGER_NAME", os.getenv("MANAGER_NAME", "Менеджер Vitrina")) or "Менеджер Vitrina"
    phone = os.getenv("AVITO_CONTACT_PHONE", os.getenv("CONTACT_PHONE", "+79102535534")) or "+79102535534"
    return manager.strip(), phone.strip()


# Маппинг категорий Vitrina -> Авито (Коммерческая недвижимость)
AVITO_OBJECT_TYPE_MAP = {
    "Офис": "Офисное помещение",
    "Торговая площадь": "Торговое помещение",
    "Склад": "Складское помещение",
    "Здание": "Здание",
    "ГАБ": "Здание",
    "Промышленное": "Помещение свободного назначения",
    "Свободного назначения": "Помещение свободного назначения",
}
AVITO_OBJECT_TYPE_DEFAULT = "Помещение свободного назначения"


def _cdata_safe(s: str) -> str:
    return (s or "").replace("]]>", "]]]]><![CDATA[>")


def generate_avito_feed(properties: list) -> bytes:
    """Упрощённый XML-фид для публичного /avito.xml (базовые поля)."""
    root = etree.Element("Ads", formatVersion="3", target="Avito.ru")
    manager_name, contact_phone = _get_avito_contacts()
    site_url = os.getenv("SITE_URL", "http://127.0.0.1:8000").rstrip("/")

    for prop in properties:
        ad = etree.SubElement(root, "Ad")
        etree.SubElement(ad, "Id").text = str(prop.id)
        etree.SubElement(ad, "Category").text = "Коммерческая недвижимость"
        operation_type = "Сдам" if (getattr(prop, "deal_type", None) or "").strip() == "Аренда" else "Продам"
        etree.SubElement(ad, "OperationType").text = operation_type
        etree.SubElement(ad, "Price").text = str(prop.price or 0)
        etree.SubElement(ad, "Title").text = ((prop.title or "Объект").strip() or "Объект")[:50]
        etree.SubElement(ad, "Description").text = (prop.description or "Описание отсутствует").strip()
        etree.SubElement(ad, "Address").text = (prop.address or "Москва").strip() or "Москва"
        etree.SubElement(ad, "Square").text = str(prop.area or 0)
        etree.SubElement(ad, "ContactPhone").text = contact_phone
        etree.SubElement(ad, "ManagerName").text = manager_name
        image_urls = []
        if getattr(prop, "main_image", None) and (prop.main_image or "").strip():
            url = (prop.main_image if prop.main_image.startswith("/") else "/" + prop.main_image).strip()
            image_urls.append(site_url + url)
        for img in sorted(getattr(prop, "images", []) or [], key=lambda x: getattr(x, "sort_order", 0)):
            if getattr(img, "image_url", None) and (img.image_url or "").strip():
                url = (img.image_url if img.image_url.startswith("/") else "/" + img.image_url).strip()
                full = site_url + url
                if full not in image_urls:
                    image_urls.append(full)
        if image_urls:
            images_el = etree.SubElement(ad, "Images")
            for url in image_urls[:40]:
                etree.SubElement(images_el, "Image", url=url)

    return etree.tostring(root, pretty_print=True, encoding="UTF-8", xml_declaration=True)


def generate_avito_feed_full(properties: List) -> bytes:
    """Полный XML-фид для экспорта из дашборда (шаблоны Продам и Сдам, все теги Авито)."""
    root = etree.Element("Ads", formatVersion="3", target="Avito.ru")
    site_url = os.getenv("SITE_URL", "http://127.0.0.1:8000").rstrip("/")
    manager_name, contact_phone = _get_avito_contacts()

    for prop in properties:
        ad = etree.SubElement(root, "Ad")
        data = getattr(prop, "avito_data", None) or {}

        def _avito(key: str, default: str = "") -> str:
            v = data.get(key)
            return str(v).strip() if v is not None and str(v).strip() else default

        operation_type = "Сдам" if (getattr(prop, "deal_type", None) or "").strip() == "Аренда" else "Продам"
        object_type = (getattr(prop, "avito_object_type", None) or "").strip()
        if not object_type:
            object_type = AVITO_OBJECT_TYPE_MAP.get((getattr(prop, "category", None) or "").strip(), AVITO_OBJECT_TYPE_DEFAULT)
        deco = _avito("Decoration") or (getattr(prop, "decoration", None) or "").strip() or ("Офисная" if object_type == "Офисное помещение" else "Без отделки")

        def _add(key: str, value: str, cdata: bool = False) -> None:
            if not value:
                return
            if cdata:
                safe = _cdata_safe(value)
                child = etree.fromstring(f"<{key}><![CDATA[{safe}]]></{key}>")
                ad.append(child)
            else:
                sub = etree.SubElement(ad, key)
                sub.text = value

        etree.SubElement(ad, "Id").text = str(prop.id)
        _add("DateBegin", _avito("DateBegin"))
        _add("DateEnd", _avito("DateEnd"))
        _add("ListingFee", _avito("ListingFee"))
        _add("AdStatus", _avito("AdStatus"))
        _add("AvitoId", _avito("AvitoId"))
        etree.SubElement(ad, "ManagerName").text = manager_name
        etree.SubElement(ad, "ContactPhone").text = contact_phone
        _desc_text = (getattr(prop, "description", None) or "Описание отсутствует").strip()
        desc_elem = etree.fromstring(
            "<Description><![CDATA[" + _cdata_safe(_desc_text) + "]]></Description>"
        )
        ad.append(desc_elem)
        image_urls = []
        if getattr(prop, "main_image", None) and (prop.main_image or "").strip():
            url = (prop.main_image if prop.main_image.startswith("/") else "/" + prop.main_image).strip()
            image_urls.append(site_url + url)
        for img in sorted(getattr(prop, "images", []) or [], key=lambda x: getattr(x, "sort_order", 0)):
            if getattr(img, "image_url", None) and (img.image_url or "").strip():
                url = (img.image_url if img.image_url.startswith("/") else "/" + img.image_url).strip()
                full = site_url + url
                if full not in image_urls:
                    image_urls.append(full)
        if image_urls:
            images_el = etree.SubElement(ad, "Images")
            for url in image_urls[:40]:
                etree.SubElement(images_el, "Image", url=url)
        _add("VideoURL", _avito("VideoURL"))
        etree.SubElement(ad, "Address").text = (getattr(prop, "address", None) or "").strip() or "Москва"
        if getattr(prop, "longitude", None) is not None:
            etree.SubElement(ad, "Longitude").text = str(prop.longitude)
        if getattr(prop, "latitude", None) is not None:
            etree.SubElement(ad, "Latitude").text = str(prop.latitude)
        _add("ContactMethod", _avito("ContactMethod"))
        etree.SubElement(ad, "Category").text = "Коммерческая недвижимость"
        etree.SubElement(ad, "Title").text = ((getattr(prop, "title", None) or "Объект недвижимости").strip() or "Объект недвижимости")[:50]
        etree.SubElement(ad, "Price").text = str(int(prop.price) if prop.price is not None else 0)
        _add("InternetCalls", _avito("InternetCalls"))
        _add("CallsDevices", _avito("CallsDevices"))
        _add("PriceWithVAT", _avito("PriceWithVAT"))
        etree.SubElement(ad, "OperationType").text = operation_type
        etree.SubElement(ad, "ObjectType").text = object_type

        if operation_type == "Продам":
            _add("AdditionalObjectTypes", _avito("AdditionalObjectTypes"))
            _add("VideoFileURL", _avito("VideoFileURL"), cdata=True)
            _add("EgrnExtractionLink", _avito("EgrnExtractionLink"), cdata=True)
            _pr = _avito("PropertyRights") or (getattr(prop, "property_rights", None) or "").strip() or "Собственник"
            etree.SubElement(ad, "PropertyRights").text = _pr
            _add("PremisesType", _avito("PremisesType"))
            _ent = _avito("Entrance") or (getattr(prop, "entrance_type", None) or "").strip() or "С улицы"
            etree.SubElement(ad, "Entrance").text = _ent
            _add("EntranceAdditionally", _avito("EntranceAdditionally"))
            _fl = _avito("Floor") or (str(int(prop.floor_number)) if getattr(prop, "floor_number", None) is not None else "") or "1"
            etree.SubElement(ad, "Floor").text = _fl
            _add("FloorAdditionally", _avito("FloorAdditionally"))
            _add("Layout", _avito("Layout") or (getattr(prop, "layout_type", None) or "").strip())
            etree.SubElement(ad, "Square").text = str(float(prop.area) if prop.area is not None else 0)
            _add("PlaceIsRented", _avito("PlaceIsRented"))
            _add("RenterName", _avito("RenterName"))
            _add("RenterMonthPayment", _avito("RenterMonthPayment"))
            _add("RentContractExpireDate", _avito("RentContractExpireDate"))
            _add("PaymentIndexation", _avito("PaymentIndexation"))
            _add("PercentOfTrade", _avito("PercentOfTrade"))
            _add("CeilingHeight", _avito("CeilingHeight") or (str(prop.ceiling_height) if getattr(prop, "ceiling_height", None) is not None else ""))
            etree.SubElement(ad, "Decoration").text = deco
            _add("PowerGridCapacity", _avito("PowerGridCapacity") or (str(prop.power_kw) if getattr(prop, "power_kw", None) is not None else ""))
            _add("PowerGridAdditionally", _avito("PowerGridAdditionally"))
            _add("Heating", _avito("Heating") or (getattr(prop, "heating_type", None) or "").strip())
            _add("ReadinessStatus", _avito("ReadinessStatus"))
            _bt = _avito("BuildingType") or (getattr(prop, "building_type", None) or "").strip() or "Другой"
            etree.SubElement(ad, "BuildingType").text = _bt
            _add("BuildingClass", _avito("BuildingClass") or (getattr(prop, "building_class", None) or "").strip())
            _add("DistanceFromRoad", _avito("DistanceFromRoad") or (getattr(prop, "distance_from_road", None) or "").strip())
            _pt = _avito("ParkingType") or (getattr(prop, "parking_type", None) or "").strip() or "На улице"
            etree.SubElement(ad, "ParkingType").text = _pt
            _add("ParkingAdditionally", _avito("ParkingAdditionally"))
            _add("ParkingSpaces", _avito("ParkingSpaces") or (str(prop.parking_spaces) if getattr(prop, "parking_spaces", None) is not None else ""))
            etree.SubElement(ad, "TransactionType").text = _avito("TransactionType", "Продажа")
            _add("PriceType", _avito("PriceType"))
            _add("SaleOptions", _avito("SaleOptions"))
            _add("AgentSellCommissionPresence", _avito("AgentSellCommissionPresence"))
            _add("AgentSellCommissionSize", _avito("AgentSellCommissionSize"))
        else:
            if object_type == "Офисное помещение":
                etree.SubElement(ad, "OfficeType").text = _avito("OfficeType", "Помещение под офис")
            _add("AdditionalObjectTypes", _avito("AdditionalObjectTypes"))
            _add("VideoFileURL", _avito("VideoFileURL"), cdata=True)
            _add("EgrnExtractionLink", _avito("EgrnExtractionLink"), cdata=True)
            _add("PropertyRights", _avito("PropertyRights") or (getattr(prop, "property_rights", None) or "").strip())
            _add("PremisesType", _avito("PremisesType"))
            _ent = _avito("Entrance") or (getattr(prop, "entrance_type", None) or "").strip() or "С улицы"
            etree.SubElement(ad, "Entrance").text = _ent
            _add("EntranceAdditionally", _avito("EntranceAdditionally"))
            _fl = _avito("Floor") or (str(int(prop.floor_number)) if getattr(prop, "floor_number", None) is not None else "") or "1"
            etree.SubElement(ad, "Floor").text = _fl
            _add("FloorAdditionally", _avito("FloorAdditionally"))
            _add("Layout", _avito("Layout") or (getattr(prop, "layout_type", None) or "").strip())
            etree.SubElement(ad, "Square").text = str(float(prop.area) if prop.area is not None else 0)
            _add("SquareAdditionally", _avito("SquareAdditionally"))
            _add("CeilingHeight", _avito("CeilingHeight") or (str(prop.ceiling_height) if getattr(prop, "ceiling_height", None) is not None else ""))
            etree.SubElement(ad, "Decoration").text = deco
            _add("PowerGridCapacity", _avito("PowerGridCapacity") or (str(prop.power_kw) if getattr(prop, "power_kw", None) is not None else ""))
            _add("PowerGridAdditionally", _avito("PowerGridAdditionally"))
            _add("NumTax", _avito("NumTax"))
            _add("GuaranteeLetter", _avito("GuaranteeLetter"))
            _add("LandlinePhone", _avito("LandlinePhone"))
            _add("MailService", _avito("MailService"))
            _add("Secretary", _avito("Secretary"))
            _add("Heating", _avito("Heating") or (getattr(prop, "heating_type", None) or "").strip())
            _bt = _avito("BuildingType") or (getattr(prop, "building_type", None) or "").strip() or "Другой"
            etree.SubElement(ad, "BuildingType").text = _bt
            _add("BuildingClass", _avito("BuildingClass") or (getattr(prop, "building_class", None) or "").strip())
            _add("DistanceFromRoad", _avito("DistanceFromRoad") or (getattr(prop, "distance_from_road", None) or "").strip())
            _pt = _avito("ParkingType") or (getattr(prop, "parking_type", None) or "").strip() or "На улице"
            etree.SubElement(ad, "ParkingType").text = _pt
            _add("ParkingAdditionally", _avito("ParkingAdditionally"))
            _add("ParkingSpaces", _avito("ParkingSpaces") or (str(prop.parking_spaces) if getattr(prop, "parking_spaces", None) is not None else ""))
            _add("PlacesAmount", _avito("PlacesAmount"))
            _add("WeekendWork", _avito("WeekendWork"))
            _add("Working24Hours", _avito("Working24Hours"))
            _add("WorksFrom", _avito("WorksFrom"))
            _add("WorksTill", _avito("WorksTill"))
            _add("PlaceType", _avito("PlaceType"))
            _add("RoomArea", _avito("RoomArea"))
            _add("PlacesInRoom", _avito("PlacesInRoom"))
            _add("KeyConveniences", _avito("KeyConveniences"))
            _add("ConvenienceIncluded", _avito("ConvenienceIncluded"))
            _add("AvailableHardware", _avito("AvailableHardware"))
            _add("FoodAndDrinks", _avito("FoodAndDrinks"))
            _add("AvailableService", _avito("AvailableService"))
            _add("AdditionalFacilities", _avito("AdditionalFacilities"))
            _rt = _avito("RentalType") or (getattr(prop, "rental_type", None) or "").strip() or "Прямая"
            etree.SubElement(ad, "RentalType").text = _rt
            _add("RentalHolidays", _avito("RentalHolidays"))
            _add("RentalMinimumPeriod", _avito("RentalMinimumPeriod"))
            _add("LeasePriceOptions", _avito("LeasePriceOptions"))
            _add("PriceType", _avito("PriceType"))
            _add("LeaseDeposit", _avito("LeaseDeposit"))
            _add("AgentLeaseCommissionPresence", _avito("AgentLeaseCommissionPresence"))
            _add("AgentLeaseCommissionSize", _avito("AgentLeaseCommissionSize"))

    return etree.tostring(
        root, pretty_print=True, encoding="UTF-8", xml_declaration=True
    )
