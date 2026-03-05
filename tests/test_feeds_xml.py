"""
Тесты для XML-фидов Авито и Циан.

Здесь проверяем структуру и ключевые поля, используя generate_* напрямую
на "фейковых" объектах без обращения к БД.
"""
from dataclasses import dataclass, field
from typing import Any, List

from lxml import etree

from app.feed import generate_avito_feed
from app.feed_cian import generate_cian_feed


@dataclass
class DummyImage:
    image_url: str
    sort_order: int = 0


@dataclass
class DummyProperty:
    id: int
    deal_type: str
    price: int
    area: float
    title: str
    description: str
    address: str
    main_image: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    floor_number: int | None = None
    floors_total: int | None = None
    ceiling_height: float | None = None
    avito_data: dict[str, Any] | None = None
    cian_data: dict[str, Any] | None = None
    images: List[DummyImage] = field(default_factory=list)


def test_generate_avito_feed_basic_structure():
    """Avito-фид: root Ads, по одному Ad на объект, корректный OperationType и базовые теги."""
    props = [
        DummyProperty(
            id=1,
            deal_type="Аренда",
            price=100000,
            area=120.5,
            title="Офис на Тверской",
            description="Светлый офис рядом с метро.",
            address="Москва, Тверская улица, 1",
            main_image="/static/uploads/test1.jpg",
        ),
        DummyProperty(
            id=2,
            deal_type="Продажа",
            price=25000000,
            area=300.0,
            title="Склад в промзоне",
            description="Склад с удобным подъездом для фур.",
            address="Москва, Промышленная улица, 5",
            main_image=None,
        ),
    ]

    xml_bytes = generate_avito_feed(props)
    root = etree.fromstring(xml_bytes)

    assert root.tag == "Ads"
    ads = root.findall("Ad")
    assert len(ads) == 2

    ad_rent = ads[0]
    assert ad_rent.findtext("Id") == "1"
    assert ad_rent.findtext("Category") == "Коммерческая недвижимость"
    assert ad_rent.findtext("OperationType") == "Сдам"
    assert ad_rent.findtext("Price") == "100000"
    assert ad_rent.findtext("Title") == "Офис на Тверской"
    assert "Тверская" in (ad_rent.findtext("Address") or "")
    assert ad_rent.find("Images") is not None

    ad_sale = ads[1]
    assert ad_sale.findtext("Id") == "2"
    assert ad_sale.findtext("OperationType") == "Продам"
    assert ad_sale.find("Images") is None  # main_image не задан


def test_generate_cian_feed_rent_and_sale_categories_and_bargain_terms():
    """
    Циан-фид: проверяем Category для аренды/продажи и структуру BargainTerms.
    Аренда: PaymentPeriod/LeaseType присутствуют.
    Продажа: ContractType присутствует, PaymentPeriod/LeaseType отсутствуют.
    """
    rent_prop = DummyProperty(
        id=10,
        deal_type="Аренда",
        price=200000,
        area=150.0,
        title="Офис аренда",
        description="Офис для аренды, описание не короче 15 символов.",
        address="Москва, улица Аренды, 10",
        latitude=55.75,
        longitude=37.61,
        cian_data={
            "CianCategory": "officeRent",
            "PaymentPeriod": "monthly",
            "LeaseType": "direct",
            "Currency": "rur",
            "VatType": "included",
            "Floor": "3",
            "FloorsTotal": "10",
        },
    )

    sale_prop = DummyProperty(
        id=20,
        deal_type="Продажа",
        price=30000000,
        area=280.0,
        title="Офис продажа",
        description="Офис для продажи, описание тоже достаточно длинное.",
        address="Москва, улица Продажи, 20",
        latitude=55.76,
        longitude=37.62,
        cian_data={
            "CianCategory": "officeSale",
            "Currency": "rur",
            "VatType": "included",
            "ContractType": "sale",
            "Floor": "5",
            "FloorsTotal": "12",
        },
    )

    xml_bytes = generate_cian_feed([rent_prop, sale_prop])
    root = etree.fromstring(xml_bytes)

    assert root.tag == "feed"
    assert root.findtext("feed_version") == "2"

    objects = root.findall("object")
    assert len(objects) == 2

    obj_rent = objects[0]
    assert obj_rent.findtext("ExternalId") == "10"
    assert obj_rent.findtext("Category") == "officeRent"
    bargain_rent = obj_rent.find("BargainTerms")
    assert bargain_rent is not None
    assert bargain_rent.findtext("Price") == "200000"
    assert bargain_rent.findtext("Currency") == "rur"
    assert bargain_rent.findtext("VatType") == "included"
    assert bargain_rent.findtext("PaymentPeriod") == "monthly"
    assert bargain_rent.findtext("LeaseType") == "direct"

    obj_sale = objects[1]
    assert obj_sale.findtext("ExternalId") == "20"
    assert obj_sale.findtext("Category") == "officeSale"
    bargain_sale = obj_sale.find("BargainTerms")
    assert bargain_sale is not None
    assert bargain_sale.findtext("Price") == "30000000"
    assert bargain_sale.findtext("Currency") == "rur"
    assert bargain_sale.findtext("VatType") == "included"
    assert bargain_sale.findtext("ContractType") == "sale"
    # Для продажи в нашей реализации PaymentPeriod и LeaseType не должны присутствовать
    assert bargain_sale.find("PaymentPeriod") is None
    assert bargain_sale.find("LeaseType") is None

